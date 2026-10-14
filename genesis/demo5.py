"""Deterministic demonstration fixture (v0.5): one component's path across a generational handoff.

LABEL: scripted demonstration, not an experiment. The scripted agents' actions are chosen by this file (submitted
overrides, recorded as such); the engine validates every one of them under the ordinary rules, and every other agent
runs the offline controller. Nothing here is evidence that the behaviour arises on its own; see the experiments for that.

Chain: an ancestor researcher extracts a component from its admitted workflow, has it admitted in-host, refactors the
workflow to call it (declared refactor admission path), teaches the workflow to its successor during the overlap
(dependency-aware lesson: the component is taught inside the session), retires at the boundary; the successor executes
the inherited workflow (component resolved by hash) and proposes a behaviour-changing revision of the component, which
receives an ordinary admission decision.
"""
from __future__ import annotations

from typing import Any

from . import workshop as ws
from .controllers import OfflineController
from .engine import advance
from .models import Action, JSON, Scenario
from .world import new_world

DEMO_LABEL = "deterministic scripted demonstration (not an experiment)"


def demo_config(seed: int = 101) -> Scenario:
    return Scenario(seed=seed, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=60, cohort_count=2, cohort_overlap=30,
                    teaching=True, teaching_policy="package", budget_unit="credits", search_budget=48, cross_cohort_access=False, max_ticks=120)


class _Driver:
    def __init__(self, config: Scenario):
        self.state = new_world(config)
        self.controller = OfflineController(config.controller_seed)
        self.scripted: set[str] = set()
        self.log: list[JSON] = []

    @property
    def tick(self) -> int:
        return self.state["tick"]

    def idle(self, aid: str) -> Action:
        a = self.state["agents"][aid]
        kind = "consume" if a["energy"] < 20 and a["inventory"]["food"] > 0 else "wait"
        return Action(id=f"demo-{self.tick}-{aid}-{kind}", agent=aid, tick=self.tick, kind=kind, params={})

    def step(self, actions: dict[str, Action] | None = None) -> list[JSON]:
        actions = dict(actions or {})
        for aid in self.scripted:
            if aid not in actions and self.state["agents"][aid]["status"] == "active":
                actions[aid] = self.idle(aid)
        self.state, events, _ = advance(self.state, self.controller, actions)
        return events

    def do(self, actions: dict[str, tuple[str, dict]], note: str = "", require: bool = True) -> dict[str, JSON]:
        for aid in actions:   # a batch occupies the agent; wait it out (recorded as waits)
            while self.state["agents"][aid].get("busy_until", 0) > self.tick:
                self.step()
        built = {aid: Action(id=f"demo-{self.tick}-{aid}-{kind}", agent=aid, tick=self.tick, kind=kind, params=params)
                 for aid, (kind, params) in actions.items()}
        events = self.step(built)
        out = {}
        for aid, action in built.items():
            ev = next(e for e in events if e.get("id") == action.id)
            if require and not ev["accepted"]:
                raise AssertionError(f"scripted action rejected: {aid} {action.kind}: {ev.get('reason')}")
            out[aid] = ev
            self.log.append({"tick": ev["tick"], "agent": aid, "action": action.kind, "accepted": ev["accepted"], "note": note,
                             **({"reason": ev["reason"]} if not ev["accepted"] else {}),
                             **{k: v for k, v in (ev.get("result") or {}).items() if k in (
                                 "artifact", "origin", "operator", "admitted", "admission_path", "status", "dev_score", "host_dev_score",
                                 "behavior_equal_to_host", "stage", "package", "already_known", "closure", "dependencies_acquired",
                                 "reference", "supersedes", "cost_per_alloy", "baseline_cost_per_alloy", "decision")}})
        return out

    def walk_to(self, aid: str, x: int, y: int, within: int = 0) -> None:
        for _ in range(60):
            a = self.state["agents"][aid]
            if abs(a["x"] - x) + abs(a["y"] - y) <= within:
                return
            options = []
            if a["x"] != x:
                options.append((a["x"] + (1 if x > a["x"] else -1), a["y"]))
            if a["y"] != y:
                options.append((a["x"], a["y"] + (1 if y > a["y"] else -1)))
            options += [(a["x"], a["y"] + 1), (a["x"], a["y"] - 1), (a["x"] + 1, a["y"]), (a["x"] - 1, a["y"])]
            for nx, ny in options:
                if 0 <= nx < self.state["config"]["width"] and 0 <= ny < self.state["config"]["height"] and self.state["terrain"][ny][nx] != "water":
                    self.do({aid: ("move", {"x": nx, "y": ny})}, "walk")
                    break
        raise AssertionError(f"{aid} could not reach ({x},{y})")

    def fetch(self, aid: str, resource: str, amount: int) -> None:
        a = self.state["agents"][aid]
        sites = sorted((s for s in self.state["sites"].values() if s["resource"] == resource and s["stock"] >= 4),
                       key=lambda s: (abs(s["x"] - a["x"]) + abs(s["y"] - a["y"]), s["id"]))
        site = sites[0]
        self.walk_to(aid, site["x"], site["y"], within=1)
        while self.state["agents"][aid]["inventory"][resource] < amount:
            self.do({aid: ("gather", {"site": site["id"]})}, f"gather {resource}")

    def rest(self, aid: str, energy: int) -> None:
        while self.state["agents"][aid]["energy"] < energy and self.state["agents"][aid]["inventory"]["food"] > 0:
            self.do({aid: ("consume", {})}, "eat")


