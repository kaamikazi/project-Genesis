"""M5c summaries: paired world-level differences with expected/completed/eligible/missing and distinct-parameter counts.

Usage: python tools/summarize_m5c.py EVIDENCE_DIR
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from tools.summarize_m5b import RULE, paired

ENDPOINTS = ["final_sealed", "final_selection_panel", "final_dev", "final_admission", "production_energy_per_alloy", "produced_alloy",
             "improvement_admissions", "failed_admissions", "submissions"]


def pair_table(rows: list[dict], a: str, b: str, key: str) -> dict:
    seeds = sorted({r["seed"] for r in rows})
    out = paired(rows, a, b, key, seeds, missing_reason=lambda r: "no final pick" if r.get("status") == "completed" else "world failed")
    combos = {r["seed"]: tuple(r["hidden_combo"]) for r in rows}
    out["distinct_parameter_combinations_expected"] = len({combos[s] for s in seeds})
    out["distinct_parameter_combinations_eligible"] = len({combos[p["seed"]] for p in out["pairs"]})
    out["differences_a_minus_b"] = [{"seed": p["seed"], "block": next(r["block"] for r in rows if r["seed"] == p["seed"]), "diff": round(p[a] - p[b], 4)} for p in out["pairs"]]
    diffs = [d["diff"] for d in out["differences_a_minus_b"]]
    out["median_difference"] = round(statistics.median(diffs), 4) if diffs else None
    return out


def rows_of(report: dict, sealed: dict) -> list[dict]:
    idx = {(w["block"], w["condition"]): w for w in sealed.get("worlds", []) if w.get("status") == "scored"}
    rows = []
    for w in report["worlds"]:
        r = {"block": w["block"], "seed": w["seed"], "condition": w["condition"], "status": w["status"], "hidden_combo": w["hidden_combo"],
             "shared_from": w.get("shared_from"), "failure": w.get("failure")}
        if w["status"] == "completed":
            s = w["summary"]
            pick = s["final_pick"]
            sw = idx.get((w["block"], w["condition"]))
            sealed_pick = (sw["freezes"][-1].get("selection_panel_best") or {}) if sw else {}
            q = s["panel_queries_per_researcher_panel"]
            r.update(final_sealed=(sealed_pick.get("sealed") or {}).get("score"), final_selection_panel=pick and pick["selection_panel_score"],
                     final_dev=pick and pick["dev_score"], final_admission=pick and pick["admission_score"], final_admission_partition=pick and pick["admission_partition"],
                     baseline_sealed=sw and sw["baseline_sealed"]["score"], production_energy_per_alloy=s["production_energy_per_alloy"], produced_alloy=s["produced_alloy"],
                     improvement_admissions=s["improvement_admissions"], refactor_admissions=s["refactor_admissions"], failed_admissions=s["failed_admissions"],
                     submissions=s["submissions"], panel_cap_hits=s["panel_cap_hits"], mean_queries_per_researcher_panel=round(statistics.mean(q), 2) if q else None,
                     selection_eligible=(s["selection_accounting"] or {}).get("eligible"), selection_truncated=(s["selection_accounting"] or {}).get("truncated"),
                     ore_left_fraction=s["ore_left_fraction"],
                     **{k: s["metrics"].get(k) for k in ("search.credit_actions", "search.own_candidate_tests", "search.repeated_decisions_own", "search.untested_proposals",
                                                          "search.novelty_rejected_candidates", "search.reserve_stops", "search.withdrawals_of_stale_candidates",
                                                          "search.stale_reference_rejections", "search.distinct_programs", "population.peak_active")})
            r["gap_sealed_minus_selection"] = None if r["final_sealed"] is None or r["final_selection_panel"] is None else round(r["final_sealed"] - r["final_selection_panel"], 4)
            r["gap_sealed_minus_dev"] = None if r["final_sealed"] is None or r["final_dev"] is None else round(r["final_sealed"] - r["final_dev"], 4)
        rows.append(r)
    return rows


def md_pairs(comps: list[dict]) -> list[str]:
    lines = ["| A vs B | metric | expected (distinct combos) | eligible (distinct) | A lower | B lower | ties | median A−B | mean A / B (eligible) | sign-test p (descr.) | missing | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in comps:
        miss = "; ".join(f"{m['seed']}: {m['reason']}" for m in c["missing"]) or "—"
        lines.append(f"| {c['a']} vs {c['b']} | {c['metric']} | {c['expected_worlds']} ({c['distinct_parameter_combinations_expected']}) | {c['eligible_pairs']} ({c['distinct_parameter_combinations_eligible']}) | "
                     f"{c['a_lower']} | {c['b_lower']} | {c['ties']} | {c['median_difference']} | {c['mean_a_over_eligible']} / {c['mean_b_over_eligible']} | {c['sign_test_p_descriptive']} | {miss} | {c['verdict']} |")
    return lines


def main(root: Path) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    summary, md = {}, ["# v0.5.2 (M5c) evidence summary (generated by tools/summarize_m5c.py)", "", f"Paired rule (descriptive): {RULE['text']}", ""]
    for name, title, pairs in (
        ("primary", "Primary: admission policy under preserved knowledge (endpoint: final pick, sealed-4)",
         [("first-improvement/panels", "first-improvement/fixed"), ("beam/panels", "beam/fixed"), ("beam/fixed", "first-improvement/fixed"), ("beam/panels", "first-improvement/panels")]),
        ("ablation", "Secondary: allocation leave-one-out (fixed admission, preserved; beam/fixed shared with the primary study)",
         [("beam-alloc/fixed", "beam/fixed"), ("beam-alloc-without-stale-frontier/fixed", "beam-alloc/fixed"), ("beam-alloc-without-reserve/fixed", "beam-alloc/fixed"),
          ("beam-alloc-without-novelty/fixed", "beam-alloc/fixed")])):
        path = root / name / f"{name}.json"
        if not path.exists():
            md += [f"## {title}", "", "**Not executed.** See the protocol and preflight for the reason.", ""]
            summary[name] = {"status": "not executed"}
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        sealed_path = root / name / "sealed-results.json"
        sealed = json.loads(sealed_path.read_text(encoding="utf-8")) if sealed_path.exists() else {"worlds": []}
        rows = rows_of(report, sealed)
        comps = [pair_table(rows, a, b, k) for a, b in pairs for k in ("final_sealed", "final_selection_panel", "production_energy_per_alloy")]
        conds = list(report["conditions"])
        keys = ["final_sealed", "final_selection_panel", "final_dev", "gap_sealed_minus_selection", "gap_sealed_minus_dev", "improvement_admissions", "failed_admissions",
                "submissions", "panel_cap_hits", "mean_queries_per_researcher_panel", "produced_alloy", "production_energy_per_alloy", "search.credit_actions",
                "search.repeated_decisions_own", "search.novelty_rejected_candidates", "search.reserve_stops", "search.withdrawals_of_stale_candidates", "selection_truncated"]

        def agg(c, k):
            vals = [r.get(k) for r in rows if r["condition"] == c and r["status"] == "completed" and isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)]
            return round(statistics.mean(vals), 3) if vals else None
        counts = {c: {"expected": sum(1 for r in rows if r["condition"] == c), "completed": sum(1 for r in rows if r["condition"] == c and r["status"] == "completed"),
                      "failed": sum(1 for r in rows if r["condition"] == c and r["status"] != "completed"),
                      "shared_from_primary": sum(1 for r in rows if r["condition"] == c and r.get("shared_from")),
                      "distinct_combinations": len({tuple(r["hidden_combo"]) for r in rows if r["condition"] == c})} for c in conds}
        means = {c: {k: agg(c, k) for k in keys} for c in conds}
        summary[name] = {"rows": rows, "comparisons": comps, "counts": counts, "means": means, "parity": report.get("parity")}
        md += [f"## {title}", "", "| condition | expected | completed | failed | shared from primary | distinct combinations |", "|---|---|---|---|---|---|"]
        md += [f"| {c} | {v['expected']} | {v['completed']} | {v['failed']} | {v['shared_from_primary']} | {v['distinct_combinations']} |" for c, v in counts.items()]
        md += [""] + md_pairs(comps) + ["", "| condition | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
        md += [f"| {c} | " + " | ".join(str(means[c][k]) for k in keys) + " |" for c in conds]
        md += ["", "| block | combo | " + " | ".join(conds) + " |", "|---" * (len(conds) + 2) + "|"]
        for b in sorted({r["block"] for r in rows}):
            cells = []
            for c in conds:
                r = next((x for x in rows if x["block"] == b and x["condition"] == c), None)
                cells.append("—" if r is None else f"FAILED" if r["status"] != "completed" else f"{r['final_selection_panel']} / {r['final_sealed']}")
            combo = next(x["hidden_combo"] for x in rows if x["block"] == b)
            md.append(f"| {b} | {combo} | " + " | ".join(cells) + " |")
        md += ["", "Cells: final pick's selection-panel score / sealed-4 score (lower is better).", ""]
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (root / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:60]))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
