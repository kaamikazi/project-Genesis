"""M5b calibration on development seeds 310-312 only (never used for evaluation; distinct from v0.5 calibration seeds).

Usage: python tools/calibrate_m5b.py OUT_DIR BASE_SETTINGS_JSON
Decision rules (declared here, before running):
1. Mentorship schedule. Candidates (cohort_ticks, overlap) = (60, 30), then (80, 40). Choose the FIRST candidate under
   which at least one cross-generation lesson whose workflow has a non-empty dependency closure is acquired across the
   three calibration seeds (teaching-only condition). If none qualifies, choose the last candidate and report that no
   dependency lesson completed in calibration. The chosen schedule is used for every mentorship condition.
2. Sample size. Estimate evaluation runtime as (allocation conditions + mentorship conditions) x N x mean world seconds
   x 1.2; choose the largest N in (10, 8, 6, 5) whose estimate is at most 45 minutes.
Nothing here is tuned on outcome quality; the allocation runs only check that every condition completes and measure cost.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from genesis.experiments5b import ALLOCATION_CONDITIONS, MENTORSHIP_CONDITIONS, AllocationExperiment, MentorshipExperiment

SEEDS = [310, 311, 312]
SCHEDULES = [(60, 30), (80, 40)]
SIZES = [10, 8, 6, 5]
RUNTIME_LIMIT_MIN = 45


class TeachingOnly(MentorshipExperiment):
    conditions = tuple(c for c in MENTORSHIP_CONDITIONS if c[0] == "teaching-only")


def dependency_lessons(report: dict) -> dict:
    offered = acquired = 0
    rows = []
    for w in report["worlds"]:
        for s in (w.get("summary") or {}).get("sessions", []):
            if s["closure"] and s["teacher_cohort"] < s["learner_cohort"]:
                offered += 1
                acquired += s["outcome"] == "acquired"
                rows.append({"seed": w["seed"], "outcome": s["outcome"], "reason": s["reason"], "offered_tick": s["offered_tick"], "package": len(s["package"])})
    return {"offered": offered, "acquired": acquired, "lessons": rows}


def main() -> None:
    out = Path(sys.argv[1])
    base = json.loads(sys.argv[2])
    decision: dict = {"seeds": SEEDS, "rules": __doc__, "schedules": []}
    seconds = []
    chosen = None
    for ticks, overlap in SCHEDULES:
        settings = {**base, "cohort_ticks": ticks, "cohort_overlap": overlap}
        rep = TeachingOnly().run(SEEDS, str(out / f"mentorship-{ticks}-{overlap}"), settings, label="calibration")
        seconds += [w["wall_seconds"] for w in rep["worlds"] if w["status"] == "completed"]
        lessons = dependency_lessons(rep)
        cross = sum(1 for w in rep["worlds"] for s in (w.get("summary") or {}).get("sessions", []) if s["teacher_cohort"] < s["learner_cohort"])
        decision["schedules"].append({"cohort_ticks": ticks, "overlap": overlap, "dependency_lessons": lessons, "cross_generation_lessons": cross,
                                      "failures": [w.get("failure") for w in rep["worlds"] if w["status"] != "completed"]})
        if chosen is None and lessons["acquired"] >= 1:
            chosen = (ticks, overlap)
    decision["chosen_schedule"] = {"cohort_ticks": (chosen or SCHEDULES[-1])[0], "overlap": (chosen or SCHEDULES[-1])[1],
                                   "qualified": chosen is not None,
                                   "note": "a dependency lesson was acquired under this schedule in calibration" if chosen else
                                           "no dependency lesson completed under any candidate; the longest candidate is used and this is reported"}
    alloc = AllocationExperiment().run(SEEDS, str(out / "allocation"), {**base, "cohort_ticks": 60, "cohort_overlap": 0}, label="calibration")
    seconds += [w["wall_seconds"] for w in alloc["worlds"] if w["status"] == "completed"]
    decision["allocation_check"] = {"failures": [(w["seed"], w["condition"], w.get("failure")) for w in alloc["worlds"] if w["status"] != "completed"],
                                    "novelty_rejections": {w["condition"]: w["summary"]["search"].get("stop_reasons") for w in alloc["worlds"] if w.get("summary")}}
    mean_s = statistics.mean(seconds)
    ticks_ratio = decision["chosen_schedule"]["cohort_ticks"] / 60
    per_n = (len(ALLOCATION_CONDITIONS) + len(MENTORSHIP_CONDITIONS) * ticks_ratio) * mean_s * 1.2 / 60
    n = next((k for k in SIZES if k * per_n <= RUNTIME_LIMIT_MIN), SIZES[-1])
    decision["sample_size"] = {"mean_world_seconds": round(mean_s, 1), "estimated_minutes_per_seed": round(per_n, 1), "chosen_n": n,
                               "estimated_total_minutes": round(n * per_n, 1)}
    (out / "calibration-decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print(json.dumps({k: decision[k] for k in ("chosen_schedule", "sample_size")}, indent=1))
    for sch in decision["schedules"]:
        print(sch["cohort_ticks"], sch["overlap"], "cross-gen lessons", sch["cross_generation_lessons"], "dependency", {k: sch["dependency_lessons"][k] for k in ("offered", "acquired")})


if __name__ == "__main__":
    main()
