"""Bounded Gemini smoke run (v0.6.1). Three modes:

  python tools/gemini_smoke.py show     --config PATH
      Validate the profile and print the model, hashes, limits and missing confirmations. Contacts nothing.
  python tools/gemini_smoke.py rehearse --config PATH --db PATH
      Run the same profile against a loopback mock Gemini server with a synthetic key (mode switched to mock-http).
      No network beyond 127.0.0.1. Scripted responses; not model behaviour.
  python tools/gemini_smoke.py live     --config PATH --db PATH --profile-hash HASH
      The single live command. Runs only if every guard passes (live_authorized, GENESIS_LIVE_MODEL_CALLS=1,
      operator confirmations, finite deadline, GEMINI_API_KEY present) and HASH equals the reviewed profile hash.
      The database path must not exist yet: an ended smoke run is never resumed or retried automatically.

Every mode writes a sanitized report (no prompts, responses or keys) next to the database; transcripts stay in the
local SQLite file (data/ is git-ignored).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genesis.models import Scenario, digest  # noqa: E402
from genesis.model.profile import GEMINI_ORIGIN, ModelProfile, config_hash  # noqa: E402

SYNTHETIC_KEY = "synthetic-rehearsal-key-not-a-secret"


def load(path: str) -> tuple[Scenario, ModelProfile, int]:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    profile = ModelProfile.model_validate(cfg["profile"])
    if profile.adapter.provider != "gemini":
        raise SystemExit("this launcher is for Gemini profiles only")
    return Scenario(**cfg["scenario"]), profile, int(cfg.get("ticks", 40))


def describe(profile: ModelProfile, ticks: int) -> dict:
    a = profile.adapter
    oc = profile.operator_confirmations
    return {"model": a.model, "provider": a.provider, "origin": a.base_url, "mode": profile.mode, "agents": profile.agents, "ticks": ticks,
            "profile_hash": digest(profile.model_dump()), "config_hash": config_hash(profile),
            "limits": {"run_budget": profile.run_budget.model_dump(), "agent_budget": profile.agent_budget.model_dump(),
                       "max_output_tokens_per_request": a.max_output_tokens, "max_input_bytes_per_decision": a.max_input_bytes,
                       "deadline_ms_per_request": a.deadline_ms, "run_deadline_s": profile.run_deadline_s, "min_dispatch_interval_s": a.min_dispatch_interval_s,
                       "min_interval_ticks": profile.scheduler.min_interval, "concurrency": profile.concurrency, "repair_limit": profile.repair_limit,
                       "thinking_level": a.thinking_level, "request_logging": a.request_logging},
            "live_authorized": profile.live_authorized, "paid": profile.paid,
            "missing_confirmations": oc.missing() if oc else ["operator_confirmations"],
            "key_env_present": bool(os.environ.get("GEMINI_API_KEY", "").strip())}


def report(store, run_id: str, started: float, stop: str | None) -> dict:
    from genesis.model.budget import totals
    from genesis.model.recorded import reexecute
    from genesis.reducer import reduce_export
    export = store.export(run_id)
    profile = store.model_profile(run_id)
    decisions = []
    for e in export["ticks"]:
        rejected = {ev["id"]: ev.get("reason") for ev in e["record"]["events"] if ev.get("type") == "action_rejected" and ev.get("id")}
        for d in e["record"]["decisions"]:
            if d["action"]["agent"] in profile.agents:
                decisions.append({"tick": e["record"]["tick"], "mode": d["controller"], "kind": d["action"]["kind"],
                                  "accepted": d["action"]["id"] not in rejected, "rejection": rejected.get(d["action"]["id"]),
                                  "reason": (d.get("model") or {}).get("reason")})
    rows = store.model_calls(run_id)
    lat = [r["latency_ms"] for r in store.model_latencies(run_id)]
    model_made = [d for d in decisions if d["mode"] in ("model-proposal", "model-intent-execution")]
    red = reduce_export(export)
    t = totals(rows)
    return {"run_id": run_id, "profile_hash": digest(profile.model_dump()), "config_hash": config_hash(profile), "source": profile.mode,
            "ticks_committed": export["ticks"][-1]["record"]["tick"] if export["ticks"] else 0, "wall_seconds": round(time.time() - started, 1),
            "stopped_early": stop, "decisions_by_mode": dict(Counter(d["mode"] for d in decisions)),
            "model_actions": {"accepted": sum(d["accepted"] for d in model_made), "rejected": sum(not d["accepted"] for d in model_made),
                              "rejections": dict(Counter(d["rejection"] for d in model_made if not d["accepted"]))},
            "fallbacks": [{"tick": d["tick"], "reason": d["reason"]} for d in decisions if d["mode"] == "fallback"][:20],
            "requests": {"total_rows": len(rows), "by_status": dict(Counter(r["status"] for r in rows)),
                         "repairs": sum(1 for r in rows if r["role"] == "repair"),
                         "parse_or_content_errors": sum(1 for r in rows if r.get("parse_error")),
                         "finish_reasons": dict(Counter((r.get("usage") or {}).get("finish_reason") for r in rows if r.get("usage"))),
                         "quota_events": sum(1 for r in rows if (r.get("usage") or {}).get("halt") == "quota"),
                         "reservation_exceeded": sum(1 for r in rows if (r.get("usage") or {}).get("reservation_exceeded")),
                         "returned_models": sorted({r["returned_model"] for r in rows if r.get("returned_model")})},
            "usage": {"committed": t["committed"], "pending": t["pending"], "uncertain": t["uncertain"],
                      "thinking_tokens": sum(int((r.get("reconciled") or {}).get("thinking_tokens") or 0) for r in rows),
                      "rows_charged_at_reservation": sum(1 for r in rows if (r.get("reconciled") or {}).get("basis", "reported") != "reported")},
            "latency_ms": {"count": len(lat), "median": round(statistics.median(lat), 1) if lat else None, "max": max(lat) if lat else None},
            "reducer_model_reconciled": red.get("model", {}).get("reconciled"), "holdings_reconcile": red["reconciliation"]["holdings_match_final_state"],
            "reexecution": {k: v for k, v in reexecute(store, run_id).items() if k in ("checked", "matched", "mismatch_count", "all_matched")},
            "note": "40 ticks are an engineering test, not evidence of intelligent behaviour."}


def run(scenario: Scenario, profile: ModelProfile, ticks: int, db: Path, transport=None) -> dict:
    from genesis.model.runtime import LiveCallsDisabled
    from genesis.model.transport import CredentialMissing
    from genesis.storage import Store
    if db.exists():
        raise SystemExit(f"{db} already exists: a smoke run is never resumed or repeated automatically; choose a new --db path")
    db.parent.mkdir(parents=True, exist_ok=True)
    store = Store(db)
    run_id = store.create(scenario, model_profile=profile)
    if transport is not None:
        store.model_transports[run_id] = transport
    started, stop = time.time(), None
    try:
        for _ in range(ticks):
            if profile.run_deadline_s and time.time() - started > profile.run_deadline_s + 60:
                stop = "launcher wall-clock deadline reached"
                break
            store.step(run_id)
    except (LiveCallsDisabled, CredentialMissing) as exc:
        stop = f"refused before dispatch: {exc}"
    except Exception as exc:  # noqa: BLE001 - stop, record, never retry
        stop = f"stopped: {type(exc).__name__}: {str(exc)[:200]}"
    out = report(store, run_id, started, stop)
    path = db.with_suffix(".report.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    out["report_path"] = str(path)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("show", "rehearse", "live"))
    ap.add_argument("--config", required=True)
    ap.add_argument("--db")
    ap.add_argument("--profile-hash")
    args = ap.parse_args(argv)
    scenario, profile, ticks = load(args.config)
    if args.mode == "show":
        print(json.dumps(describe(profile, ticks), indent=2))
        return 0
    if not args.db:
        raise SystemExit("--db is required")
    if args.mode == "rehearse":
        from genesis.model.fixtures import GeminiFixtureResponder, MockGeminiServer
        from genesis.model.transport import GeminiTransport
        os.environ["GEMINI_API_KEY"] = SYNTHETIC_KEY            # this process only; a synthetic value
        responder = GeminiFixtureResponder(constrain=True)      # imitates schema-constrained decoding
        with MockGeminiServer(responder) as server:
            rehearsal = profile.model_copy(update={"mode": "mock-http", "live_authorized": False, "endpoint_label": "loopback mock Gemini (rehearsal)",
                                                   "adapter": profile.adapter.model_copy(update={"base_url": server.base_url})})
            out = run(scenario, rehearsal, ticks, Path(args.db), GeminiTransport.for_loopback_test(server.base_url))
        out["mock_requests_received"] = responder.calls
        print(json.dumps(out, indent=2))
        return 0
    expected = digest(profile.model_dump())
    if profile.mode != "live" or profile.adapter.base_url.rstrip("/") != GEMINI_ORIGIN:
        raise SystemExit("live mode needs a profile with mode 'live' and the official Gemini origin")
    if args.profile_hash != expected:
        raise SystemExit("--profile-hash does not match this profile; run 'show' and review it first")
    out = run(scenario, profile, ticks, Path(args.db))
    print(json.dumps(out, indent=2))
    return 0 if not (out["stopped_early"] or "").startswith("refused") else 2


if __name__ == "__main__":
    raise SystemExit(main())
