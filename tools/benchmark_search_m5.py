"""Controller CPU per decision and per proposal, by search policy (wall time stays out of the hashed records).

Usage: python tools/benchmark_search_m5.py OUT.json [seeds...]
Each policy runs the same cohort world; the controller's propose() is timed around every call. Timing varies with
the machine and load; it is reported with the platform and is not part of any experimental comparison.
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from pathlib import Path

from genesis.controllers import OfflineController
from genesis.engine import advance
from genesis.models import Scenario
from genesis.world import new_world

POLICIES = ("first-improvement", "beam", "beam-nocomponents")


class Timed(OfflineController):
    def __init__(self, seed: int):
        super().__init__(seed)
        self.samples: list[tuple[float, str | None]] = []

    def propose(self, observation):
        start = time.perf_counter()
        action = super().propose(observation)
        self.samples.append(((time.perf_counter() - start) * 1000, action.kind))
        return action


def main(out: Path, seeds: list[int]) -> None:
    rows = {}
    for policy in POLICIES:
        per_decision, per_proposal, run_seconds = [], [], []
        for seed in seeds:
            config = Scenario(seed=seed, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=60, cohort_count=3,
                              search_policy=policy, budget_unit="credits", search_budget=48, max_ticks=180)
            state, controller = new_world(config), Timed(config.controller_seed)
            start = time.perf_counter()
            for _ in range(config.max_ticks):
                state, _, _ = advance(state, controller)
            run_seconds.append(time.perf_counter() - start)
            per_decision += [ms for ms, _ in controller.samples]
            per_proposal += [ms for ms, kind in controller.samples if kind == "propose_artifact"]
        rows[policy] = {"decisions": len(per_decision), "proposals": len(per_proposal),
                        "mean_ms_per_decision": round(statistics.mean(per_decision), 4),
                        "mean_ms_per_proposal_decision": round(statistics.mean(per_proposal), 4) if per_proposal else None,
                        "p95_ms_per_proposal_decision": round(sorted(per_proposal)[int(0.95 * (len(per_proposal) - 1))], 4) if per_proposal else None,
                        "mean_run_seconds_180_ticks": round(statistics.mean(run_seconds), 2)}
    result = {"platform": platform.platform(), "python": platform.python_version(), "seeds": seeds, "policies": rows,
              "note": "controller wall time around propose(); proposal decisions are those whose chosen action was propose_artifact"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), [int(x) for x in sys.argv[2:]] or [300, 301])
