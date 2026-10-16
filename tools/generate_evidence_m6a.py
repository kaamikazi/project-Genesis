"""v0.6.1 (Gemini adapter) evidence, credential-free. Every Gemini-shaped response comes from a scripted fixture served
in-process or by a loopback mock server speaking the generateContent wire format; the key is a synthetic value set in
this process only. No request leaves 127.0.0.1 and no live inference call is made.

Usage (repo root): python tools/generate_evidence_m6a.py [step names...]
Output: evidence/v0.6.1/
"""
from __future__ import annotations

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
OUT = ROOT / "evidence" / "v0.6.1"
sys.path.insert(0, str(ROOT))
SYNTHETIC_KEY = "synthetic-evidence-key-not-a-secret-0001"
os.environ["GEMINI_API_KEY"] = SYNTHETIC_KEY                   # this process only

from genesis import ENGINE_VERSION  # noqa: E402
from genesis.model import ACTION_SCHEMA_VERSION, GEMINI_ADAPTER_VERSION, GEMINI_WIRE_SCHEMA_VERSION, PARSER_VERSION, PROMPT_VERSION  # noqa: E402
from genesis.model import gemini  # noqa: E402
from genesis.model.budget import totals  # noqa: E402
from genesis.model.fixtures import GeminiFixtureResponder, MockGeminiServer, gemini_in_process_transport  # noqa: E402
from genesis.model.profile import GEMINI_ORIGIN, AdapterConfig, Ceilings, ModelProfile, OperatorConfirmations  # noqa: E402
from genesis.model.prompt import build_messages  # noqa: E402
from genesis.model.recorded import reexecute  # noqa: E402
from genesis.model.runtime import DecisionInFlight, LiveCallsDisabled, RecordingMismatch, SimulatedCrash  # noqa: E402
from genesis.model.transport import CredentialMissing, GeminiTransport, NotDelivered  # noqa: E402
from genesis.models import Scenario, digest  # noqa: E402
from genesis.reducer import reduce_export  # noqa: E402
from genesis.storage import Store  # noqa: E402
from genesis.world import LocalObservations, new_world  # noqa: E402
from tools.generate_evidence_m6 import source_fingerprint  # noqa: E402

ACCESSED = "2026-10-17"
REFERENCES = ["https://ai.google.dev/gemini-api/docs/models", "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite",
              "https://ai.google.dev/gemini-api/docs/api-key", "https://ai.google.dev/api/generate-content",
              "https://ai.google.dev/gemini-api/docs/structured-output", "https://ai.google.dev/gemini-api/docs/thinking",
              "https://ai.google.dev/gemini-api/docs/pricing", "https://ai.google.dev/gemini-api/docs/rate-limits"]
BIG = Ceilings(requests=500, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)
WORLD = dict(seed=101, task="workshop-1", ore_per_site=900)
MODEL = "gemini-3.5-flash-lite"


def adapter(**kw) -> AdapterConfig:
    return AdapterConfig(**{**dict(provider="gemini", base_url="http://127.0.0.1:9", model=MODEL, thinking_level="minimal", request_logging=False,
                                   max_output_tokens=1024), **kw})


def profile(**kw) -> ModelProfile:
    return ModelProfile(**{**dict(mode="fixture", agents=["a01"], adapter=adapter(), run_budget=BIG, agent_budget=BIG, lease_grace_ms=0), **kw})


def leaks(store, rid) -> bool:
    with store.connection() as db:
        dump = "\n".join(str(tuple(r)) for t in ("model_calls", "model_profiles", "ticks", "runs") for r in db.execute(f"SELECT * FROM {t}"))
    return SYNTHETIC_KEY in dump or SYNTHETIC_KEY in json.dumps(store.export(rid)) or "FIXTURE THOUGHT" in dump


def contract() -> dict:
    obs = LocalObservations().build(new_world(Scenario(**WORLD)), "a01")
    messages, meta = build_messages(obs, 16000)
    url, body, headers = gemini.build_request(messages, adapter(base_url=GEMINI_ORIGIN).model_dump())
    req = json.loads(body)
    req["systemInstruction"]["parts"][0]["text"] = f"<{len(messages[0]['content'])} chars: versioned instructions {PROMPT_VERSION}>"
    req["contents"][0]["parts"][0]["text"] = f"<{meta['input_bytes'] - len(messages[0]['content'].encode())} bytes: restricted observation data block>"
    smoke = json.loads(subprocess.run([sys.executable, "tools/gemini_smoke.py", "show", "--config", "config/gemini-smoke.disabled.json"], cwd=ROOT,
                                      capture_output=True, text=True, check=True, env={**os.environ, "GEMINI_API_KEY": ""}).stdout)
    return {"accessed": ACCESSED, "official_references": REFERENCES, "endpoint": url, "api_version": gemini.API_VERSION, "dependency": "Python standard library urllib (no SDK; no hidden retries)",
            "headers_sent": sorted(headers) + ["x-goog-api-key (added by GeminiTransport at dispatch; never stored)"],
            "request_envelope_example": req, "wire_schema": gemini.wire_schema(), "capabilities": gemini.capabilities(adapter().model_dump()),
            "versions": {"adapter": GEMINI_ADAPTER_VERSION, "wire_schema": GEMINI_WIRE_SCHEMA_VERSION, "prompt": PROMPT_VERSION,
                         "action_schema": ACTION_SCHEMA_VERSION, "parser": PARSER_VERSION, "engine": ENGINE_VERSION},
            "smoke_template_show": smoke}


