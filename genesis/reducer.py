"""Independent metrics: a reducer over an export's initial state and immutable tick events.

It deliberately does not import the engine, the world rules or `experiments.metrics`. It reconstructs every
holding from event fields alone and then cross-checks the reconstruction against the exported final state.
Ratios with a zero denominator are reported as unavailable, never as zero.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

JSON = dict[str, Any]
RESOURCES = ("food", "ore", "alloy")
ENERGY_CATEGORY = {
    "move": "travel", "gather": "gathering", "produce": "production", "use_artifact": "production",
    "propose_artifact": "search", "test_artifact": "evaluation", "inspect_artifact": "learning",
    "transfer": "exchange", "offer_trade": "exchange", "accept_trade": "exchange", "send_message": "exchange",
    "deposit": "storage", "withdraw": "storage", "consume": "eating", "wait": "none",
    "submit_artifact": "evaluation", "offer_teaching": "teaching", "teach_step": "teaching", "abandon_session": "teaching",
    "accept_teaching": "instruction", "learn_step": "instruction", "practice_step": "practice",
}
PRODUCING = ("produce", "use_artifact", "practice_step")
SESSION_TIME = ("teach_step", "learn_step", "practice_step")


def ratio(numerator: float, denominator: float, unit: str) -> JSON:
    if not denominator:
        return {"value": None, "status": "unavailable (zero denominator)", "numerator": numerator, "denominator": denominator, "unit": unit}
    return {"value": round(numerator / denominator, 6), "status": "available", "numerator": numerator, "denominator": denominator, "unit": unit}


class Window:
    """Committed ticks t with start < t <= end. Actions committed in tick t carry event tick t."""

    def __init__(self, start: int, end: int, label: str):
        self.start, self.end, self.label = start, end, label

    def __contains__(self, tick: int) -> bool:
        return self.start < tick <= self.end

    def describe(self) -> JSON:
        return {"label": self.label, "start_exclusive": self.start, "end_inclusive": self.end, "ticks": max(0, self.end - self.start)}


def _events(export: JSON) -> Iterable[tuple[JSON, JSON]]:
    for entry in export["ticks"]:
        record = entry["record"]
        for event in record["events"]:
            yield record, event


def reduce_export(export: JSON, windows: list[Window] | None = None) -> JSON:
    initial = export["initial"]
    origin = initial["tick"]
    last = export["ticks"][-1]["record"]["tick"] if export["ticks"] else origin
    holdings: dict[str, dict[str, int]] = defaultdict(lambda: {r: 0 for r in RESOURCES})
    status: dict[str, str] = {}
    home: dict[str, str] = {}
    for aid, a in initial["agents"].items():
        holdings[f"agent:{aid}"] = dict(a["inventory"])
        status[aid], home[aid] = a["status"], a["home"]
    for sid, s in initial["settlements"].items():
        holdings[f"settlement:{sid}"] = dict(s["inventory"])
    site_resource = {}
    for sid, s in initial["sites"].items():
        holdings[f"site:{sid}"][s["resource"]] = s["stock"]
        site_resource[sid] = s["resource"]
    ore_initial = sum(h["ore"] for h in holdings.values())
    removal_tick = None
    origin_artifacts = initial.get("artifacts", {})

    def initial_cohort(aid: str | None) -> int | None:
        art = origin_artifacts.get(aid or "")
        return art.get("cohort", 0) if art else None
    successors: dict[str, JSON] = {}
    windows = list(windows or [])

    def blank() -> JSON:
        return {"produced_alloy": 0, "production_energy": 0, "energy": defaultdict(int), "proposals": 0, "verified": 0,
                "rejected_tests": 0, "revisions_verified": 0, "library_acquisitions": 0, "use_executions": 0,
                "uses_with_saving": 0, "independent_adoptions": 0, "active_agent_ticks": 0, "rejected_actions": 0,
                "accepted_actions": 0, "submissions": 0, "admitted": 0, "dev_tests": 0, "session_ticks": 0, "batch_busy_ticks": 0,
                "teaching_offers": 0, "acquisitions_by_teaching": 0, "failed_sessions": 0, "interrupted_sessions": 0}

    overall, per_window = blank(), {w.label: blank() for w in windows}
    per_agent: dict[str, JSON] = defaultdict(lambda: {"produced_alloy": 0, "production_energy": 0, "use_executions": 0, "uses_with_saving": 0,
                                                      "first_library_acquisition": None, "first_use_with_saving": None,
                                                      "first_acquisition_by_teaching": None})
    sessions: dict[str, JSON] = {}
    lineage: dict[str, JSON] = {}
    freezes: list[JSON] = []
    transitions: list[JSON] = []
    cohort_of: dict[str, int] = {aid: a.get("cohort", 0) for aid, a in initial["agents"].items()}

    def end_session(sid: str, stage: str, reason: str | None, tick: int, bs: list[JSON]) -> None:
        if sid in sessions and sessions[sid]["outcome"] is None:
            sessions[sid].update(outcome=stage, reason=reason, ended_tick=tick)
            for x in bs:
                if stage == "failed":
                    x["failed_sessions"] += 1
                elif stage in ("interrupted", "expired"):
                    x["interrupted_sessions"] += 1

    def buckets(tick: int) -> list[JSON]:
        return [overall] + [per_window[w.label] for w in windows if tick in w]

    def move(src: str, dst: str, resource: str, amount: int) -> None:
        holdings[src][resource] -= amount
        holdings[dst][resource] += amount

    for record, e in _events(export):
        tick = e["tick"]
        kind = e.get("kind")
        if e["type"] == "action_rejected":
            for b in buckets(tick):
                b["rejected_actions"] += 1
            continue
        if e["type"] == "action_accepted":
            r, agent = e["result"], f'agent:{e["agent"]}'
            for b in buckets(tick):
                b["accepted_actions"] += 1
                b["energy"][ENERGY_CATEGORY[kind]] += r.get("energy_charged", 0)
            if kind == "gather":
                move(f'site:{r["site"]}', agent, r["resource"], r["amount"])
            elif kind == "consume":
                holdings[agent]["food"] -= r["amount"]
            elif kind in PRODUCING:
                holdings[agent]["ore"] -= r["ore"]
                holdings[agent]["food"] -= r.get("food", 0)
                holdings[agent]["alloy"] += r["alloy"]
                for b in buckets(tick):
                    b["batch_busy_ticks"] += r.get("busy_ticks", 0)
                per_agent[e["agent"]]["produced_alloy"] += r["alloy"]
                per_agent[e["agent"]]["production_energy"] += r["energy"]
                for b in buckets(tick):
                    b["produced_alloy"] += r["alloy"]
                    b["production_energy"] += r["energy"]
                if kind == "use_artifact":
                    ev = r["evidence"]
                    saving = r["saving"] if "saving" in r else ev["energy"] < ev["baseline_energy"]
                    per_agent[e["agent"]]["use_executions"] += 1
                    per_agent[e["agent"]]["uses_with_saving"] += saving
                    if saving and per_agent[e["agent"]]["first_use_with_saving"] is None:
                        per_agent[e["agent"]]["first_use_with_saving"] = {"tick": tick, "event": e["id"], "artifact": r["artifact"],
                                                                          "energy": ev.get("energy"), "baseline_energy": ev.get("baseline_energy"),
                                                                          "cost_per_alloy": ev.get("cost_per_alloy"), "baseline_cost_per_alloy": ev.get("baseline_cost_per_alloy")}
                    if r.get("first_independent_use") in sessions:
                        sessions[r["first_independent_use"]]["first_independent_use_tick"] = tick
                    if r["artifact"] in lineage:
                        lineage[r["artifact"]]["world_executions"] += 1
                        lineage[r["artifact"]]["executions_with_saving"] += bool(saving)
                    for b in buckets(tick):
                        b["use_executions"] += 1
                        b["uses_with_saving"] += saving
                        b["independent_adoptions"] += bool(r.get("independent_adoption"))
            elif kind == "transfer":
                target = f'agent:{r["target"]}' if f'agent:{r["target"]}' in holdings else f'settlement:{r["target"]}'
                move(agent, target, r["resource"], r["amount"])
            elif kind == "accept_trade":
                maker = f'agent:{r["maker"]}'
                move(maker, agent, r["give"], r["give_amount"])
                move(agent, maker, r["want"], r["want_amount"])
            elif kind == "deposit":
                move(agent, f'settlement:{r["settlement"]}', r["resource"], r["amount"])
            elif kind == "withdraw":
                move(f'settlement:{r["settlement"]}', agent, r["resource"], r["amount"])
            elif kind == "propose_artifact":
                for b in buckets(tick):
                    b["proposals"] += 1
                if "origin" in r:
                    parent = r.get("parent")
                    lineage[r["artifact"]] = {"artifact": r["artifact"], "creator": e["agent"], "cohort": r.get("cohort", cohort_of.get(e["agent"], 0)),
                                              "parent": parent, "parent_cohort": lineage.get(parent, {}).get("cohort", initial_cohort(parent)) if parent else None,
                                              "sources": r.get("sources", []), "origin": r["origin"], "generation": r.get("generation"),
                                              "proposed_tick": tick, "dev_score": None, "admitted": None, "admitted_tick": None,
                                              "world_executions": 0, "executions_with_saving": 0, "search_energy": r.get("energy_charged", 0),
                                              "evaluation_energy": 0}
            elif kind == "test_artifact" and r.get("role") == "development":
                for b in buckets(tick):
                    b["dev_tests"] += 1
                if r["artifact"] in lineage and lineage[r["artifact"]]["creator"] == e["agent"] and lineage[r["artifact"]]["dev_score"] is None:
                    lineage[r["artifact"]].update(dev_score=r.get("dev_score"))
                    lineage[r["artifact"]]["evaluation_energy"] += r.get("energy_charged", 0)
            elif kind == "test_artifact":
                for b in buckets(tick):
                    b["verified" if r["status"] == "verified" else "rejected_tests"] += 1
                    b["revisions_verified"] += bool(r.get("supersedes"))
            elif kind == "submit_artifact":
                for b in buckets(tick):
                    b["submissions"] += 1
                    b["admitted"] += bool(r.get("admitted"))
                    b["revisions_verified"] += bool(r.get("supersedes"))
                if r["artifact"] in lineage:
                    lineage[r["artifact"]].update(admitted=bool(r.get("admitted")), admitted_tick=tick if r.get("admitted") else None)
                    lineage[r["artifact"]]["evaluation_energy"] += r.get("energy_charged", 0)
            elif kind == "offer_teaching":
                sessions[r["session"]] = {"session": r["session"], "teacher": r["teacher"], "learner": r["learner"], "artifact": r["artifact"],
                                          "offered_tick": tick, "accepted_tick": None, "instruction_done_tick": None, "practice": [],
                                          "acquired_tick": None, "outcome": None, "reason": None, "ended_tick": None,
                                          "teacher_energy": r.get("energy_charged", 0), "learner_energy": 0, "teacher_ticks": 1, "learner_ticks": 0,
                                          "first_independent_use_tick": None}
                for b in buckets(tick):
                    b["teaching_offers"] += 1
            if kind in ("accept_teaching", "teach_step", "learn_step", "practice_step", "abandon_session") and r.get("session") in sessions:
                se = sessions[r["session"]]
                role = r.get("role")
                if role:
                    se[f"{role}_energy"] += r.get("energy_charged", 0)
                    se[f"{role}_ticks"] += 1
                if kind == "accept_teaching":
                    se["accepted_tick"] = tick
                    if r.get("stage") == "failed":
                        end_session(r["session"], "failed", r.get("reason"), tick, buckets(tick))
                if kind in SESSION_TIME:
                    for b in buckets(tick):
                        b["session_ticks"] += 1
                if kind in ("teach_step", "learn_step") and r.get("stage") == "practice" and se["instruction_done_tick"] is None:
                    se["instruction_done_tick"] = tick
                if kind == "practice_step":
                    se["practice"].append(r["practice"])
                    if r.get("stage") == "acquired":
                        se["acquired_tick"] = tick
                        end_session(r["session"], "acquired", None, tick, buckets(tick))
                        for b in buckets(tick):
                            b["acquisitions_by_teaching"] += 1
                        if per_agent[e["agent"]]["first_acquisition_by_teaching"] is None:
                            per_agent[e["agent"]]["first_acquisition_by_teaching"] = {"tick": tick, "session": r["session"], "artifact": se["artifact"]}
                    elif r.get("stage") == "failed":
                        end_session(r["session"], "failed", "practice outcome costlier than the baseline", tick, buckets(tick))
                if kind == "abandon_session":
                    end_session(r["session"], r.get("stage", "interrupted"), r.get("reason"), tick, buckets(tick))
            elif kind == "inspect_artifact":
                if per_agent[e["agent"]]["first_library_acquisition"] is None:
                    per_agent[e["agent"]]["first_library_acquisition"] = {"tick": tick, "event": e["id"], "artifact": r["artifact"]}
                for b in buckets(tick):
                    b["library_acquisitions"] += 1
        elif e["type"] == "agent_inactive":
            status[e["agent"]] = "inactive"
        elif e["type"] == "session_ended":
            end_session(e["session"], e["stage"], e.get("reason"), tick, buckets(tick))
        elif e["type"] == "freeze":
            freezes.append({k: e.get(k) for k in ("tick", "cohort", "reason", "rule", "cohort_best", "accessible_best")})
        elif e["type"] == "cohort_transition":
            transitions.append({"tick": tick, "cohort": e["cohort"], "retired": e["retired"], "successors": [x["successor"] for x in e["successors"]]})
            for m in e["inventory_moved"]:
                for res, n in m["inventory"].items():
                    move(f'agent:{m["agent"]}', f'settlement:{m["to"]}', res, n)
                status[m["agent"]] = "retired"
            for x in e["successors"]:
                holdings[f'agent:{x["successor"]}'] = dict(x["inventory"])
                status[x["successor"]], home[x["successor"]] = "active", x["home"]
                cohort_of[x["successor"]] = e["cohort"]
        elif e["type"] == "lifecycle_removal":
            removal_tick = tick
            for m in e["inventory_moved"]:
                for res, n in m["inventory"].items():
                    move(f'agent:{m["agent"]}', f'settlement:{m["to"]}', res, n)
                status[m["agent"]] = "retired"
            for s in e.get("successors", []):
                holdings[f'agent:{s["successor"]}'] = dict(s["inventory"])
                status[s["successor"]], home[s["successor"]] = "active", s["home"]
                successors[s["successor"]] = s
                cohort_of[s["successor"]] = cohort_of.get(s["predecessor"], 0)
        elif e["type"] == "environment":
            for food in e["food_sources"]:
                holdings[f'site:{food["site"]}'][site_resource[food["site"]]] += food["amount"]
            for b in buckets(tick):
                b["energy"]["fatigue"] += sum(e.get("fatigue", {}).values())
    # Active-agent ticks: decisions with an observation are one per active agent per committed tick.
    for entry in export["ticks"]:
        record = entry["record"]
        n = sum(1 for d in record["decisions"] if d.get("observation_hash"))
        for b in buckets(record["tick"]):
            b["active_agent_ticks"] += n

    def summarize(b: JSON) -> JSON:
        energy = dict(b["energy"])
        charged = sum(v for k, v in energy.items() if k not in ("fatigue",))
        return {**{k: v for k, v in b.items() if k != "energy"},
                "energy_by_category": energy, "charged_action_energy": charged, "total_energy_including_fatigue": charged + energy.get("fatigue", 0),
                "production_energy_per_alloy": ratio(b["production_energy"], b["produced_alloy"], "energy per produced alloy"),
                "charged_energy_per_alloy": ratio(charged, b["produced_alloy"], "all action-charged energy per produced alloy"),
                "total_energy_per_alloy": ratio(charged + energy.get("fatigue", 0), b["produced_alloy"], "action energy plus fatigue per produced alloy")}

    def ore_split() -> JSON:
        accessible, inaccessible = defaultdict(int), defaultdict(int)
        members = defaultdict(int)
        for aid, st in status.items():
            if st == "active":
                members[home[aid]] += 1
        for owner, h in holdings.items():
            kind, name = owner.split(":", 1)
            ok = (kind == "site" or (kind == "agent" and status.get(name) == "active")
                  or (kind == "settlement" and members[name] > 0))
            for res in ("ore", "food"):
                (accessible if ok else inaccessible)[res] += h[res]
        return {"accessible": dict(accessible), "inaccessible": dict(inaccessible),
                "rule": "sites, active agents, and settlement storage with at least one active member are accessible"}

    final = export.get("state")
    reconciliation = None
    if final is not None:
        expected = {**{f"agent:{k}": v["inventory"] for k, v in final["agents"].items()},
                    **{f"settlement:{k}": v["inventory"] for k, v in final["settlements"].items()},
                    **{f"site:{k}": {r: (v["stock"] if v["resource"] == r else 0) for r in RESOURCES} for k, v in final["sites"].items()}}
        mismatches = [k for k in expected if dict(expected[k]) != dict(holdings[k])]
        status_mismatch = [k for k, v in final["agents"].items() if status.get(k) != v["status"]]
        reconciliation = {"holdings_match_final_state": not mismatches, "mismatched_owners": mismatches[:10],
                          "statuses_match_final_state": not status_mismatch, "mismatched_statuses": status_mismatch[:10]}
    successor_rows = []
    for sid, s in successors.items():
        pa = per_agent[sid]
        successor_rows.append({"successor": sid, "predecessor": s["predecessor"], "policy": s["policy"], "role": s["role"],
                               "package": s["package"], "first_library_acquisition": pa["first_library_acquisition"],
                               "first_acquisition_by_teaching": pa["first_acquisition_by_teaching"],
                               "first_use_with_saving": pa["first_use_with_saving"], "use_executions": pa["use_executions"],
                               "uses_with_saving": pa["uses_with_saving"], "produced_alloy": pa["produced_alloy"],
                               "production_energy_per_alloy": ratio(pa["production_energy"], pa["produced_alloy"], "energy per produced alloy")})
    final_alloy_inventory = sum(h["alloy"] for h in holdings.values())
    return {
        "reducer": "genesis.reducer/1", "origin_tick": origin, "last_tick": last, "removal_tick": removal_tick,
        "units": {"energy": "integer energy points", "alloy": "units produced by produce/use_artifact events",
                  "window": "committed ticks t with start < t <= end"},
        "starting_inventory": "excluded from produced_alloy; produced_alloy counts only production events after origin_tick",
        "theoretical_max_alloy_from_initial_ore": ore_initial // 2, "ore_at_origin": ore_initial,
        "final_alloy_inventory": final_alloy_inventory,
        "overall": summarize(overall), "windows": {w.label: {**w.describe(), **summarize(per_window[w.label])} for w in windows},
        "remaining": ore_split(), "population": {"agents_ever": len(status), "active_at_end": sum(v == "active" for v in status.values()),
                                                 "retired_at_end": sum(v == "retired" for v in status.values()),
                                                 "inactive_at_end": sum(v == "inactive" for v in status.values())},
        "successors": successor_rows, "reconciliation": reconciliation,
        "sessions": list(sessions.values()), "freezes": freezes, "cohort_transitions": transitions,
        "lineage": list(lineage.values()),
        "cross_generation": {
            "revision_attempts": sum(1 for x in lineage.values() if x["parent_cohort"] is not None and x["cohort"] > x["parent_cohort"]),
            "admitted_revisions": sum(1 for x in lineage.values() if x["parent_cohort"] is not None and x["cohort"] > x["parent_cohort"] and x["admitted"]),
            "definition": "a proposal whose parent was created by an earlier cohort; admitted means it beat that parent on the same validation cases"},
        "agents": {aid: {"produced_alloy": v["produced_alloy"], "production_energy": v["production_energy"], "use_executions": v["use_executions"],
                         "uses_with_saving": v["uses_with_saving"]} for aid, v in sorted(per_agent.items())},
    }


def post_removal_window(export: JSON) -> Window | None:
    for _, e in _events(export):
        if e["type"] == "lifecycle_removal":
            last = export["ticks"][-1]["record"]["tick"]
            return Window(e["tick"], last, "post_removal")
    return None
