"""v0.5: search credits and diagnostics, beam policy, components and closures, dependency-aware teaching,
overlapping generations, sealed-2 isolation, reducer reconciliation, restart and v0.4 regression."""
import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest

from genesis import workshop as ws
from genesis.controllers import OfflineController
from genesis.demo5 import component_chain
from genesis.engine import advance, attempt
from genesis.models import Action, Scenario, canonical, digest
from genesis.reducer import Window, reduce_export
from genesis.sealed import SealedEvaluator, create_manifest
from genesis.storage import Store
from genesis.world import LocalObservations, new_world

ROOT = Path(__file__).resolve().parent.parent
WF = {"op": "workflow", "batch": {"op": "if_lt", "measure": "ore", "threshold": 6, "then": {"op": "const", "value": 1}, "else": {"op": "const", "value": 2}},
      "heat": {"op": "if_lt", "measure": "humidity", "threshold": 3, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "mode": {"op": "if_lt", "measure": "phase", "threshold": 6, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "flux": {"op": "if_lt", "measure": "humidity", "threshold": 5, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}}}
H1, H2 = "1" * 64, "2" * 64
H = {k: k * 64 for k in "abcd"}
V05 = dict(task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, search_policy="beam", teaching_policy="package")


def act(state, kind, agent, suffix="", **params):
    return Action(id=f"v5-{state['tick']}-{agent}-{kind}{suffix}", agent=agent, tick=state["tick"], kind=kind, params=params)


def ok(state, kind, agent, **params):
    after, out = attempt(state, act(state, kind, agent, **params))
    assert out["accepted"], out
    return after, out["result"]


def nxt(state):
    state = deepcopy(state)
    state["tick"] += 1
    return state


def cohorts(**kw):
    return Scenario(seed=kw.pop("seed", 101), lifecycle="cohorts", cohort_ticks=kw.pop("cohort_ticks", 40), cohort_count=kw.pop("cohort_count", 2),
                    cohort_overlap=kw.pop("cohort_overlap", 15), max_ticks=kw.pop("max_ticks", 80), **{**V05, **kw})


@pytest.fixture(scope="module")
def demo():
    return component_chain(101)


# --- budgets and restricted feedback --------------------------------------------------------------

def test_search_credits_are_one_shared_pool_and_exhaustion_changes_nothing():
    state = new_world(Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=3, max_ticks=100))
    state, r = ok(state, "propose_artifact", "a00", program=WF, parent=None)
    state, _ = ok(nxt(state), "test_artifact", "a00", artifact=r["artifact"])
    state, _ = ok(nxt(state), "submit_artifact", "a00", artifact=r["artifact"])
    assert state["agents"]["a00"]["search_spent"] == 3
    state = nxt(state)
    after, out = attempt(state, act(state, "propose_artifact", "a00", program={**WF, "flux": {"op": "const", "value": 1}}, parent=None))
    assert not out["accepted"] and "credits exhausted" in out["reason"] and digest(after) == digest(state)


def test_proposal_budget_mode_is_unchanged_by_default():
    assert Scenario().budget_unit == "proposals" and Scenario().search_policy == "first-improvement" and Scenario().cohort_overlap == 0


def test_beam_observations_carry_no_validation_sealed_or_hidden_parameters():
    state = new_world(Scenario(seed=103, max_ticks=200, **V05))
    c = OfflineController(state["config"]["controller_seed"])
    for _ in range(45):
        state, _, decisions = advance(state, c)
    for aid in state["agents"]:
        obs = repr(LocalObservations().build(state, aid))
        assert "'validation': {" not in obs and "parent_score" not in obs and "selection_score" not in obs     # 'role': 'validation' is the one bit
        assert "sealed" not in obs and "flux_threshold" not in obs and "'split'" not in obs
    submitted = [a for a in state["artifacts"].values() if a.get("validation")]
    assert submitted, "the run should have submitted something"
    for a in submitted:
        own_view = LocalObservations().build(state, a["creator"])["artifacts"].get(a["id"], {})
        assert "selection_score" not in own_view and str(a["validation"]["score"]) not in repr(own_view.get("validation", ""))


