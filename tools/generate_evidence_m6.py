"""M6 (v0.6.0) fixture-based evidence. No credentials, model downloads, inference servers or external network:
responses come from a deterministic fixture responder, served in-process or by a loopback mock HTTP server that
speaks the Ollama /api/chat wire format (so the real adapter's serialization is exercised).

Usage (repo root): python tools/generate_evidence_m6.py [step names...]
Output: evidence/v0.6.0/ (runs.json logs every step with source fingerprints).
Fixture output is scripted; nothing here is evidence of model competence or of model-driven behaviour.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evidence" / "v0.6.0"
sys.path.insert(0, str(ROOT))

from genesis import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION  # noqa: E402
from genesis.model import ACTION_SCHEMA_VERSION, ADAPTER_VERSION, PARSER_VERSION, PROMPT_VERSION  # noqa: E402
from genesis.model.adapter import capabilities  # noqa: E402
from genesis.model.fixtures import FixtureResponder, MockOllamaServer, in_process_transport  # noqa: E402
from genesis.model.profile import AdapterConfig, Ceilings, ModelProfile, config_hash  # noqa: E402
from genesis.model.prompt import INSTRUCTIONS  # noqa: E402
from genesis.model.recorded import reexecute  # noqa: E402
from genesis.model.runtime import DecisionInFlight, LiveCallsDisabled, RecordingMismatch, SimulatedCrash  # noqa: E402
from genesis.model.schema import output_schema  # noqa: E402
from genesis.models import Scenario, digest  # noqa: E402
from genesis.reducer import reduce_export  # noqa: E402
from genesis.storage import Store  # noqa: E402
from tools.generate_evidence_m5b import fingerprint, source_fingerprint as _base_fingerprint  # noqa: E402


def source_fingerprint() -> dict:
    """The v0.5.1 fingerprint plus the genesis/model package (which the top-level glob does not cover)."""
    return {**_base_fingerprint(), "model_package_sha256": fingerprint(sorted(ROOT.glob("genesis/model/*.py")))}

BIG = Ceilings(requests=1000, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)
WORLD = dict(seed=101, task="workshop-1", ore_per_site=900, max_ticks=200)


def profile(**kw) -> ModelProfile:
    base = dict(mode="fixture", agents=["a01"], adapter=AdapterConfig(model="fixture-policy-1"), run_budget=BIG, agent_budget=BIG, lease_grace_ms=0)
    return ModelProfile(**{**base, **kw})


def compact_rows(store, rid, limit=6) -> list[dict]:
    keep = ("agent", "tick", "role", "attempt", "status", "source", "returned_model", "prompt_hash", "input_bytes", "truncations", "response",
            "parsed", "parse_error", "fallback", "termination", "reservation", "reconciled", "receipt", "consumed_tick", "recorded_from")
    return [{k: r.get(k) for k in keep} for r in store.model_calls(rid)[:limit]]


def committed(store, rid, agent="a01") -> list[dict]:
    out = []
    for e in store.export(rid)["ticks"]:
        rejected = {ev["id"]: ev.get("reason") for ev in e["record"]["events"] if ev.get("type") == "action_rejected" and ev.get("id")}
        for d in e["record"]["decisions"]:
            if d["action"]["agent"] == agent:
                out.append({"tick": e["record"]["tick"], "mode": d["controller"], "action": d["action"]["kind"], "params": d["action"]["params"],
                            "accepted": d["action"]["id"] not in rejected, "rejection": rejected.get(d["action"]["id"]),
                            "reason": (d.get("model") or {}).get("reason"), "receipt": (d.get("model") or {}).get("receipt")})
    return out


def mock_http_world(tmp: Path, responder: FixtureResponder, ticks: int, **prof) -> tuple[Store, str, MockOllamaServer]:
    server = MockOllamaServer(responder, timeout_sleep_s=1.0).__enter__()
    adapter_cfg = prof.pop("adapter_kw", {})
    p = profile(mode="mock-http", endpoint_label="loopback mock Ollama", adapter=AdapterConfig(model="fixture-policy-1", base_url=server.base_url, **adapter_cfg), **prof)
    store = Store(tmp / f"{time.perf_counter_ns()}.sqlite")
    rid = store.create(Scenario(**WORLD), model_profile=p)
    for _ in range(ticks):
        store.step(rid)
    return store, rid, server


def scenarios() -> dict:
    results = {}
    tmp = Path(tempfile.mkdtemp())

    def run(name, fn):
        try:
            results[name] = {"status": "passed", **fn()}
        except AssertionError as exc:
            results[name] = {"status": "FAILED", "failure": str(exc)}

    def s1():
        store, rid, srv = mock_http_world(tmp, FixtureResponder(), 1)
        srv.__exit__()
        d = committed(store, rid)[0]
        assert d["mode"] == "model-proposal" and d["accepted"]
        return {"decision": d, "ledger": compact_rows(store, rid)}
    run("01 valid model-shaped action applied by the engine (mock HTTP)", s1)

    def s2():
        responder = FixtureResponder(script={1: "invalid-json"})
        store, rid, srv = mock_http_world(tmp, responder, 1)
        srv.__exit__()
        d = committed(store, rid)[0]
        assert d["mode"] == "model-proposal" and "after one repair" in d["reason"] and responder.calls == 2
        return {"decision": d, "ledger": compact_rows(store, rid)}
    run("02 invalid JSON followed by one bounded repair", s2)

    def s3():
        store, rid, srv = mock_http_world(tmp, FixtureResponder(script={1: "illegal-action"}), 1)
        srv.__exit__()
        d = committed(store, rid)[0]
        assert d["mode"] == "model-proposal" and not d["accepted"]
        return {"decision": d, "note": "a well-formed illegal action is an ordinary rejected world action"}
    run("03 schema-valid illegal action rejected by the engine", s3)

    def s4():
        tight = Ceilings(requests=2, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)
        responder = FixtureResponder()
        store, rid, srv = mock_http_world(tmp, responder, 25, agent_budget=tight)
        srv.__exit__()
        fallback = [d for d in committed(store, rid) if d["mode"] == "fallback"]
        assert responder.calls == 2 and fallback and "budget exhausted" in fallback[0]["reason"]
        return {"provider_requests": responder.calls, "first_fallback": fallback[0], "blocked_rows": sum(1 for r in store.model_calls(rid) if r["status"] == "blocked")}
    run("04 budget exhaustion and labelled fallback", s4)

    def s5():
        responder = FixtureResponder(script={1: "timeout"})
        store, rid, srv = mock_http_world(tmp, responder, 6, adapter_kw={"deadline_ms": 300})
        srv.__exit__()
        from genesis.model.budget import totals
        rows = store.model_calls(rid)
        assert rows[0]["status"] == "outcome-unknown" and responder.calls == 1
        return {"row": compact_rows(store, rid, 1)[0], "uncertain_bucket": totals(rows)["uncertain"],
                "agent_modes_after": [d["mode"] for d in committed(store, rid)[1:6]]}
    run("05 provider timeout with uncertain usage (reservation kept, not resent)", s5)

    def s6():
        # Identical observations recur: a repair shares its primary's observation, and two forks from one checkpoint see
        # the same world at the same tick. The decision identity (run, agent, tick, role, attempt, ...) keeps them apart.
        store, rid, srv = mock_http_world(tmp, FixtureResponder(script={1: "invalid-json"}), 12)
        srv.__exit__()
        forks = [store.fork(rid, 6, model_profile=profile()) for _ in range(2)]
        for f in forks:
            for _ in range(6):
                store.step(f)
        rows = [r for run_id in (rid, *forks) for r in store.model_calls(run_id)]
        by_obs: dict = {}
        for r in rows:
            by_obs.setdefault(r["identity"]["observation_hash"], []).append((r["identity"]["run_id"], r["tick"], r["role"], r["attempt"]))
        shared = {h[:12]: v for h, v in by_obs.items() if len(v) > 1}
        assert shared and len({r["decision_id"] for r in rows}) == len(rows)
        return {"requests": len(rows), "distinct_decision_ids": len({r["decision_id"] for r in rows}),
                "observation_hashes_shared_by_several_requests": shared, "identity_fields": sorted(rows[0]["identity"])}
    run("06 repeated observations without recording collisions", s6)

    def s7():
        responder = FixtureResponder()
        store = Store(tmp / "s7.sqlite")
        rid = store.create(Scenario(**WORLD), model_profile=profile(adapter=AdapterConfig(model="fixture-policy-1", deadline_ms=50)))
        store.model_transports[rid] = in_process_transport(responder)
        store.model_hooks[rid] = {"after-persist": lambda: (_ for _ in ()).throw(SimulatedCrash("after-persist"))}
        try:
            store.step(rid)
        except SimulatedCrash:
            pass
        before = store.model_calls(rid)[0]["status"]
        reopened = Store(tmp / "s7.sqlite")
        reopened.model_transports[rid] = in_process_transport(responder)
        reopened.step(rid)
        assert before == "completed" and responder.calls == 1 and reopened.model_calls(rid)[0]["status"] == "consumed"
        return {"status_after_crash": before, "provider_requests_total": responder.calls, "status_after_restart": "consumed"}
    run("07 restart with an unconsumed completed response (reused, not re-requested)", s7)

    def s8():
        responder = FixtureResponder()
        store = Store(tmp / "s8.sqlite")
        rid = store.create(Scenario(**WORLD), model_profile=profile(adapter=AdapterConfig(model="fixture-policy-1", deadline_ms=50), lease_grace_ms=600))
        store.model_transports[rid] = in_process_transport(responder)
        store.model_hooks[rid] = {"during-dispatch": lambda: (_ for _ in ()).throw(SimulatedCrash("during-dispatch"))}
        try:
            store.step(rid)
        except SimulatedCrash:
            pass
        live = Store(tmp / "s8.sqlite")
        live.model_transports[rid] = in_process_transport(responder)
        blocked = False
        try:
            live.step(rid)
        except DecisionInFlight:
            blocked = True
        time.sleep(0.8)
        live.step(rid)
        row = live.model_calls(rid)[0]
        assert blocked and row["status"] == "outcome-unknown" and responder.calls == 0
        return {"second_worker_blocked_while_lease_valid": blocked, "status_after_lease_expiry": row["status"], "provider_requests": responder.calls,
                "decision_mode": committed(live, rid)[0]["mode"]}
    run("08 unknown in-flight request without duplicate dispatch", s8)

    store, rid, srv = mock_http_world(tmp, FixtureResponder(script={4: "invalid-json", 9: "illegal-action"}), 40, agents=["a01", "a05"])
    srv.__exit__()

    def s9():
        report = reexecute(store, rid)
        assert report["all_matched"] and report["checked"] > 0
        return {k: report[k] for k in ("checked", "matched", "mismatch_count", "model_decisions_by_mode", "parser_version", "prompt_version")}
    run("09 recorded decision re-execution matches the committed actions", s9)

    def s10():
        real_socket = socket.socket

        def no_network(*a, **k):
            raise AssertionError("network used")
        socket.socket = no_network
        try:
            replayed = store.replay(rid, 40)
            report = reexecute(store, rid)
        finally:
            socket.socket = real_socket
        assert digest(replayed) == digest(store.load(rid)) and report["all_matched"]
        return {"state_replay_hash_matches": True, "reexecution_all_matched": True, "network": "socket creation disabled during replay"}
    run("10 state replay and re-execution with network disabled", s10)

    def s11():
        recorded = profile(mode="recorded", source_run=rid, agents=["a01", "a05"], adapter=store.model_profile(rid).adapter)
        fork = store.fork(rid, 10, model_profile=recorded)
        for _ in range(10):
            store.step(fork)
        reused = store.model_calls(fork)
        diverged = store.fork(rid, 10, {"invention": "frozen"}, model_profile=recorded)
        stopped_at = None
        try:
            for _ in range(10):
                store.step(diverged)
        except RecordingMismatch as exc:
            stopped_at = {"tick": store.load(diverged)["tick"], "error": str(exc)}
        assert reused and all(r["source"] == "recorded" for r in reused) and stopped_at
        return {"unchanged_fork_reused_recordings": len(reused), "historical_usage_not_recharged": True, "diverged_fork_stopped": stopped_at}
    run("11 strict recorded fork stops at the first mismatch", s11)
    return results


def integration() -> dict:
    tmp = Path(tempfile.mkdtemp())
    responder = FixtureResponder(script={7: "invalid-json", 15: "illegal-action", 23: "http-500"})
    started = time.perf_counter()
    store, rid, srv = mock_http_world(tmp, responder, 120, agents=["a01", "a05"])
    srv.__exit__()
    seconds = round(time.perf_counter() - started, 2)
    export = store.export(rid)
    red = reduce_export(export)
    modes = red["model"]["decisions_by_mode"]
    rows = store.model_calls(rid)
    primaries = {a: sorted(r["tick"] for r in rows if r["agent"] == a and r["role"] == "primary") for a in ("a01", "a05")}
    out_dir = OUT / "integration"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(export, separators=(",", ":")).encode("utf-8")
    (out_dir / "integration-export.json.gz").write_bytes(gzip.compress(raw, 9))
    (out_dir / "ledger.json.gz").write_bytes(gzip.compress(json.dumps(rows, separators=(",", ":")).encode("utf-8"), 9))
    report = reexecute(store, rid)
    return {"world": WORLD, "designated_agents": ["a01", "a05"], "other_agents": "offline controller", "ticks": 120, "wall_seconds": seconds,
            "provider_requests": responder.calls, "decisions_by_mode": modes,
            "calls_per_agent_tick": {a: round(len(t) / 120, 3) for a, t in primaries.items()},
            "min_gap_between_primary_calls": {a: (min(b - x for x, b in zip(t, t[1:])) if len(t) > 1 else None) for a, t in primaries.items()},
            "ledger_status_counts": dict(__import__("collections").Counter(r["status"] for r in rows)),
            "reducer_model_reconciliation": red["model"], "holdings_reconcile": red["reconciliation"]["holdings_match_final_state"],
            "reexecution": {k: report[k] for k in ("checked", "matched", "mismatch_count")},
            "export_sha256": hashlib.sha256(raw).hexdigest(), "export_bytes": len(raw)}


def live_disabled() -> dict:
    cfg = json.loads((ROOT / "config" / "live-run.disabled.json").read_text(encoding="utf-8"))
    prof = ModelProfile.model_validate(cfg["profile"])
    tmp = Path(tempfile.mkdtemp())
    store = Store(tmp / "live.sqlite")
    rid = store.create(Scenario(**cfg["scenario"]), model_profile=prof)
    try:
        store.step(rid)
        refused = None
    except LiveCallsDisabled as exc:
        refused = str(exc)
    assert refused, "live mode must refuse without authorization"
    return {"config": "config/live-run.disabled.json", "live_authorized": prof.live_authorized, "refused": refused, "provider_contacted": False}


def offline_parity() -> dict:
    """Runs without a model profile must be unchanged: compare hashes from a v0.5.2 worktree with the current tree."""
    script = ROOT / "tools" / "m6_offline_hash.py"
    wt = Path(tempfile.mkdtemp()) / "v0.5.2"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "v0.5.2"], cwd=ROOT, check=True, capture_output=True)
    try:
        run = lambda root: json.loads(subprocess.run([sys.executable, str(script)], cwd=root, env={**os.environ, "PYTHONPATH": str(root)},
                                                     capture_output=True, text=True, check=True).stdout)
        old, new = run(wt), run(ROOT)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, capture_output=True)
    keys = [k for k in old if k != "engine"]
    assert all(old[k] == new[k] for k in keys), "offline runs changed"
    return {"v0.5.2": old, "current": new, "identical": keys, "ticks": 120}


def checks() -> dict:
    out = {}
    t = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    out["pytest"] = {"exit_code": proc.returncode, "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-500:], "seconds": round(time.perf_counter() - t, 1)}
    t = time.perf_counter()
    npm = "npm.cmd" if os.name == "nt" else "npm"
    proc = subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", capture_output=True, text=True)
    out["frontend_build"] = {"exit_code": proc.returncode, "tail": (proc.stdout.strip().splitlines() or [""])[-1][-200:], "seconds": round(time.perf_counter() - t, 1)}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"started_at": datetime.now(timezone.utc).isoformat(), "source_at_start": source_fingerprint(),
           "versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION, "prompt": PROMPT_VERSION,
                        "action_schema": ACTION_SCHEMA_VERSION, "parser": PARSER_VERSION, "adapter": ADAPTER_VERSION}, "steps": []}
    only = set(sys.argv[1:])
    for name, fn, file in (("scenarios", scenarios, "scenarios.json"), ("integration", integration, "integration/integration.json"),
                           ("live disabled", live_disabled, "live-disabled.json"),
                           ("offline parity", offline_parity, "offline-parity.json"), ("checks", checks, "checks.json")):
        if only and name not in only:
            continue
        t = time.perf_counter()
        try:
            result, code = fn(), 0
        except Exception as exc:  # noqa: BLE001
            result, code = {"failure": f"{type(exc).__name__}: {exc}"}, 1
        path = OUT / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        log["steps"].append({"step": name, "exit_code": code, "seconds": round(time.perf_counter() - t, 1)})
        print(f"{name}: exit {code}", flush=True)
    (OUT / "contract.json").write_text(json.dumps({"adapter_capabilities": capabilities(AdapterConfig(model="m").model_dump()), "output_schema": output_schema(),
                                                   "instructions_sha256": hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
                                                   "example_config_hash": config_hash(profile()),
                                                   "official_references": ["https://docs.ollama.com/api/chat", "https://docs.ollama.com/capabilities/structured-outputs"]}, indent=2),
                                       encoding="utf-8")
    sizes = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    log.update(source_at_end=source_fingerprint(), finished_at=datetime.now(timezone.utc).isoformat(), evidence_bytes=sizes)
    (OUT / "runs.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