FAULTS = ["(none)", "thought-parts", "invalid-json", "illegal-action", "extra-field", "empty-text", "blocked-prompt", "no-candidates", "two-candidates",
          "safety", "max-tokens", "non-text-part", "no-usage", "inconsistent-usage", "nonfinite-usage", "overshoot", "secret-echo",
          "http-500", "http-400-schema", "http-429", "redirect", "timeout"]


def fault_matrix() -> dict:
    """One decision per fault through real loopback HTTP (header path, no-redirect opener, classification)."""
    tmp = Path(tempfile.mkdtemp())
    out = {}
    for fault in FAULTS:
        responder = GeminiFixtureResponder(script={} if fault == "(none)" else {1: fault})
        with MockGeminiServer(GeminiFixtureResponder()) as elsewhere:
            with MockGeminiServer(responder, timeout_sleep_s=1.0, redirect_target=elsewhere.base_url + f"/v1beta/models/{MODEL}:generateContent") as srv:
                store = Store(tmp / f"{fault}.sqlite")
                rid = store.create(Scenario(**WORLD), model_profile=profile(mode="mock-http", adapter=adapter(base_url=srv.base_url, deadline_ms=400)))
                for _ in range(6 if fault == "http-429" else 1):
                    store.step(rid)
        rows = store.model_calls(rid)
        first = rows[0]
        d = [x for e in store.export(rid)["ticks"] for x in e["record"]["decisions"] if x["action"]["agent"] == "a01"][0]
        out[fault] = {"provider_requests": responder.calls, "rows": [(r["role"], r["status"]) for r in rows[:3]],
                      "first_row": {"status": first["status"], "parse_error": first["parse_error"], "termination": first["termination"],
                                    "usage_basis": (first["reconciled"] or {}).get("basis", "reservation held")[:60],
                                    "thinking_tokens": (first["reconciled"] or {}).get("thinking_tokens"),
                                    "repairable": (first["usage"] or {}).get("repairable"), "halt": (first["usage"] or {}).get("halt"),
                                    "reservation_exceeded": (first["usage"] or {}).get("reservation_exceeded")},
                      "decision_mode": d["controller"], "decision_reason": (d.get("model") or {}).get("reason"),
                      "key_header_sent": all(s["key_header"] == SYNTHETIC_KEY for s in srv.seen), "redirect_target_contacted": bool(elsewhere.seen),
                      "key_or_thoughts_in_records": leaks(store, rid)}
        if fault == "http-429":
            out[fault]["later_rows"] = [r["fallback"] for r in rows[1:3]]
    assert not any(v["key_or_thoughts_in_records"] for v in out.values())
    assert not out["redirect"]["redirect_target_contacted"]
    return out


