import itertools

import pytest

from genesis import workshop as ws
from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.models import Action, Scenario, digest
from genesis.world import LocalObservations, check_invariants, new_world, totals

WF = {"op": "workflow", "batch": {"op": "if_lt", "measure": "ore", "threshold": 6, "then": {"op": "const", "value": 1}, "else": {"op": "const", "value": 2}},
      "heat": {"op": "if_lt", "measure": "humidity", "threshold": 3, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "mode": {"op": "if_lt", "measure": "phase", "threshold": 6, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "flux": {"op": "if_lt", "measure": "humidity", "threshold": 5, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}}}


def act(state, kind, agent="a00", **params):
    return Action(id=f"w-{state['tick']}-{agent}-{kind}", agent=agent, tick=state["tick"], kind=kind, params=params)


@pytest.mark.parametrize("bad", [
    {"op": "workflow"}, {"op": "eval", "code": "1"}, {**WF, "extra": 1},
    {**WF, "batch": {"op": "const", "value": 9}}, {**WF, "heat": {"op": "if_lt", "measure": "secret", "threshold": 1, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 0}}},
    {"op": "component", "field": "heat", "expr": {"op": "call", "artifact": "a" * 64}},   # components cannot call
])
def test_malformed_programs_are_rejected(bad):
    with pytest.raises(ws.InvalidWorkflow):
        ws.validate(bad)


def test_interpreter_bounds_nodes_depth_and_steps():
    deep = {"op": "const", "value": 1}
    for _ in range(8):
        deep = {"op": "if_lt", "measure": "ore", "threshold": 3, "then": deep, "else": {"op": "const", "value": 1}}
    with pytest.raises(ws.InvalidWorkflow):
        ws.validate({**WF, "batch": deep})
    with pytest.raises(ws.InvalidWorkflow, match="missing prerequisite"):
        ws.execute({**WF, "heat": {"op": "call", "artifact": "b" * 64}}, {"phase": 1, "humidity": 1, "ore": 9, "energy": 40}, {})


def test_decisions_interact():
    """Heat accuracy changes ore needed, so it changes which batch sizes are feasible; mode changes energy."""
    params = {"split": 6, "offset": 0, "flux_threshold": 9}
    m = {"phase": 2, "humidity": 6, "ore": 8, "energy": 40}      # optimal heat 2
    right = ws.outcome(params, m, {"batch": 4, "heat": 2, "mode": 0, "flux": 0})
    wrong_heat = ws.outcome(params, m, {"batch": 4, "heat": 0, "mode": 0, "flux": 0})
    assert right["feasible"] and not wrong_heat["feasible"]   # wasted ore makes the big batch infeasible
    wrong_mode = ws.outcome(params, m, {"batch": 4, "heat": 2, "mode": 1, "flux": 0})
    assert wrong_mode["energy"] > right["energy"]
    small = ws.outcome(params, m, {"batch": 1, "heat": 2, "mode": 0, "flux": 0})
    assert right["cost"] / right["alloy"] < small["cost"] / small["alloy"]   # batching amortises setup


def test_partitions_are_disjoint_versioned_and_parent_child_comparable():
    assert not set(ws.DEV_CASES) & set(ws.VALIDATION_CASES)
    assert ws.DEV_CASES == ws.partition("dev", 24) and len(ws.VALIDATION_CASES) == 24
    params = ws.world_params(5)
    val = ws.WorkshopEvaluator().validation(WF, params, {}, ws.BASELINE, {})
    assert val["parent_score"] == ws.score_cases(ws.BASELINE, params, ws.VALIDATION_CASES, {})["score"]
    assert "one bit" in val["feedback_policy"]


def test_oracle_lower_bound_is_not_beaten_by_any_program():
    params = ws.world_params(5)
    decisions = [dict(zip(ws.FIELDS, d)) for d in itertools.product(range(1, 5), range(4), range(2), range(2))]
    for prog in (ws.BASELINE, WF):
        score = ws.score_cases(prog, params, ws.DEV_CASES, {})["score"]
        lam = score
        for _ in range(40):   # Dinkelbach: minimum pooled ratio over per-case decisions
            c = a = 0
            for p, h, o, e in ws.DEV_CASES:
                m = {"phase": p, "humidity": h, "ore": o, "energy": e}
                best = min(((r["cost"], r["alloy"]) if r["feasible"] else (ws.INFEASIBLE_PENALTY, 0) for r in (ws.outcome(params, m, d) for d in decisions)),
                           key=lambda t: t[0] - lam * t[1])
                c, a = c + best[0], a + best[1]
            lam = c / a
        assert score >= lam - 1e-9


def workshop_world(ticks=0, **kw):
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=400, **kw)
    state = new_world(cfg)
    c = OfflineController(cfg.controller_seed)
    for _ in range(ticks):
        state, _, _ = advance(state, c)
    return state


def test_flux_workflow_conserves_resources_and_sets_busy_time():
    state = workshop_world()
    a = state["agents"]["a01"]
    state["agents"]["a01"]["inventory"]["ore"] = 8
    state["initial_totals"]["ore"] += 0
    before = totals(state)
    state = workshop_world()
    after, out = attempt(state, act(state, "produce", "a01"))
    assert out["accepted"], out
    r = out["result"]
    assert r["procedure"] == "baseline workflow" and r["alloy"] == 1
    t = totals(after)
    assert t["ore"] == totals(state)["ore"] - r["ore"] and t["alloy"] == totals(state)["alloy"] + r["alloy"]
    check_invariants(after)
    assert after["agents"]["a01"]["busy_until"] == state["tick"] + 1


def test_batches_occupy_agents_and_reject_other_actions():
    state = workshop_world()
    state["agents"]["a01"]["busy_until"] = state["tick"] + 2
    after, out = attempt(state, act(state, "gather", "a01", site="hearth-ore-1-0"))
    assert not out["accepted"] and "busy" in out["reason"] and digest(after) == digest(state)
    after, out = attempt(state, act(state, "consume", "a01"))
    assert out["accepted"]


def test_workshop_lifecycle_dev_feedback_then_admission_bit():
    state = workshop_world()
    after, out = attempt(state, act(state, "propose_artifact", program=WF, parent=None))
    assert out["accepted"]
    aid = out["result"]["artifact"]
    after["tick"] += 1
    after, out = attempt(after, act(after, "test_artifact", artifact=aid))
    res = out["result"]
    assert res["role"] == "development" and len(res["cases"]) == 24 and "validation" not in repr(res)
    after["tick"] += 1
    after, out = attempt(after, act(after, "submit_artifact", artifact=aid))
    res = out["result"]
    assert set(res) >= {"admitted", "status"} and "score" not in repr({k: v for k, v in res.items() if k != "energy_charged"})
    obs = LocalObservations().build(after, "a00")
    assert "validation" not in repr(obs) and "sealed" not in repr(obs)
    assert "split" not in repr(obs) and "flux_threshold" not in repr(obs)