def component_chain(seed: int = 101) -> JSON:
    d = _Driver(demo_config(seed))
    st = lambda: d.state  # noqa: E731
    # 1. Ordinary run until a cohort-0 researcher holds an admitted workflow with a branching field.
    ancestor = champion = field = None
    while d.tick < 28 and ancestor is None:
        d.step()
        for aid, a in sorted(st()["agents"].items()):
            if a["role"] != "researcher" or a.get("cohort", 0) != 0:
                continue
            mine = [st()["artifacts"][k] for k in a["known"] if st()["artifacts"][k].get("kind") == "workflow" and st()["artifacts"][k]["status"] == "admitted" and st()["artifacts"][k]["creator"] == aid]
            for art in sorted(mine, key=lambda x: x["validation"]["score"]):
                fields = [f for f in ws.FIELDS if art["content"]["program"][f]["op"] == "if_lt"]
                if fields:
                    ancestor, champion, field = aid, art["id"], fields[0]
                    break
            if ancestor:
                break
    if ancestor is None:
        raise AssertionError("no admitted branching workflow by tick 28")
    d.scripted.add(ancestor)
    found = {"tick": d.tick, "ancestor": ancestor, "workflow": champion, "field": field}
    host = st()["artifacts"][champion]["content"]["program"]
    # 2. Extraction: a component equal to the field (refactoring, not discovery), tested and admitted in-host.
    comp_program = {"op": "component", "field": field, "expr": host[field]}
    r = d.do({ancestor: ("propose_artifact", {"program": comp_program, "parent": None, "operator": f"extract:{field}"})}, "extract component")
    comp = r[ancestor]["result"]["artifact"]
    d.do({ancestor: ("test_artifact", {"artifact": comp, "host": champion})}, "component dev test inside host")
    d.do({ancestor: ("submit_artifact", {"artifact": comp})}, "component submission (no parent: host-with-component no worse than host)")
    # 3. Refactor the workflow to call the component; equal behaviour -> declared refactor admission path.
    refactor = {**host, field: {"op": "call", "artifact": comp}}
    r = d.do({ancestor: ("propose_artifact", {"program": refactor, "parent": champion, "operator": f"call:{field}"})}, "refactor workflow to call the component")
    wf = r[ancestor]["result"]["artifact"]
    d.do({ancestor: ("test_artifact", {"artifact": wf})}, "dev test of refactor")
    d.do({ancestor: ("submit_artifact", {"artifact": wf})}, "refactor submission")
    refactor_admitted = st()["artifacts"][wf]["status"] == "admitted"
    # 4. Overlap: the successor arrives 30 ticks before the boundary.
    while not st()["agents"][ancestor].get("successor"):
        d.step()
    successor = st()["agents"][ancestor]["successor"]
    d.scripted.add(successor)
    arrival_tick = d.tick
    d.fetch(successor, "food", 8)                            # practice needs inputs and energy; gathered under ordinary rules
    d.fetch(successor, "ore", 16)
    s = st()["agents"][successor]
    d.walk_to(ancestor, s["x"], s["y"], within=1)
    r = d.do({ancestor: ("offer_teaching", {"learner": successor, "artifact": wf})}, "offer dependency-aware lesson")
    session = r[ancestor]["result"]["session"]
    d.do({successor: ("accept_teaching", {"session": session})}, "accept: missing dependencies join the lesson package")
    while st()["sessions"][session]["stage"] == "instruction":
        d.do({ancestor: ("teach_step", {"session": session}), successor: ("learn_step", {"session": session})}, "instruction")
    while st()["sessions"][session]["stage"] == "practice":
        d.rest(successor, 24)
        d.do({successor: ("practice_step", {"session": session})}, "practice run")
    lesson = {k: st()["sessions"][session][k] for k in ("stage", "closure", "package", "already_known", "required_work", "costs", "assessment", "reason")}
    # 5. Boundary: the ancestor is frozen and retired on schedule.
    boundary = st()["config"]["cohort_ticks"]
    while d.tick < boundary:
        d.step()
    retired = st()["agents"][ancestor]["status"]
    # 6. The successor executes the inherited workflow; the call resolves to the component by hash.
    use = None
    if wf in st()["agents"][successor]["known"]:
        if st()["agents"][successor]["inventory"]["ore"] < 8:
            d.fetch(successor, "ore", 8)
        d.fetch(successor, "food", 4)
        d.rest(successor, 24)
        use = d.do({successor: ("use_artifact", {"artifact": wf})}, "successor executes inherited workflow")[successor]["result"]
    # 7. The successor proposes behaviour-changing revisions of the component and receives admission decisions.
    revisions = []
    if comp in st()["agents"][successor]["known"]:
        cands = [p for label, p, extra in ws.component_operators(st()["artifacts"][wf]["content"]["program"], {comp: comp_program})
                 if label == "mutate-component"]
        for cand in cands[:3]:
            d.rest(successor, 20)
            r = d.do({successor: ("propose_artifact", {"program": cand, "parent": comp, "operator": "mutate-component"})}, "successor revises the component")
            cid = r[successor]["result"]["artifact"]
            t = d.do({successor: ("test_artifact", {"artifact": cid, "host": wf})}, "revision dev test inside inherited host")[successor]["result"]
            entry = {"component": cid, "program": cand, "dev_score": t["dev_score"], "host_dev_score": t["host_dev_score"]}
            if t["dev_score"] is not None and t["host_dev_score"] is not None and t["dev_score"] < t["host_dev_score"]:
                sub = d.do({successor: ("submit_artifact", {"artifact": cid})}, "revision submission")[successor]["result"]
                entry.update(submitted=True, admitted=sub.get("admitted"))
            else:
                entry.update(submitted=False, reason="development score not better than the host with the current component")
            revisions.append(entry)
            if entry.get("admitted"):
                break
    rewired = None
    admitted_revision = next((r["component"] for r in revisions if r.get("admitted")), None)
    if admitted_revision:
        # 8. The successor's workflow calls the revised component (behaviour changes, so the ordinary strict admission applies).
        program = {**st()["artifacts"][wf]["content"]["program"], field: {"op": "call", "artifact": admitted_revision}}
        d.rest(successor, 20)
        r = d.do({successor: ("propose_artifact", {"program": program, "parent": wf, "operator": f"call:{field}"})}, "successor rewires workflow to the revised component")
        nwf = r[successor]["result"]["artifact"]
        t = d.do({successor: ("test_artifact", {"artifact": nwf})}, "dev test of rewired workflow")[successor]["result"]
        sub = d.do({successor: ("submit_artifact", {"artifact": nwf})}, "rewired workflow submission")[successor]["result"]
        rewired = {"workflow": nwf, "dev_score": t["dev_score"], "admitted": sub.get("admitted"), "admission_path": sub.get("admission_path", "improvement" if sub.get("admitted") else None),
                   "closure": st()["artifacts"][nwf].get("closure")}
    return {"label": DEMO_LABEL, "seed": seed, "config": demo_config(seed).model_dump(), "found": found,
            "component": {"id": comp, "program": comp_program, "status": st()["artifacts"][comp]["status"],
                          "transmissions": st()["artifacts"][comp]["transmissions"]},
            "refactored_workflow": {"id": wf, "admitted": refactor_admitted, "validation_path": (st()["artifacts"][wf].get("validation") or {}).get("admission_path"),
                                    "closure": st()["artifacts"][wf].get("closure"), "transmissions": st()["artifacts"][wf]["transmissions"]},
            "successor": successor, "arrival_tick": arrival_tick, "lesson": lesson, "ancestor_status_after_boundary": retired,
            "successor_execution": use and {k: use.get(k) for k in ("decision", "alloy", "energy", "cost_per_alloy", "baseline_cost_per_alloy", "saving")},
            "revisions": revisions, "rewired_workflow": rewired, "steps": d.log, "final_tick": d.tick}


def summary(result: JSON) -> dict[str, Any]:
    return {"refactor_admitted": result["refactored_workflow"]["admitted"], "lesson": result["lesson"]["stage"],
            "package": len(result["lesson"]["package"]), "ancestor": result["ancestor_status_after_boundary"],
            "successor_executed": result["successor_execution"] is not None, "revisions": [(r["submitted"], r.get("admitted")) for r in result["revisions"]],
            "rewired": result["rewired_workflow"] and result["rewired_workflow"]["admitted"]}
