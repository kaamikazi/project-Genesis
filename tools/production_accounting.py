"""Production-cost accounting from events (genesis-metrics-1), for any experiment folder.

Usage: python tools/production_accounting.py REPORT_JSON OUT.json [COND_A COND_B ...pairs]
For each condition: agent-ticks by activity (accepted and rejected), production actions, alloy, alloy per action,
rejections by class, busy ticks, stale-submission rejections, base and peak population. For each requested pair
(A, B): the exact identity  alloy = actions x yield  split into an actions term and a yield term, and the
difference in agent-ticks per activity (which sums to the difference in active agent-ticks). The identity is exact;
WHY agents spent their ticks differently is attributed only where an event class shows it (e.g. rejected production
for a missing component); everything else is listed as an unexplained shift, not guessed.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from genesis.reducer import dictionary_metrics


def main(report_path: Path, out: Path, pairs: list[tuple[str, str]]) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    folder = report_path.parent
    agg: dict[str, Counter] = defaultdict(Counter)
    activity: dict[str, Counter] = defaultdict(Counter)
    rejections: dict[str, Counter] = defaultdict(Counter)
    pop: dict[str, list] = defaultdict(list)
    worlds = Counter()
    for item in report["worlds"]:
        if item["status"] != "completed":
            continue
        export = json.loads(gzip.decompress((folder / item["export"]["file"]).read_bytes()))
        m = dictionary_metrics(export)
        c = item["condition"]
        worlds[c] += 1
        for k in ("production.actions", "production.alloy", "production.busy_ticks", "production.rejected_use_missing_prerequisite",
                  "search.stale_reference_rejections", "search.credit_actions"):
            agg[c][k] += m[k] or 0
        activity[c].update(m["time.agent_ticks_by_activity"])
        rejections[c].update(m["rejections_by_class"])
        pop[c].append((m["population.base"], m["population.peak_active"]))
    rows = {}
    for c in agg:
        actions, alloy = agg[c]["production.actions"], agg[c]["production.alloy"]
        rows[c] = {"worlds": worlds[c], **dict(agg[c]), "alloy_per_action": round(alloy / actions, 4) if actions else None,
                   "agent_ticks_by_activity": dict(sorted(activity[c].items())), "active_agent_ticks": sum(activity[c].values()),
                   "top_rejections": dict(rejections[c].most_common(8)),
                   "population_base_peak": sorted(set(pop[c]))}
    decomposition = []
    for a, b in pairs:
        if a not in rows or b not in rows:
            decomposition.append({"pair": [a, b], "status": "unavailable (condition missing)"})
            continue
        ra, rb = rows[a], rows[b]
        ya = ra["production.alloy"] / ra["production.actions"] if ra["production.actions"] else 0       # exact, unrounded
        yb = rb["production.alloy"] / rb["production.actions"] if rb["production.actions"] else 0
        d_alloy = rb["production.alloy"] - ra["production.alloy"]
        actions_term = (rb["production.actions"] - ra["production.actions"]) * ya
        yield_term = rb["production.actions"] * (yb - ya)
        shift = {k: rb["agent_ticks_by_activity"].get(k, 0) - ra["agent_ticks_by_activity"].get(k, 0)
                 for k in sorted(set(ra["agent_ticks_by_activity"]) | set(rb["agent_ticks_by_activity"]))}
        attributed = {"rejected production (missing component)": rb["production.rejected_use_missing_prerequisite"] - ra["production.rejected_use_missing_prerequisite"],
                      "rejected submissions (stale reference)": rb["search.stale_reference_rejections"] - ra["search.stale_reference_rejections"]}
        decomposition.append({"pair": [a, b], "delta_alloy": d_alloy, "actions_term": round(actions_term, 2), "yield_term": round(yield_term, 2),
                              "identity_check": round(actions_term + yield_term - d_alloy, 6),
                              "delta_production_actions": rb["production.actions"] - ra["production.actions"],
                              "delta_agent_ticks_by_activity": shift, "delta_active_agent_ticks": rb["active_agent_ticks"] - ra["active_agent_ticks"],
                              "attributed_by_event_class": attributed,
                              "unexplained": "shifts between accepted activities (gathering, eating, search, learning, waiting) are reported, not attributed"})
    result = {"source": str(report_path), "metrics_version": "genesis-metrics-1", "conditions": rows, "decomposition": decomposition}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for d in decomposition:
        print(json.dumps({k: d[k] for k in d if k != "delta_agent_ticks_by_activity"}))


if __name__ == "__main__":
    args = sys.argv[3:]
    main(Path(sys.argv[1]), Path(sys.argv[2]), list(zip(args[::2], args[1::2])))
