from copy import deepcopy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from genesis.api import create_app
from genesis.models import Scenario, digest
from genesis.storage import Store


def test_restart_replay_export_import_fork(tmp_path):
    path = tmp_path / "world.sqlite"
    store = Store(path)
    rid = store.create(Scenario(snapshot_every=7))
    hashes = {0: digest(store.load(rid))}
    for _ in range(25):
        s = store.step(rid)
        hashes[s["tick"]] = digest(s)
    store.checkpoint(rid)
    restarted = Store(path)
    for tick, hashed in hashes.items():
        assert digest(restarted.replay(rid, tick)) == hashed
    fork = restarted.fork(rid, 11)
    for _ in range(14):
        restarted.step(fork)
    assert digest(restarted.load(fork)) == hashes[25]
    export = restarted.export(rid)
    other = Store(tmp_path / "import.sqlite")
    imported = other.import_run(export)
    assert digest(other.load(imported)) == hashes[25]
    assert digest(other.step(imported)) == digest(restarted.step(rid))


def test_corrupt_snapshot_artifact_and_export_rejected(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    rid = store.create(Scenario())
    for _ in range(20):
        store.step(rid)
    payload = store.export(rid)
    payload["state"]["tick"] = 900
    with pytest.raises(ValueError, match="checksum"):
        store.import_run(payload)
    with store.connection() as db, db:
        db.execute("UPDATE snapshots SET state_hash='bad' WHERE run_id=? AND tick=20", (rid,))
    with pytest.raises(ValueError, match="snapshot"):
        store.replay(rid, 20)
    payload = store.export(rid)
    artifact = next(iter(payload["state"]["artifacts"].values()))
    artifact["content"]["program"] = {"op": "mode", "value": 1}
    with store.connection() as db, db:
        # Even if materialized hash is recomputed, content addressing catches corrupt artifacts.
        db.execute("UPDATE runs SET state=?,state_hash=? WHERE id=?", (json.dumps(payload["state"]), digest(payload["state"]), rid))
    with pytest.raises(ValueError, match="artifact"):
        store.load(rid)


def test_crash_rolls_back_entire_tick(tmp_path, monkeypatch):
    store = Store(tmp_path / "db.sqlite")
    rid = store.create(Scenario())
    before = digest(store.load(rid))
    original = store._commit_tick

    def fail_after_writes(*args):
        original(*args)
        raise RuntimeError("simulated interruption before commit")

    monkeypatch.setattr(store, "_commit_tick", fail_after_writes)
    with pytest.raises(RuntimeError):
        store.step(rid, request_id="crash")
    assert digest(Store(store.path).load(rid)) == before
    assert store.events(rid) == []
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 0


def test_idempotency_under_concurrent_writers(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    rid = store.create(Scenario())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.step(rid, request_id="same-intent"), range(4)))
    assert store.load(rid)["tick"] == 1
    assert len({digest(s) for s in results}) == 1
    with store.connection() as db, pytest.raises(Exception, match="append only"):
        db.execute("DELETE FROM ticks")


def test_api_offline_controls_submission_and_idempotency(tmp_path):
    app = create_app(tmp_path / "api.sqlite")
    with TestClient(app) as client:
        assert client.get("/api/health").json()["offline"]
        rid = client.get("/api/status").json()["run_id"]
        first = client.get(f"/api/runs/{rid}").json()
        assert first["state"]["tick"] == 0
        command = {"operation": "step", "request_id": "ui-click-1"}
        assert client.post("/api/control", json=command).status_code == 200
        assert client.post("/api/control", json=command).status_code == 200
        assert client.get(f"/api/runs/{rid}").json()["state"]["tick"] == 1
        checkpoint = client.post(f"/api/runs/{rid}/checkpoint").json()
        assert checkpoint["tick"] == 1
        assert client.get(f"/api/runs/{rid}?tick=0").json()["hash"] == first["hash"]
        submitted = {"request_id": "manual", "action": {"id": "manual-move", "agent": "a00", "tick": 1, "kind": "move", "params": {"x": 22, "y": 8}}}
        response = client.post(f"/api/runs/{rid}/actions", json=submitted)
        assert response.status_code == 200 and not response.json()["result"]["accepted"]
        repeated = client.post(f"/api/runs/{rid}/actions", json=submitted)
        assert repeated.json() == response.json()
        submitted["action"]["kind"] = "wait"
        submitted["action"]["params"] = {}
        assert client.post(f"/api/runs/{rid}/actions", json=submitted).status_code == 409
        assert client.post("/api/control", json={"operation": "run"}).json()["running"]
        assert client.post("/api/control", json=command).status_code == 409
        assert not client.post("/api/control", json={"operation": "pause"}).json()["running"]
        fork = client.post(f"/api/runs/{rid}/fork", json={"tick": 1}).json()["run_id"]
        assert fork != rid
        assert client.get(f"/api/runs/{fork}").json()["state"]["tick"] == 1
        assert client.get(f"/api/runs/{rid}/export").json()["format"] == "genesis-export-1"
        assert client.get(f"/api/runs/{rid}?tick=9999").status_code == 409


