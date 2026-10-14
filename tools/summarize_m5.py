"""Summaries of Milestone 5 evidence: per-world rows, paired comparisons under the frozen claim rule, and a Markdown table.

Usage: python tools/summarize_m5.py evidence/v0.5.0
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def sealed_index(sealed: dict | None) -> dict:
    out = {}
    for w in (sealed or {}).get("worlds", []):
        if w.get("status") == "scored":
            out[(w["seed"], w["condition"])] = w
    return out


def pick_score(pick):
    return None if not pick else round(pick["selection_score"], 4)


def row(world: dict, sealed: dict) -> dict:
    s = world.get("summary")
    if not s:
        return {"seed": world["seed"], "condition": world["condition"], "status": world["status"], "failure": world.get("failure")}
    final = s["freezes"][-1]
    scored = sealed.get((world["seed"], world["condition"]))
    sfinal = scored["freezes"][-1] if scored else {}
    sealed_of = lambda key: (sfinal.get(key) or {}).get("sealed", {}).get("score") if sfinal.get(key) else None  # noqa: E731
    dep = s["components"]["dependency_teaching"]
    sessions = s["sessions"]
    cross = [x for x in sessions if x["teacher_cohort"] != x["learner_cohort"]]
    return {
        "seed": world["seed"], "condition": world["condition"], "status": world["status"],
        "final_cohort_best_validation": pick_score(final["cohort_best"]), "final_held_best_validation": pick_score(final.get("held_best")),
        "final_accessible_best_validation": pick_score(final["accessible_best"]),
        "final_held_best_sealed": sealed_of("held_best"), "final_cohort_best_sealed": sealed_of("cohort_best"),
        "final_accessible_best_sealed": sealed_of("accessible_best"), "baseline_sealed": (scored or {}).get("baseline_sealed", {}).get("score"),
        "final_held_best_created_by_cohort": (final.get("held_best") or {}).get("cohort"),
        "final_held_best_closure": len((final.get("held_best") or {}).get("closure") or []),
        "freeze_validation_by_cohort": [(f["cohort"], pick_score(f["cohort_best"]), pick_score(f.get("held_best"))) for f in s["freezes"]],
        "further_improvement": [(x["cohort"], x["improved_beyond_previous_held"]) for x in s["further_improvement"]],
        "proposals": s["search"]["proposals"], "unique_programs": s["search"]["unique_programs"],
        "duplicate_behaviour_dev_results": s["search"]["duplicate_behaviour_dev_results"], "submissions": s["search"]["submissions"],
        "improvement_admissions": s["search"]["improvement_admissions"], "refactor_admissions": s["search"]["refactor_admissions"],
        "stop_reasons": s["search"]["stop_reasons"], "private_parent_proposals": s["search"]["private_parent_proposals"],
        "component_extractions": s["components"]["extractions"], "component_revisions": s["components"]["revisions"],
        "components_admitted": s["components"]["admitted_by_origin"], "compositions": s["components"]["compositions"],
        "calling_workflow_admissions": s["components"]["calling_workflow_admissions"],
        "executions_with_dependencies": s["components"]["executions_with_dependencies"],
        "executions_with_dependencies_by_later_cohort": s["components"]["executions_by_non_creator_cohort"],
        "uses_of_earlier_cohort_artifacts": s["inherited"]["uses_of_earlier_cohort_artifacts"],
        "sessions": len(sessions), "sessions_acquired": sum(1 for x in sessions if x["outcome"] == "acquired"),
        "cross_generation_sessions": len(cross), "cross_generation_acquired": sum(1 for x in cross if x["outcome"] == "acquired"),
        "cross_generation_failed": sum(1 for x in cross if x["outcome"] == "failed"),
        "cross_generation_interrupted": sum(1 for x in cross if x["outcome"] in ("interrupted", "expired")),
        "dependencies_taught_in_package": dep["dependencies_taught_in_package"], "dependencies_acquired": dep["dependencies_acquired"],
        "cross_generation_admitted_revisions": s["cross_generation"]["admitted_revisions"],
        "produced_alloy": s["overall"]["produced_alloy"], "production_energy_per_alloy": s["overall"]["production_energy_per_alloy"]["value"]}


def paired(rows: list[dict], a: str, b: str, key: str) -> dict:
    """Lower is better. Counts seeds where a < b, a > b, ties; the frozen rule needs >= 4 of 5 for a consistent direction."""
    by = {(r["seed"], r["condition"]): r for r in rows}
    seeds = sorted({r["seed"] for r in rows})
    pairs = [(by.get((s, a), {}).get(key), by.get((s, b), {}).get(key), s) for s in seeds]
    pairs = [(x, y, s) for x, y, s in pairs if x is not None and y is not None]
    better = sum(1 for x, y, _ in pairs if x < y)
    worse = sum(1 for x, y, _ in pairs if x > y)
    verdict = (f"{a} lower in {better}/{len(pairs)}" if better >= 4 else f"{b} lower in {worse}/{len(pairs)}" if worse >= 4 else "no consistent difference")
    return {"a": a, "b": b, "metric": key, "pairs": [{"seed": s, a: x, b: y} for x, y, s in pairs], "a_lower": better, "b_lower": worse,
            "ties": len(pairs) - better - worse, "mean_a": round(statistics.mean(x for x, _, _ in pairs), 4) if pairs else None,
            "mean_b": round(statistics.mean(y for _, y, _ in pairs), 4) if pairs else None, "verdict_under_frozen_rule": verdict}


def totals(rows: list[dict], condition: str, keys: list[str]) -> dict:
    mine = [r for r in rows if r["condition"] == condition and r["status"] == "completed"]
    return {k: sum(r[k] for r in mine) for k in keys} | {"worlds": len(mine)}


def main(root: Path) -> None:
    out = {}
    md = ["# v0.5.0 evidence summary (generated by tools/summarize_m5.py)", ""]
    pol = load(root / "policy" / "policy.json")
    if pol:
        rows = [row(w, sealed_index(load(root / "policy" / "sealed-results.json"))) for w in pol["worlds"]]
        comparisons = []
        for access in ("preserved", "reset"):
            for key in ("final_held_best_validation", "final_held_best_sealed", "final_cohort_best_sealed"):
                comparisons.append(paired(rows, f"beam/{access}", f"first-improvement/{access}", key))
        for key in ("final_held_best_validation", "final_held_best_sealed"):
            comparisons.append(paired(rows, "beam/preserved", "beam-nocomponents/preserved", key))
            comparisons.append(paired(rows, "first-improvement/preserved", "first-improvement/reset", key))
            comparisons.append(paired(rows, "beam/preserved", "beam/reset", key))
        keys = ["proposals", "submissions", "improvement_admissions", "refactor_admissions", "component_extractions", "component_revisions",
                "compositions", "calling_workflow_admissions", "executions_with_dependencies", "executions_with_dependencies_by_later_cohort",
                "uses_of_earlier_cohort_artifacts", "cross_generation_admitted_revisions", "duplicate_behaviour_dev_results"]
        out["P"] = {"rows": rows, "comparisons": comparisons, "totals": {c: totals(rows, c, keys) for c in pol["conditions"]}, "parity": pol.get("parity")}
        md += ["## P: search policy x access (lower cost per alloy is better)", "",
               "| comparison | metric | a lower | b lower | ties | mean a | mean b | verdict (>=4/5) |", "|---|---|---|---|---|---|---|---|"]
        md += [f"| {c['a']} vs {c['b']} | {c['metric']} | {c['a_lower']} | {c['b_lower']} | {c['ties']} | {c['mean_a']} | {c['mean_b']} | {c['verdict_under_frozen_rule']} |"
               for c in comparisons]
        md += ["", "| condition | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
        md += [f"| {c} | " + " | ".join(str(out['P']['totals'][c][k]) for k in keys) + " |" for c in pol["conditions"]]
        md.append("")
    tea = load(root / "teaching" / "teaching.json")
    if tea:
        rows = [row(w, sealed_index(load(root / "teaching" / "sealed-results.json"))) for w in tea["worlds"]]
        comparisons = [paired(rows, "teaching-only", "none", k) for k in ("final_held_best_validation", "final_held_best_sealed")]
        comparisons += [paired(rows, "library", "none", k) for k in ("final_held_best_validation", "final_held_best_sealed")]
        comparisons += [paired(rows, "library", "teaching-only", k) for k in ("final_held_best_validation", "final_held_best_sealed")]
        keys = ["sessions", "sessions_acquired", "cross_generation_sessions", "cross_generation_acquired", "cross_generation_failed",
                "cross_generation_interrupted", "dependencies_taught_in_package", "dependencies_acquired", "uses_of_earlier_cohort_artifacts",
                "cross_generation_admitted_revisions", "calling_workflow_admissions", "refactor_admissions"]
        further = {c: sum(1 for r in rows if r["condition"] == c for _, ok in r.get("further_improvement", []) if ok) for c in tea["conditions"]}
        out["T"] = {"rows": rows, "comparisons": comparisons, "totals": {c: totals(rows, c, keys) for c in tea["conditions"]},
                    "further_improvement_transitions": further, "parity": tea.get("parity")}
        md += ["## T: teaching across overlapping generations", "",
               "| comparison | metric | a lower | b lower | ties | mean a | mean b | verdict (>=4/5) |", "|---|---|---|---|---|---|---|---|"]
        md += [f"| {c['a']} vs {c['b']} | {c['metric']} | {c['a_lower']} | {c['b_lower']} | {c['ties']} | {c['mean_a']} | {c['mean_b']} | {c['verdict_under_frozen_rule']} |"
               for c in comparisons]
        md += ["", "| condition | " + " | ".join(keys) + " | cohort transitions with further improvement (of 10) |", "|---" * (len(keys) + 2) + "|"]
        md += [f"| {c} | " + " | ".join(str(out['T']['totals'][c][k]) for k in keys) + f" | {further[c]} |" for c in tea["conditions"]]
        md.append("")
    (root / "summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (root / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
