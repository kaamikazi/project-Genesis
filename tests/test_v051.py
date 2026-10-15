"""v0.5.1 (M5b): stale-reference repair, dependency-aware library copies, allocation bundle, exact novelty, creation-time
attribution, admission panels, declared mentorship, metric dictionary and paired denominators."""
import itertools
import json
import random
from copy import deepcopy
from pathlib import Path

import pytest

from genesis import workshop as ws
from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.metrics_dictionary import METRICS
from genesis.models import Action, Scenario, digest
from genesis.reducer import Window, reduce_export
from genesis.sealed import SealedEvaluator, create_manifest
from genesis.storage import Store
from genesis.world import LocalObservations, new_world

ROOT = Path(__file__).resolve().parent.parent
WF = {"op": "workflow", "batch": {"op": "if_lt", "measure": "ore", "threshold": 6, "then": {"op": "const", "value": 1}, "else": {"op": "const", "value": 2}},
      "heat": {"op": "if_lt", "measure": "humidity", "threshold": 3, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "mode": {"op": "if_lt", "measure": "phase", "threshold": 6, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "flux": {"op": "if_lt", "measure": "humidity", "threshold": 5, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}}}


def act(state, kind, agent, **params):
    return Action(id=f"t-{state['tick']}-{agent}-{kind}-{len(state['artifacts'])}", agent=agent, tick=state["tick"], kind=kind, params=params)


def ok(state, kind, agent, **params):
    after, out = attempt(state, act(state, kind, agent, **params))
    assert out["accepted"], out
    after = deepcopy(after)
    after["tick"] += 1
    return after, out["result"]


def stale_world(policy="beam", budget=48, **kw):
    """a00 holds a dev-tested candidate whose reference R was superseded by another agent's admission."""
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=budget, search_policy=policy, max_ticks=300, **kw)
    s = new_world(cfg)
    s, r = ok(s, "propose_artifact", "a00", program=WF, parent=None)
    ref = r["artifact"]
    s, _ = ok(s, "test_artifact", "a00", artifact=ref)
    s["artifacts"][ref]["status"] = "admitted"
    s["agents"]["a00"]["known"].append(ref)
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "flux": {"op": "const", "value": 0}}, parent=ref)
    pending = r["artifact"]
    s, _ = ok(s, "test_artifact", "a00", artifact=pending)
    s["artifacts"][pending]["development"]["score"] = 1.0
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "flux": {"op": "const", "value": 1}}, parent=ref)
    head = r["artifact"]
    s["artifacts"][head].update(status="admitted", creator="a01")
    s["artifacts"][ref].update(status="superseded", superseded_by=head)
    return s, pending, ref, head


# --- stale-reference contract and repair ---------------------------------------------------------------------

@pytest.mark.parametrize("policy", ["beam", "beam-alloc", "first-improvement"])
def test_stale_candidate_is_withdrawn_not_resubmitted(policy):
    s, pending, ref, head = stale_world(policy)
    if policy == "first-improvement":
        s["artifacts"][pending]["created_tick"] = s["tick"]        # make it the policy's latest own candidate
    obs = LocalObservations().build(s, "a00")
    assert obs["artifacts"][pending]["reference"] == ref and obs["artifacts"][pending]["reference_status"] == "superseded"
    c = OfflineController(s["config"]["controller_seed"])
    rejected, kinds = 0, []
    for _ in range(8):
        a = c.propose(LocalObservations().build(s, "a00"))
        kinds.append(a.kind)
        nxt, out = attempt(s, a)
        rejected += not out["accepted"]
        s = deepcopy(nxt)
        s["tick"] += 1
    assert rejected == 0 and "withdraw_artifact" in kinds and s["artifacts"][pending]["status"] == "withdrawn"
    assert kinds.count("submit_artifact") == 0 or s["artifacts"][pending]["status"] == "withdrawn"


def test_stale_submission_is_rejected_with_the_conflict_named_and_costs_nothing():
    s, pending, ref, head = stale_world()
    before = (s["agents"]["a00"]["search_spent"], s["agents"]["a00"]["energy"])
    after, out = attempt(s, act(s, "submit_artifact", "a00", artifact=pending))
    assert not out["accepted"] and "stale reference" in out["reason"] and ref[:12] in out["reason"] and head[:12] in out["reason"]
    assert digest(after) == digest(s) and (after["agents"]["a00"]["search_spent"], after["agents"]["a00"]["energy"]) == before


