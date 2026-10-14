"""Milestone 5 calibration on development seeds only (300, 301, 302; never used for evaluation).

Usage: python tools/calibrate_m5.py OUT_DIR SETTINGS_JSON
Runs both protocols with the frozen settings and reports saturation (budget exhaustion), component activity, lesson
outcomes and parity. The tuning history that led to these settings is in evidence/v0.5.0/calibration/CALIBRATION_LOG.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from genesis.experiments5 import OverlapTeachingExperiment, PolicyExperiment

CALIBRATION_SEEDS = [300, 301, 302]


def brief(world: dict) -> dict:
    s = world.get("summary") or {}
    if not s:
        return {"seed": world["seed"], "condition": world["condition"], "status": world["status"], "failure": world.get("failure")}
    score = lambda pick: pick and round(pick["selection_score"], 3)  # noqa: E731
    return {"seed": world["seed"], "condition": world["condition"], "status": world["status"],
            "freezes": [(f["cohort"], score(f["cohort_best"]), score(f["accessible_best"]), score(f.get("held_best"))) for f in s["freezes"]],
            "stops": s["search"]["stop_reasons"], "proposals": s["search"]["proposals"], "admissions": s["search"]["admissions"],
            "refactor_admissions": s["search"]["refactor_admissions"], "components": s["components"]["admitted_by_origin"],
            "calling_workflow_admissions": s["components"]["calling_workflow_admissions"],
            "dependency_teaching": s["components"]["dependency_teaching"], "inherited": s["inherited"],
            "further_improvement": [(x["cohort"], x["improved_beyond_previous_held"]) for x in s["further_improvement"]]}


def main() -> None:
    out = Path(sys.argv[1])
    settings = json.loads(sys.argv[2])
    p = PolicyExperiment().run(CALIBRATION_SEEDS, str(out / "P"), settings, label="calibration")
    t = OverlapTeachingExperiment().run(CALIBRATION_SEEDS, str(out / "T"), settings, label="calibration")
    summary = {"settings": settings, "seeds": CALIBRATION_SEEDS, "P": [brief(w) for w in p["worlds"]], "P_parity": p.get("parity"),
               "T": [brief(w) for w in t["worlds"]], "T_parity": t.get("parity")}
    (out / "calibration-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"P": [(w["seed"], w["condition"], w.get("freezes")) for w in summary["P"]],
                      "T": [(w["seed"], w["condition"], w.get("freezes")) for w in summary["T"]]}, indent=1))


if __name__ == "__main__":
    main()
