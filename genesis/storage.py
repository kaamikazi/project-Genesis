from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
from .controllers import OfflineController
from .engine import advance
from .models import Action, JSON, Scenario, canonical, digest
from .world import check_invariants, new_world
from .model import ledger as model_ledger
from .model.ledger import DDL as MODEL_DDL

SCHEMA = 1


def changes(before: Any, after: Any, path: list[str] | None = None) -> list[JSON]:
    path = path or []
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            if key not in after:
                result.append({"path": path + [key], "delete": True})
            elif key not in before:
                result.append({"path": path + [key], "value": after[key]})
            else:
                result.extend(changes(before[key], after[key], path + [key]))
        return result
    if isinstance(before, list) and isinstance(after, list) and path:
        # Bounded logs (memories, uses, messages) mostly shift: record dropped-from-front + appended.
        for drop in range(len(before)):
            kept = len(before) - drop
            if after[:kept] == before[drop:]:
                return [{"path": path, "drop": drop, "append": after[kept:]}]
    return [{"path": path, "value": after}]


def apply_delta(state: JSON, delta: list[JSON]) -> JSON:
    result = deepcopy(state)
    for item in delta:
        path = item["path"]
        if not path:
            result = deepcopy(item["value"])
            continue
        target = result
        for key in path[:-1]:
            target = target[key]
        if item.get("delete"):
            del target[path[-1]]
        elif "append" in item:
            target[path[-1]] = target[path[-1]][item["drop"]:] + deepcopy(item["append"])
        else:
            target[path[-1]] = deepcopy(item["value"])
    return result


def validate_state(state: JSON) -> None:
    Scenario.model_validate(state["config"])
    check_invariants(state)
    for key, artifact in state["artifacts"].items():
        if key != artifact["id"] or digest(artifact["content"]) != key:
            raise ValueError("corrupt artifact")


def is_current(manifest: JSON) -> bool:
    return (manifest["engine_version"], manifest["rule_version"], manifest["evaluator_version"], manifest["schema_version"]) == (ENGINE_VERSION, RULE_VERSION, EVALUATOR_VERSION, SCHEMA)


def readable(manifest: JSON) -> None:
    if digest(manifest["config"]) != manifest["config_hash"]:
        raise ValueError("configuration hash mismatch")


def compatible(manifest: JSON) -> None:
    """Continuation (step, fork, import) needs the exact versions that wrote the history.
    Older runs stay readable and replayable from recorded deltas, never silently continued."""
    readable(manifest)
    if not is_current(manifest):
        raise ValueError(f'run written by engine {manifest["engine_version"]} / {manifest["rule_version"]}; '
                         f'this is {ENGINE_VERSION} / {RULE_VERSION}. History is preserved read-only; start a new run to continue')


