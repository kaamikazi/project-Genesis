"""Paired comparisons with explicit denominators (genesis-metrics-1 `compare.paired`) and the v0.5.1 summaries.

Usage: python tools/summarize_m5b.py EVIDENCE_DIR
Every comparison reports expected worlds, completed worlds, eligible pairs, missing values with reasons,
wins/losses/ties among eligible pairs and the denominator used by the decision rule. Means use eligible pairs only.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

RULE = {"min_eligible_fraction": 0.75, "min_share": 0.75,
        "text": "a direction is reported only if at least 75% of expected worlds are eligible pairs AND the same side is lower in at least 75% of eligible pairs; otherwise 'no consistent difference' or 'insufficient eligible pairs'. Descriptive, not a significance test."}


def sign_test_p(wins: int, losses: int) -> float | None:
    """Two-sided exact sign test over non-tied pairs (descriptive only)."""
    n = wins + losses
    if n == 0:
        return None
    k = min(wins, losses)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 4)


def paired(rows: list[dict], a: str, b: str, key: str, expected_seeds: list[int], missing_reason=None) -> dict:
    by = {(r["seed"], r["condition"]): r for r in rows}
    pairs, missing = [], []
    for seed in expected_seeds:
        why = []
        vals = []
        for cond in (a, b):
            r = by.get((seed, cond))
            if r is None or r.get("status") != "completed":
                why.append(f"{cond}: world {'missing' if r is None else 'failed'}")
                vals.append(None)
                continue
            v = r.get(key)
            if v is None:
                why.append(f"{cond}: {missing_reason(r) if missing_reason else 'value unavailable'}")
            vals.append(v)
        if None in vals:
            missing.append({"seed": seed, "reason": "; ".join(why)})
        else:
            pairs.append((seed, vals[0], vals[1]))
    a_lower = sum(1 for _, x, y in pairs if x < y)
    b_lower = sum(1 for _, x, y in pairs if x > y)
    ties = len(pairs) - a_lower - b_lower
    eligible, expected = len(pairs), len(expected_seeds)
    if eligible < RULE["min_eligible_fraction"] * expected:
        verdict = f"insufficient eligible pairs ({eligible} of {expected})"
    elif a_lower >= RULE["min_share"] * eligible:
        verdict = f"{a} lower in {a_lower}/{eligible} eligible"
    elif b_lower >= RULE["min_share"] * eligible:
        verdict = f"{b} lower in {b_lower}/{eligible} eligible"
    else:
        verdict = "no consistent difference"
    completed = {c: sum(1 for s in expected_seeds if by.get((s, c), {}).get("status") == "completed") for c in (a, b)}
    return {"a": a, "b": b, "metric": key, "expected_worlds": expected, "completed_worlds": completed, "eligible_pairs": eligible,
            "missing": missing, "a_lower": a_lower, "b_lower": b_lower, "ties": ties, "decision_denominator": eligible,
            "mean_a_over_eligible": round(statistics.mean(x for _, x, _ in pairs), 4) if pairs else None,
            "mean_b_over_eligible": round(statistics.mean(y for _, _, y in pairs), 4) if pairs else None,
            "sign_test_p_descriptive": sign_test_p(a_lower, b_lower), "pairs": [{"seed": s, a: x, b: y} for s, x, y in pairs],
            "verdict": verdict, "rule": RULE["text"]}


def markdown_table(comparisons: list[dict]) -> list[str]:
    lines = ["| A vs B | metric | expected | eligible | A lower | B lower | ties | mean A / B (eligible) | sign-test p (descr.) | missing | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in comparisons:
        miss = "; ".join(f"{m['seed']}: {m['reason']}" for m in c["missing"]) or "—"
        lines.append(f"| {c['a']} vs {c['b']} | {c['metric']} | {c['expected_worlds']} | {c['eligible_pairs']} | {c['a_lower']} | {c['b_lower']} | {c['ties']} | "
                     f"{c['mean_a_over_eligible']} / {c['mean_b_over_eligible']} | {c['sign_test_p_descriptive']} | {miss} | {c['verdict']} |")
    return lines


if __name__ == "__main__":
    from tools.m5b_reports import main   # report assembly lives with the experiment-specific code
    main(Path(sys.argv[1]))
