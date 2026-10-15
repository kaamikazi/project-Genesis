"""Stored check (v0.5.2): interrupt a streams-1 world with admission panels, reopen, continue identically; RNG-source
fields and panel query state survive restart and replay.

Usage: python tools/verify_restart_m5c.py OUT.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import tools.verify_restart_m5 as base

base.CONFIG = dict(seed=5299, seed_scheme="streams-1", hidden_combo=[6, 1, 5], terrain_seed=424242, controller_seed=777777, task="workshop-1",
                   ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, validation_policy="cohort-panels", final_selection="selection-panel",
                   search_policy="beam", budget_unit="credits", search_budget=48, max_ticks=80)


def main(out: Path) -> None:
    panels = lambda s: s["tick"] > 45 and any(a.get("panel_queries") for a in s["agents"].values())  # noqa: E731
    pending = lambda s: s["tick"] > 5 and any(a["status"] == "dev-tested" for a in s["artifacts"].values() if a.get("task") == "workshop-1")  # noqa: E731
    with tempfile.TemporaryDirectory() as tmp:
        checks = base.interrupted(Path(tmp), "panels", panels, "after panel queries in the second cohort")
        checks += base.interrupted(Path(tmp), "pending", pending, "during a pending candidate")
    result = {"config": base.CONFIG, "checks": checks, "all_passed": all(c["passed"] for c in checks)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"all_passed": result["all_passed"], "checks": len(checks)}))
    if not result["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
