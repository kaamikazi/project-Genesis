"""Print and save a compact per-world summary of Milestone 4 results (no new computation beyond the stored reports).

Usage: python tools/summarize_m4.py evidence/v0.4.0
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def main(root: Path) -> None:
    cum = json.loads((root / "cumulative" / "cumulative.json").read_text(encoding="utf-8"))
    sealed_path = root / "cumulative" / "sealed-results.json"
    sealed = json.loads(sealed_path.read_text(encoding="utf-8")) if sealed_path.exists() else {"worlds": []}
    rows = []
    for w in cum["worlds"]:
        s = next((x for x in sealed["worlds"] if x["seed"] == w["seed"] and x["condition"] == w["condition"]), {})
        row = {"seed": w["seed"], "condition": w["condition"], "status": w["status"]}
        if w["status"] == "completed":
            fz = s.get("freezes", [])
            row.update({
                "baseline_sealed": s.get("baseline_sealed", {}).get("score"),
                "cohort_best": [{"cohort": f["cohort"], "reason": f["reason"],
                                 "validation": f["cohort_best"]["selection_score"] if f.get("cohort_best") else None,
                                 "sealed": f["cohort_best"]["sealed"]["score"] if f.get("cohort_best") else None,
                                 "generation": f["cohort_best"]["generation"] if f.get("cohort_best") else None} for f in fz],
                "final_accessible": {"validation": fz[-1]["accessible_best"]["selection_score"], "sealed": fz[-1]["accessible_best"]["sealed"]["score"],
                                     "cohort": fz[-1]["accessible_best"]["cohort"], "generation": fz[-1]["accessible_best"]["generation"]} if fz and fz[-1].get("accessible_best") else None,
                "cross_generation": w["summary"]["cross_generation"],
                "levels": w["summary"]["first_tick_reaching_validation_level"],
                "per_cohort": [{k: c[k] for k in ("cohort", "proposals", "admitted", "cross_generation_attempts", "cross_generation_admitted", "search_energy", "evaluation_energy", "produced_alloy")}
                               | {"production_energy_per_alloy": c["production_energy_per_alloy"]["value"], "charged_energy_per_alloy": c["charged_energy_per_alloy"]["value"]}
                               for c in w["summary"]["per_cohort"]],
                "ore_left": w["summary"]["ore_on_sites_at_end"],
            })
        rows.append(row)
    agg = {}
    for cond in ("preserved", "reset"):
        done = [r for r in rows if r["condition"] == cond and r["status"] == "completed" and r.get("final_accessible")]
        final_sealed = [r["final_accessible"]["sealed"] for r in done]
        cohort2 = [next((c["sealed"] for c in r["cohort_best"] if c["cohort"] == 2 and c["sealed"] is not None), None) for r in done]
        agg[cond] = {"worlds": len(done), "mean_final_accessible_sealed": round(statistics.mean(final_sealed), 4) if final_sealed else None,
                     "final_accessible_sealed_by_world": final_sealed, "cohort2_created_best_sealed_by_world": cohort2,
                     "cross_generation_admitted_total": sum(r["cross_generation"]["admitted_revisions"] for r in done),
                     "cross_generation_attempts_total": sum(r["cross_generation"]["revision_attempts"] for r in done)}
    out = {"worlds": rows, "aggregates": agg, "parity": cum.get("parity"),
           "note": "mean of world values; worlds are the replication unit; exploratory (5 seeds)"}
    (root / "cumulative" / "summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
