"""Budget arithmetic over ledger rows (integer units throughout).

Per call the ledger holds a `reservation` (conservative upper bound written before dispatch) and, after the outcome is
known, a `reconciled` usage. Totals per run and per agent:
- committed: reconciled usage of completed / consumed / failed-delivered rows (reported tokens where the provider
  reported them, otherwise the reservation, labelled estimated);
- pending:   reservations of reserved / dispatching rows;
- uncertain: reservations of outcome-unknown rows (never released to zero);
- historical: usage of recordings re-used from another run (not new usage, never charged again).
A new call is allowed only if committed + pending + uncertain + its own reservation stays within every ceiling.

Input-token reservations use the UTF-8 byte length of the prompt as a heuristic upper bound (labelled estimate, not a
provider guarantee); output is bounded by options.num_predict. Money is reserved only when prices are configured.
"""
from __future__ import annotations

from ..models import JSON
from .profile import Ceilings, ModelProfile

DIMENSIONS = ("requests", "input_tokens", "output_tokens", "controller_time_ms", "cost_micros")
PENDING = ("reserved", "dispatching")
UNCERTAIN = ("outcome-unknown",)
COMMITTED = ("completed", "consumed", "failed-delivered", "expired-unconsumed", "failed-not-delivered")
NO_USAGE = ("cancelled-before-dispatch", "blocked")


def cost_micros(profile: ModelProfile, input_tokens: int, output_tokens: int) -> int | None:
    p = profile.pricing
    if p is None:
        return None
    # ceil division keeps the estimate conservative and integral
    return -(-(input_tokens * p.input_micros_per_mtok + output_tokens * p.output_micros_per_mtok) // 1_000_000)


def reservation(profile: ModelProfile, input_bytes: int) -> JSON:
    out = profile.adapter.max_output_tokens
    return {"requests": 1, "input_tokens": input_bytes, "output_tokens": out, "controller_time_ms": profile.adapter.deadline_ms,
            "cost_micros": cost_micros(profile, input_bytes, out), "basis": "upper bound: prompt bytes as input tokens (heuristic), num_predict as output tokens",
            "pricing_version": profile.pricing.version if profile.pricing else None, "currency": profile.pricing.currency if profile.pricing else None}


def usage_of(row: JSON) -> tuple[str, JSON]:
    status = row["status"]
    if row.get("source") == "recorded":
        return "historical", row.get("reconciled") or {}
    if status in PENDING:
        return "pending", row["reservation"] or {}
    if status in UNCERTAIN:
        return "uncertain", row["reservation"] or {}
    if status in COMMITTED:
        return "committed", row.get("reconciled") or row["reservation"] or {}
    return "none", {}


def totals(rows: list[JSON]) -> JSON:
    out = {k: {d: 0 for d in DIMENSIONS} for k in ("committed", "pending", "uncertain", "historical")}
    for row in rows:
        bucket, use = usage_of(row)
        if bucket == "none":
            continue
        for d in DIMENSIONS:
            v = use.get(d)
            if isinstance(v, int):
                out[bucket][d] += v
    out["charged"] = {d: out["committed"][d] + out["pending"][d] + out["uncertain"][d] for d in DIMENSIONS}
    return out


def check(ceilings: Ceilings, rows: list[JSON], new: JSON) -> str | None:
    """None if the new reservation fits; otherwise the first exceeded dimension."""
    charged = totals(rows)["charged"]
    limits = ceilings.model_dump()
    for d in DIMENSIONS:
        limit = limits.get(d)
        if limit is None:
            continue
        if new.get(d) is None and d == "cost_micros":
            continue
        if charged[d] + (new.get(d) or 0) > limit:
            return d
    return None


def remaining(ceilings: Ceilings, rows: list[JSON]) -> JSON:
    charged = totals(rows)["charged"]
    return {d: (None if ceilings.model_dump().get(d) is None else ceilings.model_dump()[d] - charged[d]) for d in DIMENSIONS}
