"""Milestone 4 calibration on development seeds only (100, 101, 103; hidden parameters differ from every evaluation seed).

Usage: python tools/calibrate_m4.py OUT_DIR [cohort_ticks ore_per_site search_budget checkpoint window]
Reports saturation, resource sufficiency and whether teaching sessions complete. Evaluation seeds are never run here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from genesis.experiments4 import CumulativeExperiment, TeachingExperiment

CALIBRATION_SEEDS = [100, 101, 103]


def main() -> None:
    out = Path(sys.argv[1])
    cohort_ticks, ore, budget, checkpoint, window = (int(x) for x in (sys.argv[2:7] if len(sys.argv) >= 7 else (60, 900, 16, 60, 60)))
    a = TeachingExperiment().run(CALIBRATION_SEEDS, str(out / "A"), checkpoint, window, ore, label="calibration")
    b = CumulativeExperiment().run(CALIBRATION_SEEDS, str(out / "B"), cohort_ticks, 3, ore, budget, label="calibration")
    summary = {"settings": {"cohort_ticks": cohort_ticks, "ore_per_site": ore, "search_budget": budget, "checkpoint": checkpoint, "window": window},
               "A": {k: {x: v[x] for x in ("acquired", "used_with_saving", "successors", "median_ticks_to_acquisition", "sessions_failed", "sessions_interrupted")}
                     for k, v in a["aggregates"].items()},
               "A_status": [(s["seed"], s["status"], s.get("physical_parity", {}).get("identical")) for s in a["seeds"]],
               "B": [{"seed": w["seed"], "condition": w["condition"], "status": w["status"],
                      "freeze_scores": [(f["cohort"], f["cohort_best"] and f["cohort_best"]["selection_score"], f["accessible_best"] and f["accessible_best"]["selection_score"])
                                        for f in w.get("summary", {}).get("freezes", [])],
                      "ore_left": w.get("summary", {}).get("ore_on_sites_at_end")} for w in b["worlds"]],
               "B_parity": b.get("parity")}
    (out / "calibration-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