def guards() -> dict:
    tmp = Path(tempfile.mkdtemp())
    res = {}
    saved = os.environ.pop("GEMINI_API_KEY")
    os.environ["UNRELATED_SECRET_TOKEN"] = "unrelated-secret-value-do-not-print"
    try:
        with MockGeminiServer(GeminiFixtureResponder()) as srv:
            store = Store(tmp / "nokey.sqlite")
            rid = store.create(Scenario(**WORLD), model_profile=profile(mode="mock-http", adapter=adapter(base_url=srv.base_url)))
            try:
                store.step(rid)
            except CredentialMissing as exc:
                res["missing_key"] = {"error": str(exc), "contains_env_values": "unrelated-secret" in str(exc), "ledger_rows": len(store.model_calls(rid)),
                                      "requests_received": len(srv.seen)}
    finally:
        os.environ["GEMINI_API_KEY"] = saved
        os.environ.pop("UNRELATED_SECRET_TOKEN")
    ok = OperatorConfirmations(free_tier_billing_disabled=True, model_available=True, quota_sufficient=True, simulation_data_only=True,
                               confirmed_by="evidence", confirmed_on=ACCESSED)
    live = dict(mode="live", adapter=adapter(base_url=GEMINI_ORIGIN), live_authorized=True, run_deadline_s=900, operator_confirmations=ok)
    cases = {"env switch unset": (live, False), "live_authorized false": ({**live, "live_authorized": False}, True),
             "confirmations missing": ({**live, "operator_confirmations": OperatorConfirmations()}, True),
             "no run deadline": ({**live, "run_deadline_s": None}, True),
             "disabled smoke template": (json.loads((ROOT / "config/gemini-smoke.disabled.json").read_text(encoding="utf-8"))["profile"], True)}
    original_send = GeminiTransport.send
    GeminiTransport.send = lambda *a, **k: (_ for _ in ()).throw(AssertionError("live send attempted"))
    try:
        refusals = {}
        for name, (kw, flag) in cases.items():
            os.environ["GENESIS_LIVE_MODEL_CALLS"] = "1" if flag else "0"
            p = ModelProfile.model_validate(kw) if name == "disabled smoke template" else profile(**kw)
            store = Store(tmp / f"{time.perf_counter_ns()}.sqlite")
            rid = store.create(Scenario(**WORLD), model_profile=p)
            try:
                store.step(rid)
                refusals[name] = "NOT REFUSED"
            except (LiveCallsDisabled, CredentialMissing) as exc:
                refusals[name] = str(exc)
        res["live_guard_refusals"] = refusals
    finally:
        GeminiTransport.send = original_send
        os.environ.pop("GENESIS_LIVE_MODEL_CALLS", None)
    prod = GeminiTransport("live")
    pinned = {}
    for url in ("https://generativelanguage.googleapis.com.evil.example/v1beta/models/m:generateContent",
                f"{GEMINI_ORIGIN}/v1beta/models/m:generateContent?key=x", "http://generativelanguage.googleapis.com/v1beta/models/m:generateContent",
                f"{GEMINI_ORIGIN}/upload/v1beta/files"):
        try:
            prod.send(url, b"{}", {}, 1, 100)
            pinned[url] = "SENT"
        except NotDelivered as exc:
            pinned[url] = str(exc)
    res["origin_pinning"] = pinned
    assert all(v != "NOT REFUSED" for v in res["live_guard_refusals"].values()) and all(v != "SENT" for v in pinned.values())
    return res


def recovery() -> dict:
    tmp = Path(tempfile.mkdtemp())
    res = {}
    responder = GeminiFixtureResponder()
    store = Store(tmp / "crash.sqlite")
    rid = store.create(Scenario(**WORLD), model_profile=profile(adapter=adapter(deadline_ms=50), lease_grace_ms=600))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    store.model_hooks[rid] = {"during-dispatch": lambda: (_ for _ in ()).throw(SimulatedCrash("x"))}
    try:
        store.step(rid)
    except SimulatedCrash:
        pass
    other = Store(tmp / "crash.sqlite")
    other.model_transports[rid] = gemini_in_process_transport(responder)
    blocked = False
    try:
        other.step(rid)
    except DecisionInFlight:
        blocked = True
    time.sleep(0.8)
    other.step(rid)
    res["crash_after_possible_dispatch"] = {"second_worker_blocked": blocked, "status": other.model_calls(rid)[0]["status"],
                                            "resends": responder.calls, "uncertain_bucket": totals(other.model_calls(rid))["uncertain"]}
    responder = GeminiFixtureResponder()
    store = Store(tmp / "persist.sqlite")
    rid = store.create(Scenario(**WORLD), model_profile=profile(adapter=adapter(deadline_ms=50)))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    store.model_hooks[rid] = {"after-persist": lambda: (_ for _ in ()).throw(SimulatedCrash("x"))}
    try:
        store.step(rid)
    except SimulatedCrash:
        pass
    again = Store(tmp / "persist.sqlite")
    again.model_transports[rid] = gemini_in_process_transport(responder)
    again.step(rid)
    res["saved_response_reuse"] = {"provider_requests": responder.calls, "status_after_restart": again.model_calls(rid)[0]["status"]}
    responder = GeminiFixtureResponder(script={2: "empty-text", 5: "invalid-json", 8: "safety", 11: "thought-parts"})
    store = Store(tmp / "main.sqlite")
    rid = store.create(Scenario(**WORLD), model_profile=profile(agents=["a01", "a05"]))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    for _ in range(60):
        store.step(rid)
    forks = [store.fork(rid, 30, model_profile=profile(agents=["a01", "a05"])) for _ in range(2)]
    for f in forks:
        store.model_transports[f] = gemini_in_process_transport(GeminiFixtureResponder())
        store.step(f)
    rows = [r for x in (rid, *forks) for r in store.model_calls(x)]
    hashes = [r["identity"]["observation_hash"] for r in rows]
    res["repeated_observations"] = {"requests": len(rows), "distinct_decision_ids": len({r["decision_id"] for r in rows}),
                                    "requests_sharing_an_observation_hash": len(hashes) - len(set(hashes))}
    real = socket.socket
    socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used"))
    try:
        replay_ok = digest(store.replay(rid, 60)) == digest(store.load(rid))
        rex = reexecute(store, rid)
    finally:
        socket.socket = real
    red = reduce_export(store.export(rid))["model"]
    res["replay_network_disabled"] = {"state_replay_hash_matches": replay_ok, "reexecution": {k: rex[k] for k in ("checked", "matched", "mismatch_count")},
                                      "decisions_by_mode": red["decisions_by_mode"], "reducer_reconciled": red["reconciled"],
                                      "committed_usage": totals(store.model_calls(rid))["committed"],
                                      "thinking_tokens": sum(int((r["reconciled"] or {}).get("thinking_tokens") or 0) for r in store.model_calls(rid))}
    recorded = profile(mode="recorded", source_run=rid, agents=["a01", "a05"])
    fork = store.fork(rid, 30, model_profile=recorded)
    for _ in range(10):
        store.step(fork)
    diverged = store.fork(rid, 30, {"invention": "frozen"}, model_profile=recorded)
    stopped = None
    try:
        for _ in range(10):
            store.step(diverged)
    except RecordingMismatch as exc:
        stopped = {"tick": store.load(diverged)["tick"], "error": str(exc)}
    res["recorded_fork"] = {"reused_rows": len(store.model_calls(fork)), "new_committed_requests": totals(store.model_calls(fork))["committed"]["requests"],
                            "diverged_fork_stopped": stopped}
    assert res["crash_after_possible_dispatch"]["resends"] == 0 and res["saved_response_reuse"]["provider_requests"] == 1
    assert replay_ok and rex["all_matched"] and red["reconciled"] and stopped
    return res