def test_named_reference_is_compare_and_swap():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, max_ticks=300)
    s = new_world(cfg)
    s, r = ok(s, "propose_artifact", "a00", program=WF, parent=None)
    cand = r["artifact"]
    s, _ = ok(s, "test_artifact", "a00", artifact=cand)
    after, out = attempt(s, act(s, "submit_artifact", "a00", artifact=cand, reference="f" * 64))
    assert not out["accepted"] and "reference conflict" in out["reason"] and digest(after) == digest(s)
    after, out = attempt(s, act(s, "submit_artifact", "a00", artifact=cand, reference=None))
    assert out["accepted"] and out["result"]["reference"] is None       # baseline rule, as named


def test_withdraw_is_free_creator_only_and_only_for_pending_candidates():
    s, pending, ref, head = stale_world()
    spent, energy = s["agents"]["a00"]["search_spent"], s["agents"]["a00"]["energy"]
    after, out = attempt(s, act(s, "withdraw_artifact", "a01", artifact=pending))
    assert not out["accepted"] and digest(after) == digest(s)
    after, out = attempt(s, act(s, "withdraw_artifact", "a00", artifact=head))
    assert not out["accepted"]                                          # not a pending candidate of a00
    s2, r = ok(s, "withdraw_artifact", "a00", artifact=pending)
    assert r["previous_status"] == "dev-tested" and s2["agents"]["a00"]["search_spent"] == spent and s2["agents"]["a00"]["energy"] == energy
    after, out = attempt(s2, act(s2, "submit_artifact", "a00", artifact=pending))
    assert not out["accepted"]                                          # withdrawn candidates cannot be submitted


def test_exhausted_credits_never_produce_a_resubmission_loop():
    s, pending, ref, head = stale_world(budget=48)
    s["agents"]["a00"]["search_spent"] = 48
    c = OfflineController(s["config"]["controller_seed"])
    for _ in range(6):
        a = c.propose(LocalObservations().build(s, "a00"))
        assert a.kind != "submit_artifact"
        nxt, out = attempt(s, a)
        s = deepcopy(nxt)
        s["tick"] += 1


def test_repeated_api_submissions_are_rejected_auditable_and_counted(tmp_path):
    store = Store(tmp_path / "r.sqlite")
    s, pending, ref, head = stale_world()
    rid = store.create(Scenario.model_validate(s["config"]), s)
    for i in range(3):
        st = store.load(rid)
        store.step(rid, {"a00": Action(id=f"api-{i}", agent="a00", tick=st["tick"], kind="submit_artifact", params={"artifact": pending})})
    events = [e for e in store.events(rid, limit=500) if e.get("agent") == "a00" and e["kind"] == "submit_artifact"]
    assert len(events) == 3 and all(e["type"] == "action_rejected" and e["params"] == {"artifact": pending} for e in events)
    red = reduce_export(store.export(rid))
    assert red["metrics"]["search.stale_reference_rejections"] == 3 and red["metrics"]["search.repeated_rejected_attempts"] == 2
    assert store.load(rid)["artifacts"][pending]["status"] == "dev-tested"


def test_retired_agent_cannot_resubmit_or_withdraw_and_restart_preserves_pending_state(tmp_path):
    store = Store(tmp_path / "p.sqlite")
    s, pending, ref, head = stale_world()
    rid = store.create(Scenario.model_validate(s["config"]), s)
    store.step(rid)
    state = store.load(rid)
    reopened = Store(tmp_path / "p.sqlite")
    assert reopened.load(rid)["artifacts"][pending] == state["artifacts"][pending]
    assert digest(reopened.replay(rid, state["tick"])) == digest(state)
    retired = deepcopy(state)
    retired["agents"]["a00"].update(status="retired", inventory={"food": 0, "ore": 0, "alloy": 0})
    for kind in ("submit_artifact", "withdraw_artifact"):
        after, out = attempt(retired, act(retired, kind, "a00", artifact=pending))
        assert not out["accepted"] and "not active" in out["reason"]


# --- dependency-aware library copies ------------------------------------------------------------------------

def component_world():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=300)
    s = new_world(cfg)
    comp = {"op": "component", "field": "heat", "expr": WF["heat"]}
    s, r = ok(s, "propose_artifact", "a00", program=comp, parent=None)
    cid = r["artifact"]
    s["artifacts"][cid]["status"] = "admitted"
    s["agents"]["a00"]["known"].append(cid)
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "heat": {"op": "call", "artifact": cid}}, parent=None)
    wid = r["artifact"]
    s["artifacts"][wid]["status"] = "admitted"
    s["agents"]["a00"]["known"].append(wid)
    for aid in ("a01",):
        s["agents"][aid].update(x=s["settlements"]["hearth"]["x"], y=s["settlements"]["hearth"]["y"], energy=40)
    return s, cid, wid