def test_beam_decisions_record_diagnostics_with_operators_and_stops():
    state = new_world(Scenario(seed=101, max_ticks=200, **V05))
    c = OfflineController(state["config"]["controller_seed"])
    diags = []
    for _ in range(60):
        state, _, decisions = advance(state, c)
        diags += [d["diagnostic"] for d in decisions if d.get("diagnostic")]
    assert any(d.get("operator") for d in diags) and all(d["policy"] == "beam" for d in diags)
    json.dumps(diags, allow_nan=False)        # no non-finite numbers in records


# --- components, closures, limits ---------------------------------------------------------------

def test_extraction_preserves_behaviour_on_every_case():
    for label, comp, extra in ws.component_operators(WF, {}):
        cid = digest(comp)
        substituted = ws.substitute(WF, cid, comp)
        for cases in (ws.DEV_CASES, ws.VALIDATION_CASES):
            assert ws.behavior_hash(substituted, cases, {cid: comp}) == ws.behavior_hash(WF, cases, {})


def test_closure_is_transitive_ordered_and_rejects_missing_cycles_and_workflows():
    c1 = {"op": "component", "field": "heat", "expr": {"op": "const", "value": 1}}
    c2 = {"op": "component", "field": "heat", "expr": {"op": "if_lt", "measure": "phase", "threshold": 4, "then": {"op": "call", "artifact": H1}, "else": {"op": "const", "value": 2}}}
    host = {**WF, "heat": {"op": "call", "artifact": H2}}
    table = {H1: c1, H2: c2}
    assert ws.closure(host, table.get) == [H1, H2]
    with pytest.raises(ws.InvalidWorkflow, match="missing prerequisite"):
        ws.closure(host, {H2: c2}.get)
    looped = {H2: {**c2, "expr": {**c2["expr"], "then": {"op": "call", "artifact": H2}}}}
    with pytest.raises(ws.InvalidWorkflow, match="cyclic"):
        ws.closure(host, looped.get)
    with pytest.raises(ws.InvalidWorkflow, match="components"):
        ws.closure(host, {H2: WF}.get)
    with pytest.raises(ws.InvalidWorkflow, match="cyclic|step limit"):
        ws.execute(host, {"phase": 1, "humidity": 1, "ore": 9, "energy": 40}, looped)


def test_splitting_a_program_across_components_grants_no_extra_depth():
    leaf = {"op": "const", "value": 1}
    deep = leaf
    for _ in range(4):
        deep = {"op": "if_lt", "measure": "ore", "threshold": 3, "then": deep, "else": leaf}
    table = {H["a"]: {"op": "component", "field": "heat", "expr": deep}}
    prev = H["a"]
    for name in ("b", "c", "d"):
        table[H[name]] = {"op": "component", "field": "heat", "expr": {"op": "if_lt", "measure": "phase", "threshold": 4,
                                                                       "then": {"op": "call", "artifact": prev}, "else": leaf}}
        prev = H[name]
    for comp in table.values():
        ws.validate(comp)                                   # each artifact alone is within limits
    ws.check_closure_limits({**WF, "heat": {"op": "call", "artifact": H["b"]}}, table.get)
    with pytest.raises(ws.InvalidWorkflow, match="limit"):
        ws.check_closure_limits({**WF, "heat": {"op": "call", "artifact": H["d"]}}, table.get)
    with pytest.raises(ws.InvalidWorkflow, match="interface"):
        ws.check_closure_limits({**WF, "batch": {"op": "call", "artifact": H["a"]}}, table.get)


def test_engine_rejects_calls_to_components_the_proposer_does_not_hold():
    state = new_world(Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=100))
    after, out = attempt(state, act(state, "propose_artifact", "a00", program={**WF, "heat": {"op": "call", "artifact": "e" * 64}}, parent=None))
    assert not out["accepted"] and digest(after) == digest(state)


def test_calls_resolve_by_immutable_hash_after_a_revision_is_admitted(demo):
    comp = demo["component"]["id"]
    assert demo["component"]["status"] == "superseded"                       # the successor's revision replaced it
    assert demo["refactored_workflow"]["closure"] == [comp]                  # the ancestor's workflow still names the original hash
    revised = next(r["component"] for r in demo["revisions"] if r.get("admitted"))
    assert demo["rewired_workflow"]["closure"] == [revised] and revised != comp
    old = demo["component"]["program"]
    new = next(r["program"] for r in demo["revisions"] if r.get("admitted"))
    host = {**WF, old["field"]: {"op": "call", "artifact": comp}}
    m = {"phase": 7, "humidity": 2, "ore": 9, "energy": 40}
    assert ws.execute(host, m, {comp: old, revised: new})[0] == ws.execute(host, m, {comp: old})[0]


