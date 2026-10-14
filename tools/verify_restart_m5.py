"""Stored check: interrupt the process during overlap mentorship and during search, reopen, continue identically.

Usage: python tools/verify_restart_m5.py OUT.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from genesis.models import Scenario, digest
from genesis.storage import Store

CONFIG = dict(seed=101, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, cohort_overlap=15,
              teaching=True, teaching_policy="package", search_policy="beam", budget_unit="credits", search_budget=48,
              cross_cohort_access=False, max_ticks=80)


def interrupted(tmp: Path, name: str, condition, label: str) -> list[dict]:
    checks = []
    store = Store(tmp / f"{name}.sqlite")
    rid = store.create(Scenario(**CONFIG))
    state = None
    for _ in range(CONFIG["max_ticks"] - 20):
        state = store.step(rid)
        if condition(state):
            break
    checks.append({"check": f"{label}: condition holds at the interruption point", "passed": bool(condition(state)), "tick": state["tick"]})
    reference = Store(tmp / f"{name}-ref.sqlite")
    ref = reference.import_run(store.export(rid))
    del store
    reopened = Store(tmp / f"{name}.sqlite")
    checks.append({"check": f"{label}: reopened database holds the same committed state", "passed": digest(reopened.load(rid)) == digest(state)})
    a = b = None
    for _ in range(20):
        a, b = reopened.step(rid), reference.step(ref)
    checks.append({"check": f"{label}: continuation matches an uninterrupted reference for 20 ticks", "passed": digest(a) == digest(b), "tick": a["tick"]})
    replay = reopened.replay(rid, state["tick"])
    checks.append({"check": f"{label}: replay to the interruption tick restores sessions, credits and lifecycle",
                   "passed": digest(replay) == digest(state) and replay["sessions"] == state["sessions"]})
    return checks


def main(out: Path) -> None:
    mentorship = lambda s: s["tick"] >= 25 and any(x["stage"] in ("instruction", "practice") and s["agents"][x["teacher"]]["cohort"] != s["agents"][x["learner"]]["cohort"]
                                                   for x in s["sessions"].values())   # noqa: E731
    mentorship_any = lambda s: s["tick"] >= 25 and any(x["stage"] in ("instruction", "practice") for x in s["sessions"].values())  # noqa: E731
    search = lambda s: any(a["status"] == "proposed" for a in s["artifacts"].values() if a.get("task") == "workshop-1") and s["tick"] > 5  # noqa: E731
    with tempfile.TemporaryDirectory() as tmp:
        checks = interrupted(Path(tmp), "mentor", lambda s: mentorship(s) or mentorship_any(s), "during overlap mentorship")
        checks += interrupted(Path(tmp), "search", search, "during search (a proposal awaits its development test)")
    result = {"config": CONFIG, "checks": checks, "all_passed": all(c["passed"] for c in checks),
              "note": "the mentorship check interrupts at the first tick during the overlap with an active lesson (cross-generation when one exists)"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