def test_library_copy_brings_the_missing_closure_at_separate_cost():
    s, cid, wid = component_world()
    e0 = s["agents"]["a01"]["energy"]
    s2, r = ok(s, "inspect_artifact", "a01", artifact=wid)
    assert r["dependencies_acquired"] == [cid] and {cid, wid} <= set(s2["agents"]["a01"]["known"])
    assert s2["agents"]["a01"]["energy"] == e0 - 4
    assert any(t["via"] == "settlement library (dependency)" for t in s2["artifacts"][cid]["transmissions"])


def test_library_copy_is_refused_when_a_dependency_is_not_in_the_library():
    s, cid, wid = component_world()
    s["artifacts"][cid]["status"] = "superseded"
    after, out = attempt(s, act(s, "inspect_artifact", "a01", artifact=wid))
    assert not out["accepted"] and "missing prerequisite" in out["reason"] and digest(after) == digest(s)
    obs = LocalObservations().build(s, "a01")
    assert obs["artifacts"][wid]["closure"] == [cid] and "program" not in obs["artifacts"][wid]


# --- allocation bundle and exact novelty --------------------------------------------------------------------

def test_exact_equivalence_matches_brute_force_on_random_expressions():
    rng = random.Random(5)

    def expr(depth):
        if depth == 0 or rng.random() < 0.3:
            return {"op": "const", "value": rng.randint(0, 3)}
        m = rng.choice(list(ws.MEASURES))
        return {"op": "if_lt", "measure": m, "threshold": rng.randint(0, 12), "then": expr(depth - 1), "else": expr(depth - 1)}
    grid = list(itertools.product(range(-2, 15), range(-2, 15), range(-2, 15), range(-2, 15)))[::7]
    for _ in range(300):
        a, b = expr(3), expr(3)
        if rng.random() < 0.3:
            b = {"op": "if_lt", "measure": "ore", "threshold": 9, "then": a, "else": a}      # equivalent by construction
        same, work = ws.field_equivalent(a, b, {})
        brute = all(ws._field_value(a, dict(zip(("phase", "humidity", "ore", "energy"), g)), {}) == ws._field_value(b, dict(zip(("phase", "humidity", "ore", "energy"), g)), {}) for g in grid)
        assert (not same) or brute            # equivalence is never claimed when some input differs
        if not brute:
            assert not same


def test_allocation_reserve_blocks_proposals_it_cannot_fund():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, search_policy="beam-alloc", max_ticks=300)
    s = new_world(cfg)
    s["agents"]["a00"]["search_spent"] = 46                 # 2 left: cannot fund propose + test + submit
    s["agents"]["a00"]["dev_notes"] = {"baseline": 14.0}
    c = OfflineController(cfg.controller_seed)
    a = c.propose(LocalObservations().build(s, "a00"))
    assert a.kind != "propose_artifact" and c.diagnostic and c.diagnostic.get("stop") == "reserve"
    s["agents"]["a00"]["search_spent"] = 0
    a = c.propose(LocalObservations().build(s, "a00"))
    assert a.kind == "propose_artifact"


def test_novelty_filter_accounts_its_work_and_uses_only_permitted_programs():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, search_policy="beam-alloc", max_ticks=300)
    s = new_world(cfg)
    s["agents"]["a00"]["dev_notes"] = {"baseline": 14.0}
    c = OfflineController(cfg.controller_seed)
    picks = []
    for _ in range(6):
        a = c.propose(LocalObservations().build(s, "a00"))
        if a.kind == "propose_artifact":
            assert {"novelty_examined", "novelty_rejected", "novelty_point_evaluations"} <= set(c.diagnostic)
            picks.append(a.params["program"])
        nxt, out = attempt(s, a)
        s = deepcopy(nxt)
        s["tick"] += 1
        if a.kind == "propose_artifact":
            aid = out["result"]["artifact"]
            s, _ = ok(s, "test_artifact", "a00", artifact=aid)
    for x, y in itertools.combinations(picks, 2):
        assert not ws.decision_equivalent(x, y, {})
    obs = LocalObservations().build(s, "a04")              # another settlement's researcher sees none of a00's programs
    assert not any("program" in v for v in obs["artifacts"].values() if v["creator"] == "a00")