# --- dependency-aware teaching and overlap -------------------------------------------------------

def test_demonstration_chain_crosses_a_generation_with_the_dependency(demo):
    steps = demo["steps"]
    assert demo["label"].startswith("deterministic scripted demonstration")
    assert demo["refactored_workflow"]["admitted"] and demo["refactored_workflow"]["validation_path"] == "refactor"
    assert demo["lesson"]["stage"] == "acquired" and demo["lesson"]["package"] == [demo["component"]["id"]]
    assert demo["lesson"]["required_work"] == 6                              # root + one dependency, separately accounted
    vias = [t["via"] for t in demo["component"]["transmissions"]]
    assert "teaching session (dependency)" in vias
    assert demo["ancestor_status_after_boundary"] == "retired"
    lesson_end = max(s["tick"] for s in steps if s["action"] == "practice_step")
    assert lesson_end < demo["config"]["cohort_ticks"] <= min(s["tick"] for s in steps if s["action"] == "use_artifact")
    assert demo["successor_execution"] is not None
    assert any(r.get("admitted") for r in demo["revisions"]) and demo["rewired_workflow"]["admission_path"] == "improvement"


def test_strict_policy_rejects_missing_prerequisites_and_package_policy_teaches_them():
    from tests.test_teaching import classroom
    for policy in ("strict-prerequisites", "package", "package-scheduled"):
        state, teacher, learner, artifact = classroom()
        state["config"] = Scenario.model_validate({**state["config"], "teaching_policy": policy}).model_dump()
        comp = {"op": "component", "field": "heat", "expr": deepcopy(state["artifacts"][artifact]["content"]["program"]["heat"])}
        state["config"]["invention"] = "open"
        state, r = ok(state, "propose_artifact", teacher, program=comp, parent=None)
        cid = r["artifact"]
        state["artifacts"][cid]["status"] = "admitted"
        state["agents"][teacher]["known"].append(cid)
        program = {**state["artifacts"][artifact]["content"]["program"], "heat": {"op": "call", "artifact": cid}}
        state, r = ok(nxt(state), "propose_artifact", teacher, program=program, parent=artifact)
        wid = r["artifact"]
        state["artifacts"][wid]["status"] = "admitted"
        state["agents"][teacher]["known"].append(wid)
        state["config"]["invention"] = "frozen"
        state, r = ok(nxt(state), "offer_teaching", teacher, learner=learner, artifact=wid)
        sid = r["session"]
        assert r["closure"] == [cid]
        state, r = ok(nxt(state), "accept_teaching", learner, session=sid)
        if policy == "strict-prerequisites":
            assert r["stage"] == "failed" and "missing prerequisite" in state["sessions"][sid]["reason"]
            continue
        assert r["stage"] == "instruction" and r["package"] == [cid] and r["required_work"] == 6
        for _ in range(6):
            state = nxt(state)
            state, _ = ok(state, "teach_step", teacher, session=sid)
            state, _ = ok(state, "learn_step", learner, session=sid)
        assert state["sessions"][sid]["stage"] == "practice" and cid not in state["agents"][learner]["known"]


