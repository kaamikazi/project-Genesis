"""Search diagnosis for v0.5.0 experiment P (and T): how credits were allocated, how many evaluations were useful,
why searching paused or stopped, and how development, adaptive validation and fresh sealed performance relate.

Usage: python tools/diagnose_v05_search.py EVIDENCE_DIR OUT.json
Reads only stored exports, reducer files and sealed results; runs nothing.

Definitions (per researcher lifetime unless stated):
- credit actions: propose_artifact, test_artifact (development, incl. component tests), submit_artifact (accepted only)
- own-candidate test: development test of the agent's own proposal; re-test: development test of a held artifact it did not create
- novel evaluation: an own-candidate test whose behaviour hash (decisions on the 24 development cases) is new to that agent
- repeated evaluation result: an own-candidate test whose behaviour hash the agent had already observed (different program, same decisions)
- duplicate program: a proposal whose program hash the same agent had already proposed (content-identical program)
- energy pause: a maximal run of consecutive decisions with stop reason 'energy'; 'temporary' if the agent later took a
  credit action, 'sustained' if it never did again before its lifetime ended
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 4) if xs else None


def lifetimes(export: dict) -> dict:
    state = export["state"]
    researchers = {a: v for a, v in state["agents"].items() if v["role"] == "researcher"}
    end = state["tick"]
    life = {a: {"cohort": v.get("cohort", 0), "start": v["created_tick"], "end": v.get("retired_tick") or end,
                "credits": Counter(), "programs": set(), "duplicate_programs": 0, "behaviours": set(), "novel": 0, "repeated": 0,
                "pauses": [], "last_credit_tick": None, "stops": Counter(), "remaining_at_end": None, "submissions_dev_gain": []}
            for a, v in researchers.items()}
    creator = {}
    dev_score = {}
    for entry in export["ticks"]:
        rec = entry["record"]
        for e in rec["events"]:
            a = e.get("agent")
            if e.get("type") != "action_accepted" or a not in life:
                continue
            r, k, L = e["result"], e["kind"], life[a]
            if k == "propose_artifact" and "program_hash" in r:
                L["credits"]["propose"] += 1
                creator[r["artifact"]] = a
                if r["program_hash"] in L["programs"]:
                    L["duplicate_programs"] += 1
                L["programs"].add(r["program_hash"])
                L["last_credit_tick"] = e["tick"]
            elif k == "test_artifact" and r.get("role") == "development":
                own = creator.get(r["artifact"]) == a
                L["credits"]["component test" if "host" in r else "own-candidate test" if own else "re-test of held"] += 1
                L["last_credit_tick"] = e["tick"]
                dev_score[r["artifact"]] = r.get("dev_score")
                if own and "host" not in r:
                    if r["behavior_hash"] in L["behaviours"]:
                        L["repeated"] += 1
                    else:
                        L["novel"] += 1
                if r.get("behavior_hash"):
                    L["behaviours"].add(r["behavior_hash"])
            elif k == "submit_artifact":
                L["credits"]["submit"] += 1
                L["last_credit_tick"] = e["tick"]
        for d in rec["decisions"]:
            diag = d.get("diagnostic")
            a = d["action"]["agent"]
            if not diag or a not in life:
                continue
            L = life[a]
            L["remaining_at_end"] = diag.get("budget_remaining")
            if diag.get("stop"):
                L["stops"][diag["stop"]] += 1
            if diag.get("stop") == "energy":
                if L["pauses"] and L["pauses"][-1]["end"] == rec["tick"] - 1:
                    L["pauses"][-1]["end"] = rec["tick"]
                else:
                    L["pauses"].append({"start": rec["tick"], "end": rec["tick"]})
    for L in life.values():
        last = L["last_credit_tick"] or -1
        for p in L["pauses"]:
            p["kind"] = "temporary" if last > p["end"] else "sustained"
    return life


def summarise(exports: dict, sealed: dict, budget: int) -> dict:
    out = {}
    for cond, worlds in exports.items():
        lives = [L for w in worlds for L in w["life"].values()]
        credits = Counter()
        for L in lives:
            credits.update(L["credits"])
        total = sum(credits.values())
        pauses = [p for L in lives for p in L["pauses"]]
        temp = [p for p in pauses if p["kind"] == "temporary"]
        sust = [p for p in pauses if p["kind"] == "sustained"]
        unspent = [budget - sum(L["credits"].values()) for L in lives]
        out[cond] = {
            "lifetimes": len(lives), "credits_spent": total, "credits_available": budget * len(lives),
            "allocation": {k: credits[k] for k in ("propose", "own-candidate test", "re-test of held", "component test", "submit")},
            "allocation_share": {k: round(credits[k] / total, 4) for k in credits} if total else {},
            "novel_evaluations": sum(L["novel"] for L in lives), "repeated_evaluation_results": sum(L["repeated"] for L in lives),
            "novel_per_100_credits": round(100 * sum(L["novel"] for L in lives) / total, 2) if total else None,
            "duplicate_programs": sum(L["duplicate_programs"] for L in lives),
            "energy_pauses": {"temporary": len(temp), "temporary_ticks": sum(p["end"] - p["start"] + 1 for p in temp),
                              "sustained": len(sust), "sustained_ticks": sum(p["end"] - p["start"] + 1 for p in sust),
                              "lifetimes_ending_in_sustained_pause": sum(1 for L in lives if L["pauses"] and L["pauses"][-1]["kind"] == "sustained")},
            "unspent_credits": {"total": sum(unspent), "lifetimes_with_at_least_6_unspent": sum(1 for u in unspent if u >= 6),
                                "max": max(unspent) if unspent else None},
            "admissions": sum(w["reducer"]["search"]["admissions"] for w in worlds), "submissions": sum(w["reducer"]["search"]["submissions"] for w in worlds),
            "refactor_admissions": sum(w["reducer"]["search"]["refactor_admissions"] for w in worlds),
            "scores": score_rows(worlds, sealed.get(cond, {}))}
    return out


def score_rows(worlds: list, sealed: dict) -> dict:
    rows = []
    for w in worlds:
        final = w["reducer"]["freezes"][-1]
        pick = final.get("held_best")
        sw = sealed.get(w["seed"])
        s_pick = (sw["freezes"][-1].get("held_best") or {}) if sw else {}
        rows.append({"seed": w["seed"], "dev": pick and pick.get("dev_score"), "validation": pick and round(pick["selection_score"], 4),
                     "sealed": (s_pick.get("sealed") or {}).get("score"), "baseline_sealed": sw and sw["baseline_sealed"]["score"],
                     "creator_cohort": pick and pick["cohort"]})
    return {"per_world": rows, "mean_dev": mean(r["dev"] for r in rows), "mean_validation": mean(r["validation"] for r in rows),
            "mean_sealed": mean(r["sealed"] for r in rows),
            "mean_validation_minus_dev": mean((r["validation"] - r["dev"]) for r in rows if r["dev"] is not None and r["validation"] is not None),
            "mean_sealed_minus_validation": mean((r["sealed"] - r["validation"]) for r in rows if r["sealed"] is not None and r["validation"] is not None),
            "note": "final freeze held_best; dev = the creator's own development score; lower is better"}


def main(evidence: Path, out: Path) -> None:
    result = {}
    protocol = json.loads((evidence / "protocol" / "protocol.json").read_text(encoding="utf-8"))
    budget = protocol["settings"]["search_budget"]
    for folder in ("policy", "teaching"):
        report = json.loads((evidence / folder / f"{folder}.json").read_text(encoding="utf-8"))
        sealed_report = json.loads((evidence / folder / "sealed-results.json").read_text(encoding="utf-8")) if (evidence / folder / "sealed-results.json").exists() else {"worlds": []}
        sealed = defaultdict(dict)
        for s in sealed_report["worlds"]:
            if s.get("status") == "scored":
                sealed[s["condition"]][s["seed"]] = s
        exports = defaultdict(list)
        for item in report["worlds"]:
            if item["status"] != "completed":
                continue
            export = json.loads(gzip.decompress((evidence / folder / item["export"]["file"]).read_bytes()))
            tag = item["condition"].replace("/", "-")
            reducer = json.loads((evidence / folder / f"{item['seed']}-{folder}-{tag}.reducer.json").read_text(encoding="utf-8"))
            exports[item["condition"]].append({"seed": item["seed"], "life": lifetimes(export), "reducer": reducer})
        result[folder] = summarise(exports, sealed, budget)
    result["definitions"] = __doc__
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for folder in ("policy", "teaching"):
        for cond, s in result[folder].items():
            print(folder, cond.ljust(28), "credits", s["credits_spent"], "/", s["credits_available"], s["allocation"], "novel", s["novel_evaluations"],
                  "repeated", s["repeated_evaluation_results"], "dupProg", s["duplicate_programs"], "pauses", s["energy_pauses"], "unspent", s["unspent_credits"],
                  "scores", {k: v for k, v in s["scores"].items() if k.startswith("mean")})


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
