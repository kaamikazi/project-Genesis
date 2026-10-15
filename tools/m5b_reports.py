"""Assemble the v0.5.1 (M5b) summary from generated evidence. Each protocol is reported in its own section.

Usage: python tools/summarize_m5b.py evidence/v0.5.1
"""
from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

from tools.summarize_m5b import RULE, markdown_table, paired


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def sealed_index(path: Path) -> dict:
    data = load(path) or {"worlds": []}
    return {(w["seed"], w["condition"]): w for w in data["worlds"] if w.get("status") == "scored"}


def pick(fz: dict, key: str):
    p = fz.get(key)
    return p and p.get("selection_score")


def sealed_pick(sw: dict | None, idx: int, key: str):
    if not sw:
        return None
    rows = sw["freezes"]
    if idx >= len(rows) or not rows[idx].get(key):
        return None
    return rows[idx][key]["sealed"]["score"]


def world_row(w: dict, sealed: dict, folder: Path) -> dict:
    if w["status"] != "completed":
        return {"seed": w["seed"], "condition": w["condition"], "status": w["status"], "failure": w.get("failure")}
    s = w["summary"]
    fz = s["freezes"]
    sw = sealed.get((w["seed"], w["condition"]))
    last = len(fz) - 1
    m = s["metrics"]
    further = []
    for k in range(1, len(fz)):
        ref_v, own_v = pick(fz[k - 1], "created_upto_best"), pick(fz[k], "cohort_best")
        ref_s, own_s = sealed_pick(sw, k - 1, "created_upto_best"), sealed_pick(sw, k, "cohort_best")
        further.append({"cohort": fz[k]["cohort"], "reference_validation": ref_v, "own_validation": own_v, "reference_sealed": ref_s, "own_sealed": own_s,
                        "improved_validation": None if own_v is None or ref_v is None else own_v < ref_v,
                        "improved_sealed": None if own_s is None or ref_s is None else own_s < ref_s,
                        "status": "no admitted workflow by this cohort" if own_v is None else "compared"})
    lessons = [x for x in s["sessions"] if x["teacher_cohort"] < x["learner_cohort"]]
    dep = [x for x in lessons if x["closure"]]
    row = {"seed": w["seed"], "condition": w["condition"], "status": "completed",
           "final_held_best_validation": pick(fz[last], "held_best"), "final_held_best_sealed": sealed_pick(sw, last, "held_best"),
           "final_created_best_validation": pick(fz[last], "created_upto_best"), "final_created_best_sealed": sealed_pick(sw, last, "created_upto_best"),
           "final_cohort_best_validation": pick(fz[last], "cohort_best"), "final_cohort_best_sealed": sealed_pick(sw, last, "cohort_best"),
           "baseline_sealed": sw and sw["baseline_sealed"]["score"], "further": further,
           "further_improved_validation": sum(1 for f in further if f["improved_validation"]), "further_improved_sealed": sum(1 for f in further if f["improved_sealed"]),
           "further_compared": sum(1 for f in further if f["status"] == "compared"), "further_transitions": len(further),
           "cross_generation_lessons": len(lessons), "cross_generation_acquired": sum(1 for x in lessons if x["outcome"] == "acquired"),
           "cross_generation_failed": sum(1 for x in lessons if x["outcome"] == "failed"),
           "cross_generation_interrupted": sum(1 for x in lessons if x["outcome"] in ("interrupted", "expired")),
           "dependency_lessons": len(dep), "dependency_lessons_acquired": sum(1 for x in dep if x["outcome"] == "acquired"),
           "dependencies_acquired": sum(len(x["dependencies_acquired"]) for x in lessons),
           "population": s.get("population"), **{k: v for k, v in m.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}}
    row.update(dependency_detail(w, folder))
    return row


def dependency_detail(w: dict, folder: Path) -> dict:
    """Eligibility (a senior held a component-calling workflow during an overlap) and independent post-retirement execution."""
    export = json.loads(gzip.decompress((folder / w["export"]["file"]).read_bytes()))
    st = export["state"]
    ct, ov = st["config"]["cohort_ticks"], st["config"]["cohort_overlap"]
    eligible = []
    for k in range(st["config"]["cohort_count"] - 1):
        boundary = (k + 1) * ct
        calling = [a for a in st["artifacts"].values() if a.get("kind") == "workflow" and a.get("closure") and a.get("cohort", 0) == k
                   and a["created_tick"] < boundary and a["status"] in ("admitted", "superseded")]
        eligible.append({"transition": k + 1, "senior_component_workflows": len(calling), "overlap_window": [boundary - ov, boundary]})
    acquired = {(x["learner"], x["artifact"]): (x["teacher"], x["acquired_tick"]) for x in st["sessions"].values()
                if x["stage"] == "acquired" and x.get("closure")}
    independent = 0
    for entry in export["ticks"]:
        for e in entry["record"]["events"]:
            if e.get("type") == "action_accepted" and e["kind"] == "use_artifact" and (e["agent"], e["result"]["artifact"]) in acquired:
                teacher, _ = acquired[(e["agent"], e["result"]["artifact"])]
                retired = st["agents"][teacher].get("retired_tick")
                if retired is not None and e["tick"] > retired:
                    independent += 1
    return {"eligible_transitions": sum(1 for x in eligible if x["senior_component_workflows"]), "eligibility": eligible,
            "independent_post_retirement_executions_of_taught_dependency_workflows": independent}