def test_experiment_configuration_parity(tmp_path):
    from genesis.experiments import CONDITIONS, PairedExperiments
    report = PairedExperiments().run([11, 42], 4, str(tmp_path), removal_tick=2)
    assert report["completed_runs"] == 2 * len(CONDITIONS) and report["failed_runs"] == 0
    varied = {"sharing", "controller", "removal"}
    for seed in (11, 42):
        configs = [dict(a["config"]) for a in report["attempts"] if a["seed"] == seed]
        assert len(configs) == len(CONDITIONS)
        shared = [{k: v for k, v in c.items() if k not in varied} for c in configs]
        assert all(c == shared[0] for c in shared)
        assert all((tmp_path / a["export"]).exists() for a in report["attempts"] if a["seed"] == seed)
    import gzip
    exported = json.loads(gzip.decompress((tmp_path / report["attempts"][0]["export"]).read_bytes()))
    assert digest(Store(tmp_path / "reimport.sqlite").load(Store(tmp_path / "reimport.sqlite").import_run(exported))) == report["attempts"][0]["metrics"]["state_hash"]


def test_older_engine_runs_are_read_only_and_skipped_at_startup(tmp_path):
    path = tmp_path / "db.sqlite"
    store = Store(path)
    old = store.create(Scenario())
    store.step(old)
    with store.connection() as db, db:
        row = db.execute("SELECT manifest FROM runs WHERE id=?", (old,)).fetchone()
        manifest = json.loads(row[0])
        manifest["engine_version"] = "0.0.1"
        db.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(manifest), old))
    assert store.load(old)["tick"] == 1 and store.replay(old, 0)["tick"] == 0
    for operation in (lambda: store.step(old), lambda: store.fork(old, 0), lambda: store.require_writable(old)):
        with pytest.raises(ValueError, match="read-only"):
            operation()
    assert not next(r for r in store.list_runs() if r["id"] == old)["compatible"]
    app = create_app(path, tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/status").json()["run_id"] != old
        assert client.get(f"/api/runs/{old}").status_code == 200
        client.post("/api/control", json={"operation": "select", "run_id": old})
        assert client.post("/api/control", json={"operation": "run"}).status_code == 409
        assert client.get("/api/experiments").json() == {"available": False}


def test_built_observatory_is_served_with_the_api(tmp_path):
    from pathlib import Path
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if not (dist / "index.html").exists():
        pytest.skip("frontend not built; run npm run build in frontend/")
    with TestClient(create_app(tmp_path / "ui.sqlite", tmp_path)) as client:
        page = client.get("/")
        assert page.status_code == 200 and '<div id="root">' in page.text
        script = next(part.split('"')[0] for part in page.text.split('src="')[1:] if part.startswith("/assets/"))
        assert client.get(script).status_code == 200
        assert client.get("/api/health").json()["offline"]


def test_list_shift_deltas_round_trip():
    import random
    from genesis.storage import apply_delta, changes
    rng = random.Random(7)
    for _ in range(300):
        before = {"log": [rng.randint(0, 9) for _ in range(rng.randint(0, 12))], "n": 1}
        after = {"log": list(before["log"]), "n": rng.randint(0, 2)}
        operation = rng.choice(["shift", "append", "replace", "same", "clear"])
        if operation == "shift":
            after["log"] = after["log"][rng.randint(0, len(after["log"])):] + [rng.randint(0, 9) for _ in range(rng.randint(0, 4))]
        elif operation == "append":
            after["log"] += [rng.randint(0, 9)]
        elif operation == "replace":
            after["log"] = [rng.randint(0, 9) for _ in range(rng.randint(0, 12))]
        elif operation == "clear":
            after["log"] = []
        assert apply_delta(before, changes(before, after)) == after
