"""Observer views of model-backed inhabitants (API side). Everything returned here is sanitized: profiles contain no
secrets by construction, prompts/responses are scrubbed again before display, and wall-clock latency is reported
separately from simulation speed."""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter

from ..models import JSON
from . import budget
from . import ledger as model_ledger
from . import adapter, gemini
from .profile import public_view
from .runtime import run_halt, scrub


def summary(store, run_id: str, recent_ticks: int = 60) -> JSON | None:
    profile = store.model_profile(run_id)
    if profile is None:
        return None
    with store.connection() as db:
        rows = model_ledger.rows(db, run_id)
        records = [json.loads(r[0]) for r in db.execute("SELECT record FROM ticks WHERE run_id=? ORDER BY tick DESC LIMIT ?", (run_id, recent_ticks))]
    latest: dict[str, JSON] = {}
    mode_counts: Counter = Counter()
    rejected_model_actions = 0
    for record in reversed(records):
        rejected_ids = {e["id"] for e in record["events"] if e.get("type") == "action_rejected" and e.get("id")}
        for d in record["decisions"]:
            agent = d["action"]["agent"]
            if agent in profile.agents:
                mode_counts[d["controller"]] += 1
                latest[agent] = {"tick": record["tick"], "mode": d["controller"], "reason": (d.get("model") or {}).get("reason"),
                                 "action": d["action"]["kind"], "accepted": d["action"]["id"] not in rejected_ids,
                                 "receipt": (d.get("model") or {}).get("receipt"), "source": (d.get("model") or {}).get("source")}
                if d["controller"] in ("model-proposal", "model-intent-execution") and d["action"]["id"] in rejected_ids:
                    rejected_model_actions += 1
    lat = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    per_agent = {a: {"remaining": budget.remaining(profile.agent_budget, [r for r in rows if r["agent"] == a]),
                     "totals": budget.totals([r for r in rows if r["agent"] == a]), "latest": latest.get(a)} for a in profile.agents}
    return {"profile": public_view(profile), "capabilities": (gemini if profile.adapter.provider == "gemini" else adapter).capabilities(profile.adapter.model_dump()), "paused": store.model_paused(run_id),
            "provider": profile.adapter.provider, "requested_model": profile.adapter.model,
            "halt": run_halt(profile, rows, time.time()),
            "source_indicator": {"fixture": "FIXTURE (scripted responses, not a model)", "mock-http": "MOCK HTTP (scripted, real wire format)",
                                 "recorded": "RECORDED (re-used responses; no new calls)", "live": "LIVE MODEL"}[profile.mode],
            "run": {"remaining": budget.remaining(profile.run_budget, rows), "totals": budget.totals(rows)}, "agents": per_agent,
            "status_counts": dict(Counter(r["status"] for r in rows)), "parse_failures": sum(1 for r in rows if r.get("parse_error")),
            "repairs": sum(1 for r in rows if r["role"] == "repair"), "fallback_decisions_recent": mode_counts.get("fallback", 0),
            "rejected_model_actions_recent": rejected_model_actions, "decision_modes_recent": dict(mode_counts),
            "provider_latency_ms": {"count": len(lat), "median": round(statistics.median(lat), 1) if lat else None, "max": max(lat) if lat else None,
                                    "note": "wall-clock provider latency (outside world-state hashes); not simulation speed"},
            "usage_totals": {"thinking_tokens": sum(int((r.get("reconciled") or {}).get("thinking_tokens") or 0) for r in rows),
                             "cached_input_tokens": sum(int((r.get("reconciled") or {}).get("cached_input_tokens") or 0) for r in rows),
                             "estimated_rows": sum(1 for r in rows if (r.get("reconciled") or {}).get("basis", "reported") != "reported")},
            "calls": [{k: r.get(k) for k in ("decision_id", "agent", "tick", "role", "attempt", "status", "source", "returned_model", "parse_error",
                                             "fallback", "termination", "receipt", "consumed_tick", "resolved")}
                      | {"usage": r.get("reconciled"), "finish_reason": (r.get("usage") or {}).get("finish_reason")}
                      for r in rows[-40:]][::-1]}


def call_detail(store, run_id: str, decision_id: str) -> JSON:
    with store.connection() as db:
        row = model_ledger.get(db, decision_id)
    if row is None or row["run_id"] != run_id:
        raise KeyError("call not found")
    out = {k: row.get(k) for k in model_ledger.SANITIZED_EXPORT_FIELDS}
    for k in ("prompt", "response", "termination", "fallback", "parse_error"):
        if isinstance(out.get(k), str):
            out[k] = scrub(out[k])                       # defence in depth: never display credential-like text
    return out