class Store:
    def __init__(self, path: str | Path = "data/genesis.sqlite"):
        self.path = Path(path)
        self.model_transports: dict = {}      # per-instance: run id -> transport (tests, tools); never persisted
        self.model_hooks: dict = {}           # per-instance: run id -> crash-simulation hooks (tests only)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA):
                raise ValueError("unsupported database schema; migration required")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, manifest TEXT NOT NULL, initial TEXT NOT NULL, state TEXT NOT NULL, state_hash TEXT NOT NULL, tick INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS ticks(run_id TEXT NOT NULL REFERENCES runs(id), tick INTEGER NOT NULL, record TEXT NOT NULL, record_hash TEXT NOT NULL, elapsed_ms REAL NOT NULL, engine_ms REAL NOT NULL, PRIMARY KEY(run_id,tick));
                CREATE TABLE IF NOT EXISTS snapshots(run_id TEXT NOT NULL REFERENCES runs(id), tick INTEGER NOT NULL, state TEXT NOT NULL, state_hash TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY(run_id,tick));
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(run_id TEXT NOT NULL REFERENCES runs(id), key TEXT NOT NULL, fingerprint TEXT NOT NULL, tick INTEGER NOT NULL, PRIMARY KEY(run_id,key));
                CREATE TABLE IF NOT EXISTS action_ids(run_id TEXT NOT NULL REFERENCES runs(id), id TEXT NOT NULL, PRIMARY KEY(run_id,id));
                CREATE TRIGGER IF NOT EXISTS immutable_ticks_update BEFORE UPDATE ON ticks BEGIN SELECT RAISE(ABORT, 'history is append only'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_ticks_delete BEFORE DELETE ON ticks BEGIN SELECT RAISE(ABORT, 'history is append only'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_artifacts_update BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT, 'artifacts are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_artifacts_delete BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT, 'artifacts are immutable'); END;
                PRAGMA user_version=1;
            """)
            db.executescript(MODEL_DDL)          # v0.6: additive sidecar tables for the model call ledger

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    def _row(self, db, run_id):
        row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("run not found")
        return row

    def _decode(self, row, continuing: bool = False) -> JSON:
        state = json.loads(row["state"])
        manifest = json.loads(row["manifest"])
        (compatible if continuing else readable)(manifest)
        if digest(state) != row["state_hash"] or state["config"] != manifest["config"]:
            raise ValueError("materialized state hash/config mismatch")
        validate_state(state)
        return state

    def _insert_run(self, db, manifest: JSON, state: JSON) -> None:
        payload, hashed = canonical(state), digest(state)
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)", (manifest["id"], canonical(manifest), payload, payload, hashed, state["tick"]))
        db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)", (manifest["id"], state["tick"], payload, hashed, "origin"))
        self._artifacts(db, state)

    def _artifacts(self, db, state: JSON) -> None:
        for aid, a in state["artifacts"].items():
            if digest(a["content"]) != aid:
                raise ValueError("artifact hash mismatch")
            db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?)", (aid, canonical(a["content"])))
            stored = db.execute("SELECT content FROM artifacts WHERE hash=?", (aid,)).fetchone()[0]
            if digest(json.loads(stored)) != aid:
                raise ValueError("corrupt stored artifact")

    def create(self, config: Scenario, initial: JSON | None = None, parent: JSON | None = None, model_profile=None) -> str:
        state = deepcopy(initial) if initial is not None else new_world(config)
        validate_state(state)
        run_id = uuid.uuid4().hex[:12]
        manifest = {"id": run_id, "engine_version": ENGINE_VERSION, "rule_version": RULE_VERSION,
                    "evaluator_version": EVALUATOR_VERSION, "schema_version": SCHEMA,
                    "config": config.model_dump(), "config_hash": digest(config.model_dump()),
                    "controller_mode": config.controller if model_profile is None else f"{config.controller}; model-backed agents {model_profile.agents} ({model_profile.mode})",
                    "model_calls_allowed": bool(model_profile is not None and model_profile.mode == "live" and model_profile.live_authorized),
                    "parent": parent, "origin_tick": state["tick"], "initial_hash": digest(state),
                    "random_streams": {"world": ["world-terrain", "environment-phase"],
                                       "controller (independent seed, never observed)": ["controller-search", "controller-revision"]},
                    "controller_privileges": "restricted local observation; own memories; accessible artifacts; no seed, config, ledger or evaluation records",
                    "scenario_design": "finite ore; food replenishes 2/site/tick up to 120; initial food 8/agent; unlimited settlement storage for members",
                    "removal_policy": config.removal if config.removal == "none" else f"{config.removal} at tick {config.removal_tick}",
                    "succession_policy": config.succession if config.succession == "none" else f"{config.succession} successors, role {config.successor_role}, access {config.successor_access}"}
        if state["config"] != manifest["config"]:
            raise ValueError("fork configuration must match state")
        if model_profile is not None:
            from .model.profile import config_hash
            manifest["model_profile_hash"] = digest(model_profile.model_dump())
            manifest["model_config_hash"] = config_hash(model_profile)
        with self.connection() as db, db:
            self._insert_run(db, manifest, state)
            if model_profile is not None:
                db.execute("INSERT INTO model_profiles VALUES(?,?,?,0)", (run_id, canonical(model_profile.model_dump()), digest(model_profile.model_dump())))
        return run_id

    # --- v0.6 model-backed inhabitants -----------------------------------------------------------------------------

    def model_profile(self, run_id: str):
        from .model.profile import ModelProfile
        with self.connection() as db:
            row = db.execute("SELECT profile FROM model_profiles WHERE run_id=?", (run_id,)).fetchone()
        return ModelProfile.model_validate(json.loads(row[0])) if row else None

    def model_paused(self, run_id: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT paused FROM model_profiles WHERE run_id=?", (run_id,)).fetchone()
        return bool(row and row[0])

    def set_model_paused(self, run_id: str, paused: bool) -> None:
        with self.connection() as db, db:
            if db.execute("UPDATE model_profiles SET paused=? WHERE run_id=?", (int(paused), run_id)).rowcount != 1:
                raise KeyError("run has no model profile")

    def resolve_unknown(self, run_id: str, decision_id: str, note: str) -> None:
        """Operator acknowledgement of an outcome-unknown request: model use may resume; the reservation stays counted."""
        with self.connection() as db, db:
            row = model_ledger.get(db, decision_id)
            if row is None or row["run_id"] != run_id or row["status"] != "outcome-unknown":
                raise ValueError("only an outcome-unknown request of this run can be resolved")
            model_ledger.update(db, decision_id, resolved=1, termination=(row["termination"] or "") + f"; resolved by operator: {note[:120]}")

    def model_calls(self, run_id: str) -> list[JSON]:
        with self.connection() as db:
            return model_ledger.export_rows(db, run_id)

    def model_latencies(self, run_id: str) -> list[JSON]:
        """Provider latency (wall clock, outside world-state hashes)."""
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT decision_id, latency_ms FROM model_calls WHERE run_id=? AND latency_ms IS NOT NULL ORDER BY seq", (run_id,))]

    def _model_transport(self, run_id: str, profile):
        from .model.fixtures import default_fixture_transport
        from .model.transport import GeminiTransport, HttpTransport
        if run_id in self.model_transports:
            return self.model_transports[run_id]
        if profile.adapter.provider == "gemini":
            from .model.fixtures import default_gemini_fixture_transport
            if profile.mode == "fixture":
                return default_gemini_fixture_transport()
            if profile.mode == "mock-http":
                return GeminiTransport.for_loopback_test(profile.adapter.base_url)
            if profile.mode == "live":
                return GeminiTransport("live")             # official origin only; key read at dispatch
            return None
        if profile.mode == "fixture":
            return default_fixture_transport()
        if profile.mode == "mock-http":
            return HttpTransport("mock-http", loopback_only=True)
        if profile.mode == "live":
            return HttpTransport("live", loopback_only=False)
        return None

    def list_runs(self) -> list[JSON]:
        with self.connection() as db:
            return [{"id": r["id"], "tick": r["tick"], "manifest": m, "compatible": is_current(m)}
                    for r in db.execute("SELECT id,tick,manifest FROM runs ORDER BY rowid DESC") for m in [json.loads(r["manifest"])]]

    def load(self, run_id: str) -> JSON:
        with self.connection() as db:
            return self._decode(self._row(db, run_id))

    def step(self, run_id: str, overrides: dict[str, Action] | None = None, request_id: str | None = None) -> JSON:
        start = time.perf_counter()
        fingerprint = digest({key: value.model_dump() for key, value in sorted((overrides or {}).items())})
        profile, prepared, prepared_hash = self.model_profile(run_id), None, None
        if profile is not None and not request_id_seen(self, run_id, request_id):
            # Phase A (no write transaction is held while a provider may be contacted).
            from .model.runtime import ModelRuntime
            current = self.load(run_id)
            self.require_writable(run_id)
            runtime = ModelRuntime(self, run_id, profile, self._model_transport(run_id, profile), hooks=self.model_hooks.get(run_id))
            prepared, prepared_hash = runtime.prepare(current), digest(current)
        with self.connection() as db, db:
            db.execute("BEGIN IMMEDIATE")
            if request_id:
                prior = db.execute("SELECT fingerprint,tick FROM requests WHERE run_id=? AND key=?", (run_id, request_id)).fetchone()
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise ValueError("idempotency key reused with a different payload")
                    return self._replay(db, run_id, prior["tick"])
            row = self._row(db, run_id)
            before = self._decode(row, continuing=True)
            # Only externally supplied ids can repeat across ticks; generated ids include the tick.
            prior_ids = {a.id for a in (overrides or {}).values() if db.execute("SELECT 1 FROM action_ids WHERE run_id=? AND id=?", (run_id, a.id)).fetchone()}
            engine_start = time.perf_counter()
            controller = OfflineController(before["config"]["controller_seed"])
            if prepared is not None:
                if digest(before) != prepared_hash:
                    raise ValueError("world changed during model preparation; prepared decisions were not applied")
                from .model.controller import ModelController
                controller = ModelController(controller, prepared, profile.agents)
            after, events, decisions = advance(before, controller, overrides, prior_ids)
            engine_ms = (time.perf_counter()-engine_start)*1000
            prev = db.execute("SELECT record_hash FROM ticks WHERE run_id=? ORDER BY tick DESC LIMIT 1", (run_id,)).fetchone()
            record = {"tick": after["tick"], "before_hash": digest(before), "state_hash": digest(after),
                      "previous_record_hash": prev[0] if prev else digest(before),
                      "events": events, "decisions": decisions, "delta": changes(before, after)}
            self._commit_tick(db, run_id, after, record, start, engine_ms)
            if request_id:
                db.execute("INSERT INTO requests VALUES(?,?,?,?)", (run_id, request_id, fingerprint, after["tick"]))
            return after

    def _commit_tick(self, db, run_id, state, record, start, engine_ms):
        self._artifacts(db, state)
        db.execute("INSERT INTO ticks VALUES(?,?,?,?,?,?)", (run_id, state["tick"], canonical(record), digest(record), (time.perf_counter()-start)*1000, engine_ms))
        db.execute("UPDATE runs SET state=?,state_hash=?,tick=? WHERE id=?", (canonical(state), digest(state), state["tick"], run_id))
        for d in record["decisions"]:
            db.execute("INSERT OR IGNORE INTO action_ids VALUES(?,?)", (run_id, d["action"]["id"]))
            for did in (d.get("model") or {}).get("decision_ids", []):
                # consumed in the same transaction that commits the tick (atomic linkage)
                db.execute("UPDATE model_calls SET status='consumed', consumed_tick=? WHERE decision_id=? AND status='completed'", (state["tick"], did))
        if state["tick"] % state["config"]["snapshot_every"] == 0:
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)", (run_id, state["tick"], canonical(state), digest(state), "periodic"))

    def require_writable(self, run_id: str) -> None:
        with self.connection() as db:
            compatible(json.loads(self._row(db, run_id)["manifest"]))

    def checkpoint(self, run_id: str) -> JSON:
        with self.connection() as db, db:
            db.execute("BEGIN IMMEDIATE")
            state = self._decode(self._row(db, run_id), continuing=True)
            db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)", (run_id, state["tick"], canonical(state), digest(state), "manual"))
            return {"tick": state["tick"], "state_hash": digest(state)}

    def checkpoints(self, run_id: str) -> list[JSON]:
        with self.connection() as db:
            self._row(db, run_id)
            return [dict(r) for r in db.execute("SELECT tick,state_hash,label FROM snapshots WHERE run_id=? ORDER BY tick", (run_id,))]

    def _replay(self, db, run_id: str, tick: int) -> JSON:
        row = self._row(db, run_id)
        manifest = json.loads(row["manifest"])
        readable(manifest)
        if not manifest["origin_tick"] <= tick <= row["tick"]:
            raise ValueError("tick outside committed history")
        snap = db.execute("SELECT * FROM snapshots WHERE run_id=? AND tick<=? ORDER BY tick DESC LIMIT 1", (run_id, tick)).fetchone()
        state = json.loads(snap["state"])
        if digest(state) != snap["state_hash"]:
            raise ValueError("snapshot hash mismatch")
        previous = db.execute("SELECT record_hash,record FROM ticks WHERE run_id=? AND tick=?", (run_id, snap["tick"])).fetchone()
        chain = previous["record_hash"] if previous else manifest["initial_hash"]
        if previous and (digest(json.loads(previous["record"])) != chain or json.loads(previous["record"])["state_hash"] != digest(state)):
            raise ValueError("snapshot does not match history")
        if not previous and digest(state) != manifest["initial_hash"]:
            raise ValueError("origin snapshot mismatch")
        for r in db.execute("SELECT * FROM ticks WHERE run_id=? AND tick>? AND tick<=? ORDER BY tick", (run_id, snap["tick"], tick)):
            record = json.loads(r["record"])
            if digest(record) != r["record_hash"] or record["previous_record_hash"] != chain or record["before_hash"] != digest(state) or record["tick"] != state["tick"] + 1:
                raise ValueError("corrupt or incomplete transition history")
            state = apply_delta(state, record["delta"])
            if digest(state) != record["state_hash"]:
                raise ValueError("replay state hash mismatch")
            chain = r["record_hash"]
        if state["tick"] != tick:
            raise ValueError("incomplete replay")
        validate_state(state)
        return state

    def replay(self, run_id: str, tick: int) -> JSON:
        with self.connection() as db:
            return self._replay(db, run_id, tick)

    FORK_INTERVENTIONS = {"removal", "removal_tick", "succession", "successor_role", "successor_access", "invention", "max_ticks", "teaching"}

    def fork(self, run_id: str, tick: int, intervention: JSON | None = None, label: str | None = None, model_profile=None) -> str:
        """A distinct continuation from a committed tick. An intervention may change only lifecycle, invention
        and run-length settings; the parent history is untouched and the change is recorded in the manifest."""
        with self.connection() as db:
            compatible(json.loads(self._row(db, run_id)["manifest"]))
        state = self.replay(run_id, tick)
        parent = {"run_id": run_id, "tick": tick, "state_hash": digest(state)}
        intervention = dict(intervention or {})
        if intervention:
            unknown = set(intervention) - self.FORK_INTERVENTIONS
            if unknown:
                raise ValueError(f"fork intervention may not change: {sorted(unknown)}")
            if "removal_tick" in intervention and intervention["removal_tick"] <= tick:
                raise ValueError("removal must be scheduled after the fork tick")
            config = Scenario.model_validate({**state["config"], **intervention})
            state["config"] = config.model_dump()
            parent.update(intervention=intervention, label=label)
        elif label:
            parent["label"] = label
        return self.create(Scenario.model_validate(state["config"]), state, parent, model_profile=model_profile)

    def events(self, run_id: str, through: int | None = None, limit: int = 100) -> list[JSON]:
        with self.connection() as db:
            row = self._row(db, run_id)
            records = db.execute("SELECT record FROM ticks WHERE run_id=? AND tick<=? ORDER BY tick DESC LIMIT ?", (run_id, through if through is not None else row["tick"], min(limit, 200)))
            result = []
            for r in records:
                result.extend(reversed(json.loads(r[0])["events"]))
                if len(result) >= limit:
                    break
            return result[:limit]

    def diagnostics(self, run_id: str, through: int | None = None, ticks: int = 40) -> list[JSON]:
        """Recent controller search diagnostics (stored with decisions in tick records, never in world state)."""
        with self.connection() as db:
            row = self._row(db, run_id)
            records = db.execute("SELECT record FROM ticks WHERE run_id=? AND tick<=? ORDER BY tick DESC LIMIT ?",
                                 (run_id, through if through is not None else row["tick"], min(ticks, 200)))
            result = []
            for r in records:
                record = json.loads(r[0])
                result.extend({"tick": record["tick"], "agent": d["action"]["agent"], "action": d["action"]["kind"], **d["diagnostic"]}
                              for d in record["decisions"] if d.get("diagnostic"))
            return result

    def export(self, run_id: str) -> JSON:
        with self.connection() as db:
            db.execute("BEGIN")
            row = self._row(db, run_id)
            state = self._decode(row)
            profile_row = db.execute("SELECT profile FROM model_profiles WHERE run_id=?", (run_id,)).fetchone()
            payload = {"format": "genesis-export-1", "manifest": json.loads(row["manifest"]),
                       "initial": json.loads(row["initial"]), "state": state,
                       "ticks": [{"record": json.loads(r["record"]), "record_hash": r["record_hash"], "elapsed_ms": r["elapsed_ms"], "engine_ms": r["engine_ms"]} for r in db.execute("SELECT * FROM ticks WHERE run_id=? ORDER BY tick", (run_id,))],
                       "snapshots": [{"state": json.loads(r["state"]), "state_hash": r["state_hash"], "label": r["label"]} for r in db.execute("SELECT * FROM snapshots WHERE run_id=? ORDER BY tick", (run_id,))]}
            if profile_row:
                payload["model_profile"] = json.loads(profile_row[0])
                payload["model_ledger"] = model_ledger.export_rows(db, run_id)
            payload["checksum"] = digest(payload)
            return payload

    def import_run(self, payload: JSON) -> str:
        body = {k: v for k, v in payload.items() if k != "checksum"}
        if digest(body) != payload.get("checksum") or body.get("format") != "genesis-export-1":
            raise ValueError("export checksum/format mismatch")
        manifest = deepcopy(body["manifest"])
        compatible(manifest)
        state = body["initial"]
        if digest(state) != manifest["initial_hash"] or state["config"] != manifest["config"]:
            raise ValueError("initial state mismatch")
        chain = digest(state)
        hashes = {state["tick"]: digest(state)}
        for entry in body["ticks"]:
            r = entry["record"]
            if digest(r) != entry["record_hash"] or r["previous_record_hash"] != chain or r["before_hash"] != digest(state) or r["tick"] != state["tick"] + 1:
                raise ValueError("invalid imported transition")
            state = apply_delta(state, r["delta"])
            if digest(state) != r["state_hash"]:
                raise ValueError("imported state hash mismatch")
            validate_state(state)
            hashes[state["tick"]] = digest(state)
            chain = entry["record_hash"]
        if digest(state) != digest(body["state"]):
            raise ValueError("export final state mismatch")
        for snap in body["snapshots"]:
            if digest(snap["state"]) != snap["state_hash"] or hashes.get(snap["state"]["tick"]) != snap["state_hash"]:
                raise ValueError("corrupt imported snapshot")
        original_id = manifest["id"]
        manifest.update(id=uuid.uuid4().hex[:12], imported_from=original_id)
        rid = manifest["id"]
        with self.connection() as db, db:
            self._insert_run(db, manifest, body["initial"])
            for entry in body["ticks"]:
                r = entry["record"]
                db.execute("INSERT INTO ticks VALUES(?,?,?,?,?,?)", (rid, r["tick"], canonical(r), entry["record_hash"], entry["elapsed_ms"], entry["engine_ms"]))
                for d in r["decisions"]:
                    db.execute("INSERT OR IGNORE INTO action_ids VALUES(?,?)", (rid, d["action"]["id"]))
            for snap in body["snapshots"]:
                db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)", (rid, snap["state"]["tick"], canonical(snap["state"]), snap["state_hash"], snap["label"]))
            self._artifacts(db, state)
            db.execute("UPDATE runs SET state=?,state_hash=?,tick=? WHERE id=?", (canonical(state), digest(state), state["tick"], rid))
        return rid

    def telemetry(self, run_id: str) -> JSON:
        with self.connection() as db:
            row = db.execute("SELECT COUNT(*) n,AVG(elapsed_ms) avg_ms,MAX(elapsed_ms) max_ms,AVG(engine_ms) engine_ms,SUM(LENGTH(record)) bytes FROM ticks WHERE run_id=?", (run_id,)).fetchone()
            return {**dict(row), "database_bytes": self.path.stat().st_size,
                    "timing_note": "elapsed_ms excludes final SQLite commit/fsync; CLI benchmark reports total wall time"}


def request_id_seen(store: "Store", run_id: str, request_id: str | None) -> bool:
    if not request_id:
        return False
    with store.connection() as db:
        return db.execute("SELECT 1 FROM requests WHERE run_id=? AND key=?", (run_id, request_id)).fetchone() is not None