# --- attribution, panels, final evaluation ------------------------------------------------------------------

def test_freeze_attributes_by_creation_not_by_who_holds_it():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, cohort_overlap=20,
                   budget_unit="credits", search_budget=48, search_policy="beam", max_ticks=80)
    s = new_world(cfg)
    c = OfflineController(cfg.controller_seed)
    for _ in range(40):
        s, _, _ = advance(s, c)
    f = s["lifecycle"]["freezes"][0]
    assert f["cohort"] == 0 and all(s["artifacts"][x]["cohort"] == 0 and s["artifacts"][x]["created_tick"] <= 40 for x in f["created_inventory"])
    assert f["created_upto_best"] is None or f["created_upto_best"]["cohort"] == 0
    # a junior-created workflow adopted by a senior may appear in held_best but never in the creation inventory
    junior = [x for x in s["artifacts"].values() if x.get("cohort") == 1]
    assert not set(f["created_inventory"]) & {x["id"] for x in junior}


def test_admission_panels_use_identical_current_cases_and_bound_queries():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, validation_policy="cohort-panels",
                   panel_queries=1, max_ticks=300)
    s = new_world(cfg)
    s, r = ok(s, "propose_artifact", "a00", program=WF, parent=None)
    first = r["artifact"]
    s, _ = ok(s, "test_artifact", "a00", artifact=first)
    s, r = ok(s, "submit_artifact", "a00", artifact=first)
    val = s["artifacts"][first]["validation"]
    assert val["partition"] == "panel-0"
    assert val["score"] == ws.score_cases(WF, ws.world_params(101), ws.panel_cases(0), {})["score"]
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "flux": {"op": "const", "value": 1}}, parent=None)
    s, _ = ok(s, "test_artifact", "a00", artifact=r["artifact"])
    after, out = attempt(s, act(s, "submit_artifact", "a00", artifact=r["artifact"]))
    assert not out["accepted"] and "allowance exhausted" in out["reason"]
    assert LocalObservations().build(s, "a00")["admission"] == {"policy": "cohort-panels", "panel": 0, "queries_used": 1, "queries_allowed": 1}
    panels = [set(ws.panel_cases(k)) for k in range(ws.PANEL_COUNT)]
    assert all(not a & b for a, b in itertools.combinations(panels, 2)) and not ws.all_panel_cases() & (set(ws.DEV_CASES) | set(ws.VALIDATION_CASES))


def test_sealed3_excludes_dev_validation_panels_and_earlier_sealed_sets(tmp_path):
    s1 = json.loads((ROOT / "evidence/v0.4.0/protected/sealed-manifest.json").read_text(encoding="utf-8"))
    s2 = json.loads((ROOT / "evidence/v0.5.0/protected/sealed-2-manifest.json").read_text(encoding="utf-8"))
    m = create_manifest(tmp_path / "s3.json", "workshop-sealed-3", [s1, s2], exclude_panels=True)
    e = SealedEvaluator(tmp_path / "s3.json")
    earlier = set(SealedEvaluator(ROOT / "evidence/v0.4.0/protected/sealed-manifest.json").cases) | set(SealedEvaluator(ROOT / "evidence/v0.5.0/protected/sealed-2-manifest.json").cases)
    assert len(e.cases) == 48 and not set(e.cases) & (earlier | ws.all_panel_cases() | set(ws.DEV_CASES) | set(ws.VALIDATION_CASES))
    assert "cohort-panels-0..9" in m["disjoint_from"]


# --- declared mentorship -----------------------------------------------------------------------------------

