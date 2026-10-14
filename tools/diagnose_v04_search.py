"""Retrospective diagnosis of why v0.4.0 searches stalled, from the stored Experiment B exports only.

Usage: python tools/diagnose_v04_search.py evidence/v0.4.0/cumulative docs/audit/v0.4-search-diagnosis.json
Reads export events and final artifact records (observer data). Nothing is fed back to any controller.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main(folder: Path, out: Path) -> None:
    report = json.loads((folder / "cumulative.json").read_text(encoding="utf-8"))
    rows, totals = [], Counter()
    for world in report["worlds"]:
        export = json.loads(gzip.decompress((folder / world["export"]["file"]).read_bytes()))
        state, budget = export["state"], export["state"]["config"]["search_budget"]
        arts = state["artifacts"]
        researchers = {aid: a for aid, a in state["agents"].items() if a["role"] == "researcher"}
        per = defaultdict(Counter)
        last_search_tick, life = {}, {}
        for entry in export["ticks"]:
            for d in entry["record"]["decisions"]:
                aid = d["action"]["agent"]
                if aid in researchers and d.get("observation_hash"):
                    per[aid]["active_ticks"] += 1
            for e in entry["record"]["events"]:
                aid = e.get("agent")
                if aid not in researchers or e.get("type") not in ("action_accepted", "action_rejected"):
                    continue
                k = e["kind"]
                per[aid][f"{k}:{'ok' if e['type'] == 'action_accepted' else 'rejected'}"] += 1
                if k in ("propose_artifact", "test_artifact", "submit_artifact") and e["type"] == "action_accepted":
                    last_search_tick[aid] = e["tick"]
        for aid, a in researchers.items():
            own = [x for x in arts.values() if x["creator"] == aid and x.get("kind") == "workflow"]
            dev_better_rejected = 0
            for x in own:
                parent = arts.get(x["parent"]) if x["parent"] else None
                dev, ref = (x.get("development") or {}).get("score"), (parent.get("development") or {}).get("score") if parent else None
                if x["status"] == "not-admitted" and dev is not None and (ref is None or dev < ref):
                    dev_better_rejected += 1
            submitted = [x for x in own if x["status"] in ("admitted", "not-admitted", "superseded")]
            exhausted = a["search_count"] >= budget
            start, end = a["created_tick"], a.get("retired_tick") or state["tick"]
            row = {"seed": world["seed"], "condition": world["condition"], "agent": aid, "cohort": a.get("cohort", 0),
                   "lifetime_ticks": end - start, "proposals": a["search_count"], "budget": budget, "budget_exhausted": exhausted,
                   "ticks_after_last_search_action": end - last_search_tick.get(aid, start),
                   "dev_tested_not_submitted": sum(1 for x in own if x["status"] == "dev-tested"),
                   "submitted": len(submitted), "admitted": sum(1 for x in own if x["status"] in ("admitted", "superseded")),
                   "not_admitted": sum(1 for x in own if x["status"] == "not-admitted"),
                   "dev_improvement_rejected_by_validation": dev_better_rejected,
                   "rejected_search_actions": sum(v for k, v in per[aid].items() if k.endswith(":rejected") and k.split(":")[0] in ("propose_artifact", "test_artifact", "submit_artifact"))}
            rows.append(row)
            totals["lifetimes"] += 1
            totals["budget_exhausted"] += exhausted
            totals["proposals"] += row["proposals"]
            totals["dev_tested_not_submitted"] += row["dev_tested_not_submitted"]
            totals["submitted"] += row["submitted"]
            totals["admitted"] += row["admitted"]
            totals["dev_improvement_rejected_by_validation"] += dev_better_rejected
            totals["idle_ticks_after_budget"] += row["ticks_after_last_search_action"] if exhausted else 0
    summary = {"lifetimes": totals["lifetimes"], "budget_exhausted_lifetimes": totals["budget_exhausted"],
               "proposals": totals["proposals"], "dev_tested_but_not_submitted": totals["dev_tested_not_submitted"],
               "submitted": totals["submitted"], "admitted": totals["admitted"],
               "dev_improvement_rejected_by_validation": totals["dev_improvement_rejected_by_validation"],
               "mean_ticks_left_after_budget_exhausted": round(totals["idle_ticks_after_budget"] / max(1, totals["budget_exhausted"]), 1)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "researcher_lifetimes": rows,
                               "limits": "v0.4 recorded neither search operators nor 'no candidate' decisions; neighbourhood exhaustion cannot be measured retrospectively"}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for r in rows[:12]:
        print(r)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
