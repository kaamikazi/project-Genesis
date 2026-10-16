"""Event-driven deliberation: decide, per designated agent and tick, whether to ask the model.

Outcomes:
- call:    ask the model now (with a trigger reason);
- intent:  repeat the agent's standing model choice (execution of a prior model decision, no new call);
- offline: use the ordinary OfflineController (between deliberations, busy, paused).
A call is never made more often than once per `min_interval` ticks per agent. Triggers: no earlier decision, the last
action was rejected, a new message arrived, no standing intent remains, or the refresh interval elapsed.
The scheduler's inputs are the agent's restricted observation and that agent's ledger rows, so its choices are
reproducible from the record (no in-memory state).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import JSON
from .profile import SchedulerConfig

ATTEMPTED = ("dispatching", "completed", "consumed", "failed-not-delivered", "failed-delivered", "outcome-unknown", "expired-unconsumed")


@dataclass
class Plan:
    kind: str                 # "call" | "intent" | "offline"
    reason: str
    intent: JSON | None = None


def standing_intent(agent_rows: list[JSON]) -> JSON | None:
    consumed = [r for r in agent_rows if r["status"] == "consumed" and r.get("parsed")]
    if not consumed:
        return None
    last = consumed[-1]
    return last if last["parsed"].get("standing") else None


def decide(obs: JSON, agent_rows: list[JSON], cfg: SchedulerConfig, paused: bool) -> Plan:
    a, tick = obs["self"], obs["tick"]
    if paused:
        return Plan("offline", "model scheduling paused by operator")
    # an unknown outcome from an earlier tick pauses this agent; one from this tick is reported by this tick's decision
    if any(r["status"] == "outcome-unknown" and not r["resolved"] and r["tick"] < tick for r in agent_rows):
        return Plan("offline", "outcome-unknown request pending (model use paused for this agent until resolved)")
    if a.get("busy_until", 0) > tick:
        return Plan("offline", "busy with a batch")
    if any(s.get("stage") == "instruction" for s in obs.get("sessions") or []):
        return Plan("offline", "reserved by a teaching session")
    # rows of the current tick belong to the decision being made now (e.g. a response persisted before a crash)
    attempted = [r for r in agent_rows if r["role"] == "primary" and r["status"] in ATTEMPTED and r["tick"] < tick]
    last_call = max((r["tick"] for r in attempted), default=None)
    since = None if last_call is None else tick - last_call
    intent = standing_intent(agent_rows)
    last = a.get("last_result") or {}
    rejected = last.get("type") == "action_rejected"
    new_message = last_call is not None and any(m.get("tick", -1) > last_call for m in a.get("messages") or [])
    intent_ok = (intent is not None and tick - intent["tick"] < cfg.max_interval and not rejected and not new_message
                 and last.get("kind") == intent["parsed"]["kind"] and last.get("type") == "action_accepted")
    if since is not None and since < cfg.min_interval:
        if intent_ok:
            return Plan("intent", "standing model choice (within minimum interval)", intent)
        return Plan("offline", f"between deliberations (minimum interval {cfg.min_interval})")
    if last_call is None:
        return Plan("call", "first deliberation")
    if rejected:
        return Plan("call", "last action rejected")
    if new_message:
        return Plan("call", "new message received")
    if intent_ok:
        return Plan("intent", "standing model choice", intent)
    if since >= cfg.max_interval:
        return Plan("call", "refresh interval elapsed")
    return Plan("call", "no standing intent")