def test_scheduled_teacher_does_not_start_a_lesson_it_cannot_finish():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, cohort_overlap=20,
                   teaching=True, teaching_policy="package-scheduled", cross_cohort_access=False, max_ticks=80)
    s = new_world(cfg)
    c = OfflineController(cfg.controller_seed)
    while s["tick"] < 21:
        s, _, _ = advance(s, c)
    teacher = next(a for a, x in s["agents"].items() if x["cohort"] == 0 and any(s["artifacts"][k].get("kind") == "workflow" for k in x["known"]))
    learner = next(a for a, x in s["agents"].items() if x["cohort"] == 1 and x["home"] == s["agents"][teacher]["home"])
    s["agents"][learner].update(x=s["agents"][teacher]["x"], y=s["agents"][teacher]["y"])
    msg = {"from": learner, "claim": "request_lesson", "tick": s["tick"], "source": "test"}
    s["agents"][teacher]["messages"] = [msg]
    s["agents"][teacher]["energy"] = 40
    s["sessions"] = {k: v for k, v in s.get("sessions", {}).items() if teacher not in (v["teacher"], v["learner"])}
    early = deepcopy(s)
    a = c.propose(LocalObservations().build(early, teacher))
    assert a.kind == "offer_teaching"
    late = deepcopy(s)
    late["tick"] = 37                                       # 3 ticks before retirement: a lesson needs at least 1 + 3 + 2 + 3
    late["agents"][teacher]["messages"] = [{**msg, "tick": 37}]
    late["agents"][teacher]["busy_until"] = 0
    a = c.propose(LocalObservations().build(late, teacher))
    assert a.kind != "offer_teaching"


def test_restart_with_pending_submission_and_mentorship_continues_identically(tmp_path):
    store = Store(tmp_path / "m.sqlite")
    rid = store.create(Scenario(seed=310, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, cohort_overlap=20,
                                teaching=True, teaching_policy="package-scheduled", search_policy="beam-alloc", budget_unit="credits", search_budget=48,
                                cross_cohort_access=False, max_ticks=80))
    state = None
    for _ in range(60):
        state = store.step(rid)
        pending = any(a["status"] in ("proposed", "dev-tested") for a in state["artifacts"].values() if a.get("task") == "workshop-1")
        lesson = any(x["stage"] in ("instruction", "practice") for x in state["sessions"].values())
        if state["tick"] >= 20 and pending and lesson:
            break
    reference = Store(tmp_path / "ref.sqlite")
    ref = reference.import_run(store.export(rid))
    del store
    reopened = Store(tmp_path / "m.sqlite")
    for _ in range(12):
        a, b = reopened.step(rid), reference.step(ref)
    assert digest(a) == digest(b) and digest(reopened.replay(rid, state["tick"])) == digest(state)


# --- reducer and dictionary ---------------------------------------------------------------------------------

def test_reducer_v3_reconciles_and_reports_every_dictionary_metric(tmp_path):
    store = Store(tmp_path / "d.sqlite")
    rid = store.create(Scenario(seed=311, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=40, cohort_count=2, cohort_overlap=20,
                                teaching=True, teaching_policy="package-scheduled", search_policy="beam-alloc", budget_unit="credits", search_budget=48,
                                max_ticks=80))
    for _ in range(80):
        store.step(rid)
    export = store.export(rid)
    red = reduce_export(export, [Window(0, 40, "c0"), Window(40, 80, "c1")])
    assert red["reconciliation"]["holdings_match_final_state"] and red["reconciliation"]["statuses_match_final_state"]
    m = red["metrics"]
    expected = {k for k in METRICS if not k.startswith(("knowledge.", "compare."))}
    assert expected <= set(m)
    assert m["search.credit_actions"] == sum(a.get("search_spent", 0) for a in export["state"]["agents"].values())
    assert m["search.own_candidate_tests"] + m["search.held_retests"] + m["search.component_tests"] == red["search"]["dev_evaluations"]
    assert m["lineage.improvements_with_earlier_cohort_ancestry"] is not None
    assert sum(m["time.agent_ticks_by_activity"].values()) == red["overall"]["active_agent_ticks"]


def test_paired_comparison_reports_denominators_and_never_scores_missing_as_zero():
    from tools.summarize_m5b import paired
    rows = [{"seed": s, "condition": c, "status": "completed", "x": v} for s, c, v in
            [(1, "a", 1.0), (1, "b", 2.0), (2, "a", 3.0), (2, "b", None), (3, "a", 2.0), (3, "b", 2.0)]]
    rows.append({"seed": 4, "condition": "a", "status": "failed"})
    out = paired(rows, "a", "b", "x", expected_seeds=[1, 2, 3, 4], missing_reason=lambda r: "no admitted workflow")
    assert out["expected_worlds"] == 4 and out["eligible_pairs"] == 2 and out["a_lower"] == 1 and out["ties"] == 1 and out["b_lower"] == 0
    reasons = {m["seed"]: m["reason"] for m in out["missing"]}
    assert reasons[2] == "b: no admitted workflow" and "a: world failed" in reasons[4]
    assert out["mean_a_over_eligible"] == 1.5 and out["decision_denominator"] == 2
