"""Phase B: the ModelController used inside the engine tick. It performs no I/O and never calls a provider; it only
turns phase-A results into Actions and labels every decision with its true source.

Decision modes recorded with each action:
- model-proposal:          a model response parsed into this action (fixture / mock-http / recorded / live source noted)
- model-intent-execution:  repeating the agent's standing model choice (no new call; links to the original receipt)
- offline-policy:          the ordinary OfflineController (between deliberations, busy, paused, not designated)
- fallback:                the configured explicit fallback (budget, parse failure, timeout, unknown outcome, ...)
The engine still validates every action; an illegal model action is an ordinary rejected world action.
"""
from __future__ import annotations

from ..controllers import OfflineController
from ..models import JSON, Action, digest
from .runtime import Prepared
from .schema import to_action


class ModelController:
    def __init__(self, offline: OfflineController, prepared: dict[str, Prepared], designated: list[str]):
        self.offline, self.prepared, self.designated = offline, prepared, set(designated)
        self.diagnostic: JSON | None = None
        self.decision_meta: JSON | None = None

    def propose(self, obs: JSON) -> Action:
        aid = obs["self"]["id"]
        self.decision_meta, self.diagnostic = None, None
        if aid not in self.designated:
            return self._offline(obs, None)
        p = self.prepared.get(aid)
        if p is None:
            return self._offline(obs, {"mode": "offline-policy", "reason": "not prepared this tick"})
        if p.observation_hash != digest(obs):
            return self._offline(obs, {"mode": "fallback", "reason": "observation changed after preparation; prepared decision not applied",
                                       "decision_ids": p.decision_ids})
        meta = {"mode": p.mode, "reason": p.reason, "decision_ids": p.decision_ids, "receipt": p.receipt, "source": p.source,
                "new_calls": p.new_calls, "new_tokens": p.new_tokens}
        if p.mode in ("model-proposal", "model-intent-execution"):
            if p.origin:
                meta["origin"] = p.origin
            if p.proposal.get("explanation"):
                meta["generated_explanation"] = p.proposal["explanation"]      # labelled; never authoritative
            self.decision_meta = {k: v for k, v in meta.items() if v not in (None, [])}
            return to_action(p.proposal, aid, obs["tick"])
        return self._offline(obs, {k: v for k, v in meta.items() if v not in (None, [])})

    def _offline(self, obs: JSON, meta: JSON | None) -> Action:
        action = self.offline.propose(obs)
        self.diagnostic = self.offline.diagnostic
        self.decision_meta = meta
        return action