def test_retirement_is_not_delayed_by_an_unfinished_lesson_during_overlap():
    state = new_world(cohorts(teaching=True, cross_cohort_access=False))
    c = OfflineController(state["config"]["controller_seed"])
    while state["tick"] < 30:
        state, _, _ = advance(state, c)
    seniors = [a for a, x in state["agents"].items() if x["cohort"] == 0 and x["status"] == "active"]
    juniors = [a for a, x in state["agents"].items() if x["cohort"] == 1]
    assert len(juniors) == len(seniors) == 8                               # successors arrived at 40 - 15 = 25
    teacher = next(a for a in seniors if any(state["artifacts"][k].get("kind") == "workflow" for k in state["agents"][a]["known"]))
    wid = next(k for k in state["agents"][teacher]["known"] if state["artifacts"][k].get("kind") == "workflow")
    learner = next(j for j in juniors if state["agents"][j]["home"] == state["agents"][teacher]["home"] and wid not in state["agents"][j]["known"])
    for a in (teacher, learner):
        if state.get("sessions"):
            for s in state["sessions"].values():
                if s["stage"] in ("offered", "instruction", "practice") and a in (s["teacher"], s["learner"]):
                    s["stage"] = "interrupted"
        state["agents"][a].update(x=state["agents"][learner]["x"], y=state["agents"][learner]["y"], busy_until=0, energy=40)
    state, r = ok(state, "offer_teaching", teacher, learner=learner, artifact=wid)
    sid = r["session"]
    state, _ = ok(nxt(state), "accept_teaching", learner, session=sid)
    state["tick"] = 39
    nstate, events, _ = advance(state, c, {teacher: act(state, "wait", teacher), learner: act(state, "wait", learner)})
    assert nstate["tick"] == 40 and nstate["agents"][teacher]["status"] == "retired" and nstate["agents"][teacher]["retired_tick"] == 40
    nstate, events, _ = advance(nstate, c)
    assert nstate["sessions"][sid]["stage"] == "interrupted" and teacher in nstate["sessions"][sid]["reason"]


def test_overlap_lifecycle_records_arrival_then_retirement_and_no_hidden_inheritance():
    state = new_world(cohorts(cross_cohort_access=False, teaching=False))
    c = OfflineController(state["config"]["controller_seed"])
    for _ in range(80):
        state, _, _ = advance(state, c)
    phases = [(t["tick"], t["phase"]) for t in state["lifecycle"]["transitions"]]
    assert phases == [(25, "arrival"), (40, "retirement")]
    early = {k for k, a in state["artifacts"].items() if a.get("cohort", 0) == 0}
    for aid, a in state["agents"].items():
        if a["cohort"] == 1:
            assert not set(a["known"]) & early and not set(a.get("dev_notes", {})) & early
            assert a["inheritance"]["memories_inherited"] == 0 and a["inheritance"]["package"] == []


def test_library_and_none_are_physically_identical_until_the_first_arrival(tmp_path):
    hashes = []
    for cross in (True, False):
        store = Store(tmp_path / f"p{cross}.sqlite")
        rid = store.create(cohorts(cross_cohort_access=cross, teaching=False))
        for _ in range(30):
            store.step(rid)
        s = json.loads(canonical(store.replay(rid, 25)))
        s["config"].pop("cross_cohort_access")
        for a in s["agents"].values():
            if a.get("inheritance"):
                a["inheritance"].pop("policy")
        hashes.append(digest(s))
    assert hashes[0] == hashes[1]


# --- final evaluation isolation ------------------------------------------------------------------

def test_sealed2_is_disjoint_from_dev_validation_and_sealed1(tmp_path):
    sealed1 = json.loads((ROOT / "evidence" / "v0.4.0" / "protected" / "sealed-manifest.json").read_text(encoding="utf-8"))
    m2 = create_manifest(tmp_path / "s2.json", "workshop-sealed-2", [sealed1])
    e1 = SealedEvaluator(ROOT / "evidence" / "v0.4.0" / "protected" / "sealed-manifest.json")
    e2 = SealedEvaluator(tmp_path / "s2.json")
    assert m2["disjoint_from"] == ["dev-24", "validation-24", "workshop-sealed-1"] and len(e2.cases) == 48
    assert not set(e2.cases) & (set(e1.cases) | set(ws.DEV_CASES) | set(ws.VALIDATION_CASES))
    tampered = json.loads((tmp_path / "s2.json").read_text(encoding="utf-8"))
    tampered["excludes"][0]["sealed_seed"] += 1
    (tmp_path / "s2.json").write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="commitment"):
        SealedEvaluator(tmp_path / "s2.json")


def test_frozen_closures_are_verified_by_hash_before_sealed_scoring(tmp_path):
    create_manifest(tmp_path / "s.json", "workshop-sealed-2")
    evaluator = SealedEvaluator(tmp_path / "s.json")
    store = Store(tmp_path / "f.sqlite")
    rid = store.create(Scenario(seed=101, task="workshop-1", lifecycle="cohorts", cohort_ticks=20, cohort_count=2, ore_per_site=900, max_ticks=40))
    for _ in range(40):
        store.step(rid)
    export = store.export(rid)
    assert evaluator.evaluate_closed_run(export)["version"] == "workshop-sealed-2"
    bad = deepcopy(export)
    pick = next(f for f in bad["state"]["lifecycle"]["freezes"] if f["cohort_best"])
    pick["cohort_best"]["closure"] = ["d" * 64]
    with pytest.raises(ValueError, match="closure"):
        evaluator.evaluate_closed_run(bad)