def rehearsal() -> dict:
    """The exact disabled smoke template (including its 15 s pacing), switched to a loopback mock server."""
    db = Path(tempfile.mkdtemp()) / "rehearsal.sqlite"
    proc = subprocess.run([sys.executable, "tools/gemini_smoke.py", "rehearse", "--config", "config/gemini-smoke.disabled.json", "--db", str(db)],
                          cwd=ROOT, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    out.pop("report_path", None)
    return out


def offline_parity() -> dict:
    script = ROOT / "tools" / "m6_offline_hash.py"
    wt = Path(tempfile.mkdtemp()) / "v0.6.0"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "v0.6.0"], cwd=ROOT, check=True, capture_output=True)
    try:
        def run(root):
            return json.loads(subprocess.run([sys.executable, str(script)], cwd=root, env={**os.environ, "PYTHONPATH": str(root)},
                                             capture_output=True, text=True, check=True).stdout)
        old, new = run(wt), run(ROOT)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, capture_output=True)
    keys = [k for k in old if k != "engine"]
    assert all(old[k] == new[k] for k in keys)
    return {"v0.6.0": old, "current": new, "identical": keys}


def checks() -> dict:
    out = {}
    t = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    out["pytest"] = {"exit_code": proc.returncode, "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:], "seconds": round(time.perf_counter() - t, 1)}
    proc = subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "build"], cwd=ROOT / "frontend", capture_output=True, text=True)
    out["frontend_build"] = {"exit_code": proc.returncode, "tail": (proc.stdout.strip().splitlines() or [""])[-1][-200:]}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"started_at": datetime.now(timezone.utc).isoformat(), "source_at_start": source_fingerprint(), "live_inference_calls": 0, "steps": []}
    only = set(sys.argv[1:])
    for name, fn, file in (("contract", contract, "contract.json"), ("fault matrix", fault_matrix, "fault-matrix.json"), ("guards", guards, "guards.json"),
                           ("recovery", recovery, "recovery-replay.json"), ("rehearsal", rehearsal, "smoke-rehearsal.json"),
                           ("offline parity", offline_parity, "offline-parity.json"), ("checks", checks, "checks.json")):
        if only and name not in only:
            continue
        t = time.perf_counter()
        try:
            result, code = fn(), 0
        except Exception as exc:  # noqa: BLE001
            result, code = {"failure": f"{type(exc).__name__}: {exc}"}, 1
        (OUT / file).write_text(json.dumps(result, indent=2), encoding="utf-8")
        log["steps"].append({"step": name, "exit_code": code, "seconds": round(time.perf_counter() - t, 1)})
        print(f"{name}: exit {code}", flush=True)
    log.update(source_at_end=source_fingerprint(), finished_at=datetime.now(timezone.utc).isoformat(),
               evidence_bytes=sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()))
    blob = "\n".join(f.read_text(encoding="utf-8") for f in OUT.glob("*.json"))
    log["synthetic_key_in_evidence"] = SYNTHETIC_KEY in blob
    (OUT / "runs.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