def section_paired(rows: list, pairs: list, keys: list, seeds: list) -> list:
    out = []
    for a, b in pairs:
        for key in keys:
            def reason(r: dict, key: str = key) -> str:
                if r.get("status") != "completed":
                    return "world failed"
                if key.endswith("_sealed") and r.get(key.replace("_sealed", "_validation")) is not None:
                    return "sealed score unavailable (selection exists)"
                return "no admitted workflow selected"
            out.append(paired(rows, a, b, key, seeds, missing_reason=reason))
    return out


def main(root: Path) -> None:
    summary, md = {}, ["# v0.5.1 (M5b) evidence summary (generated by tools/summarize_m5b.py)", "", f"Paired-comparison rule: {RULE['text']}", ""]
    bug = load(root / "bugfix" / "bugfix-evidence.json")
    if bug:
        summary["bugfix"] = bug["summary"]
        md += ["## 1. Defect repairs (minimal reproductions, v0.5.0 vs v0.5.1)", "", "| scenario | rejected actions in 10 ticks (v0.5.0) | after repair |", "|---|---|---|"]
        md += [f"| {k} | {v['rejected_before']} | {v['rejected_after']} |" for k, v in bug["summary"].items()] + [""]
    protocol = load(root / "protocol" / "protocol.json")
    seeds = protocol["evaluation_seeds"] if protocol else []
    for name, title, pairs, keys in (
        ("allocation", "3. Prospective allocation experiment (primary: final held best, sealed-3)",
         [("beam-alloc/preserved", "beam/preserved"), ("beam-alloc/reset", "beam/reset"), ("beam-alloc/preserved", "first-improvement/preserved"),
          ("beam/preserved", "first-improvement/preserved"), ("beam-alloc/reset", "first-improvement/reset"), ("beam-alloc/preserved", "beam-alloc/reset"),
          ("first-improvement/preserved", "first-improvement/reset")],
         ["final_held_best_sealed", "final_held_best_validation", "final_created_best_sealed"]),
        ("mentorship", "4. Prospective mentorship experiment",
         [("teaching-only", "none"), ("library", "none"), ("library", "teaching-only")],
         ["final_held_best_sealed", "final_held_best_validation", "final_created_best_sealed"])):
        rep = load(root / name / f"{name}.json")
        if not rep:
            continue
        sealed = sealed_index(root / name / "sealed-results.json")
        rows = [world_row(w, sealed, root / name) for w in rep["worlds"]]
        comps = section_paired(rows, pairs, keys, seeds)
        conds = list(rep["conditions"])
        tot_keys = ["search.credit_actions", "search.proposals", "search.own_candidate_tests", "search.repeated_decisions_own", "search.untested_proposals",
                    "search.novelty_rejected_candidates", "search.reserve_stops", "search.stale_reference_rejections", "search.withdrawals",
                    "admission.improvement_admissions", "admission.refactor_admissions", "lineage.improvements_on_earlier_cohort_reference",
                    "lineage.improvements_with_earlier_cohort_ancestry", "production.alloy", "production.rejected_use_missing_prerequisite",
                    "further_improved_validation", "further_improved_sealed", "further_compared", "further_transitions",
                    "cross_generation_lessons", "cross_generation_acquired", "cross_generation_failed", "cross_generation_interrupted",
                    "dependency_lessons", "dependency_lessons_acquired", "dependencies_acquired", "eligible_transitions",
                    "independent_post_retirement_executions_of_taught_dependency_workflows"]
        totals = {c: {k: sum((r.get(k) or 0) for r in rows if r["condition"] == c and r["status"] == "completed") for k in tot_keys} |
                  {"worlds_completed": sum(1 for r in rows if r["condition"] == c and r["status"] == "completed"),
                   "worlds_failed": sum(1 for r in rows if r["condition"] == c and r["status"] != "completed")} for c in conds}
        summary[name] = {"rows": rows, "comparisons": comps, "totals": totals, "parity": rep.get("parity")}
        md += [f"## {title}", "", f"Seeds: {seeds}. Parity: {rep.get('parity')}", ""] + markdown_table(comps) + ["", "| condition | " + " | ".join(tot_keys) + " |",
               "|---" * (len(tot_keys) + 1) + "|"]
        md += [f"| {c} | " + " | ".join(str(totals[c][k]) for k in tot_keys) + " |" for c in conds]
        md += ["", "| seed | condition | held best val / sealed | created best val / sealed | further (val, sealed of compared/transitions) | dependency lessons (acq/total) | eligible transitions |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            if r["status"] != "completed":
                md.append(f"| {r['seed']} | {r['condition']} | FAILED: {r.get('failure')} | | | | |")
                continue
            md.append(f"| {r['seed']} | {r['condition']} | {r['final_held_best_validation']} / {r['final_held_best_sealed']} | {r['final_created_best_validation']} / {r['final_created_best_sealed']} | "
                      f"{r['further_improved_validation']}, {r['further_improved_sealed']} of {r['further_compared']}/{r['further_transitions']} | {r['dependency_lessons_acquired']}/{r['dependency_lessons']} | {r['eligible_transitions']} |")
        md.append("")
    rerun = load(root / "rerun" / "rerun.json")
    if rerun:
        sealed = sealed_index(root / "rerun" / "sealed-2-retrospective.json")
        rows = [world_row(w, sealed, root / "rerun") for w in rerun["worlds"]]
        for r in rows:
            src = next(w for w in rerun["worlds"] if w["seed"] == r["seed"] and w["condition"] == r["condition"])
            r["condition"] = f"{src['source_protocol']}:{r['condition']}"
        summary["rerun"] = {"rows": rows}
        md += ["## 2. Repaired retrospective rerun of the v0.5.0 worlds (labelled; does not replace v0.5.0 evidence)", "",
               "Compare with `corrections-v0.5.0/` and `evidence/v0.5.0`. Sealed scores here use the already-known sealed-2 cases (retrospective).", "",
               "| condition | worlds | alloy | rejected use (missing component) | stale-reference rejections | mean final held best val / sealed-2 |", "|---|---|---|---|---|---|"]
        for c in sorted({r["condition"] for r in rows}):
            rs = [r for r in rows if r["condition"] == c and r["status"] == "completed"]
            vals = [r["final_held_best_validation"] for r in rs if r["final_held_best_validation"] is not None]
            sea = [r["final_held_best_sealed"] for r in rs if r["final_held_best_sealed"] is not None]
            md.append(f"| {c} | {len(rs)} | {sum(r.get('production.alloy', 0) for r in rs)} | {sum(r.get('production.rejected_use_missing_prerequisite', 0) for r in rs)} | "
                      f"{sum(r.get('search.stale_reference_rejections', 0) for r in rs)} | {round(sum(vals) / len(vals), 3) if vals else None} ({len(vals)}) / {round(sum(sea) / len(sea), 3) if sea else None} ({len(sea)}) |")
        md.append("")
    for name in ("production-v0.5.0-policy", "production-v0.5.0-teaching", "production-rerun", "production-allocation", "production-mentorship"):
        prod = load(root / "production" / f"{name}.json")
        if prod:
            md += [f"## Production accounting: {name}", "", "| pair (A -> B) | delta alloy | actions term | yield term | delta production actions | attributed: rejected production (missing component) | attributed: stale submissions |", "|---|---|---|---|---|---|---|"]
            for d in prod["decomposition"]:
                if "delta_alloy" in d:
                    md.append(f"| {d['pair'][0]} -> {d['pair'][1]} | {d['delta_alloy']} | {d['actions_term']} | {d['yield_term']} | {d['delta_production_actions']} | "
                              f"{d['attributed_by_event_class']['rejected production (missing component)']} | {d['attributed_by_event_class']['rejected submissions (stale reference)']} |")
            md.append("")
    speed = load(root / "benchmark" / "server-speed.json")
    if speed:
        md += ["## Achieved speed through the server clock (target 10 ticks/s)", "", "| base population | overlap | active agents | achieved ticks/s (median) | step ms (median) | max lag s |", "|---|---|---|---|---|---|"]
        md += [f"| {c['base_population']} | {c['overlap']} | {c['active_agents_seen']} | {c['achieved_ticks_per_second_median']} | {c['last_step_ms_median']} | {c['max_lag_seconds']} |" for c in speed["cases"]]
        md.append("")
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (root / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:80]))