# --- reducer, restart, regression ----------------------------------------------------------------

def test_reducer_reconciles_search_components_and_sessions(tmp_path):
    store = Store(tmp_path / "r.sqlite")
    rid = store.create(cohorts(seed=103, teaching=True, cross_cohort_access=False, cohort_ticks=50, max_ticks=100, cohort_overlap=20))
    for _ in range(100):
        store.step(rid)
    export = store.export(rid)
    final = export["state"]
    red = reduce_export(export, [Window(0, 50, "cohort-0"), Window(50, 100, "cohort-1")])
    assert red["reconciliation"]["holdings_match_final_state"] and red["reconciliation"]["statuses_match_final_state"]
    created = [a for a in final["artifacts"].values() if a.get("task") == "workshop-1"]
    assert red["search"]["proposals"] == len(created) == len(red["lineage"])
    spent = {k: a.get("search_spent", 0) for k, a in final["agents"].items() if a.get("search_spent")}
    assert red["search"]["search_actions_by_agent"] == spent
    assert red["search"]["admissions"] == sum(1 for a in created if a["status"] in ("admitted", "superseded"))
    assert red["search"]["refactor_admissions"] == sum(1 for a in created if (a.get("validation") or {}).get("admission_path") == "refactor")
    assert len(red["sessions"]) == len(final["sessions"])
    assert [t["phase"] for t in red["cohort_transitions"]] == ["arrival", "retirement"]
    for s in red["sessions"]:
        assert s["outcome"] == final["sessions"][s["session"]]["stage"] or final["sessions"][s["session"]]["stage"] in ("offered", "instruction", "practice")


def test_restart_during_overlap_mentorship_or_search_continues_identically(tmp_path):
    store = Store(tmp_path / "x.sqlite")
    rid = store.create(cohorts(seed=101, teaching=True, cross_cohort_access=False))
    state = None
    for _ in range(40):
        state = store.step(rid)
        overlap = state["tick"] >= 25
        busy = any(s["stage"] in ("instruction", "practice") for s in state["sessions"].values())
        if overlap and busy:
            break
    reference = Store(tmp_path / "ref.sqlite")
    ref = reference.import_run(store.export(rid))
    del store
    reopened = Store(tmp_path / "x.sqlite")
    assert digest(reopened.load(rid)) == digest(state)
    for _ in range(15):
        a, b = reopened.step(rid), reference.step(ref)
    assert digest(a) == digest(b)
    assert digest(reopened.replay(rid, state["tick"])) == digest(state)


def test_v040_cumulative_world_reproduces_under_v050_defaults(tmp_path):
    """Re-run a stored v0.4.0 experiment-B world (default v0.5 options) and compare with its stored reducer output."""
    report = json.loads((ROOT / "evidence" / "v0.4.0" / "cumulative" / "cumulative.json").read_text(encoding="utf-8"))
    item = next(w for w in report["worlds"] if w["seed"] == 11 and w["condition"] == "preserved")
    stored = json.loads((ROOT / "evidence" / "v0.4.0" / "cumulative" / "11-B-preserved.reducer.json").read_text(encoding="utf-8"))
    store = Store(tmp_path / "v4.sqlite")
    rid = store.create(Scenario.model_validate(item["config"]))
    for _ in range(item["config"]["max_ticks"]):
        store.step(rid)
    now = reduce_export(store.export(rid), [Window(k * 60, (k + 1) * 60, f"cohort-{k}") for k in range(3)])
    for key in ("produced_alloy", "production_energy", "proposals", "submissions", "admitted", "dev_tests", "accepted_actions", "rejected_actions"):
        assert now["overall"][key] == stored["overall"][key], key
    assert now["overall"]["energy_by_category"] == stored["overall"]["energy_by_category"]
    assert [(f["cohort_best"] or {}).get("artifact") for f in now["freezes"]] == [(f["cohort_best"] or {}).get("artifact") for f in stored["freezes"]]
