"""Stored check (v0.5.1): interrupt during a pending submission and during declared mentorship; reopen and continue.

Usage: python tools/verify_restart_m5b.py OUT.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import tools.verify_restart_m5 as base

base.CONFIG = dict(seed=310, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, cohort_overlap=20,
                   teaching=True, teaching_policy="package-scheduled", search_policy="beam-alloc", budget_unit="credits", search_budget=48,
                   cross_cohort_access=False, max_ticks=80)


def main(out: Path) -> None:
    pending = lambda s: s["tick"] > 5 and any(a["status"] == "dev-tested" for a in s["artifacts"].values() if a.get("task") == "workshop-1")  # noqa: E731
    lesson = lambda s: s["tick"] >= 20 and any(x["stage"] in ("instruction", "practice") for x in s["sessions"].values())  # noqa: E731
    with tempfile.TemporaryDirectory() as tmp:
        checks = base.interrupted(Path(tmp), "pending", pending, "during a pending (development-tested, unsubmitted) candidate")
        checks += base.interrupted(Path(tmp), "mentor", lesson, "during declared mentorship (lesson in progress)")
    result = {"config": base.CONFIG, "checks": checks, "all_passed": all(c["passed"] for c in checks)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"all_passed": result["all_passed"], "checks": len(checks)}))
    if not result["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
