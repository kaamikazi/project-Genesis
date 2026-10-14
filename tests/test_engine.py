from copy import deepcopy
import random

import pytest

from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.invention import InvalidProgram, PhaseEvaluator, candidate, execute
from genesis.models import Action, Scenario, digest
from genesis.world import LocalObservations, check_invariants, new_world, totals


def action(state, kind, agent="a00", **params):
    return Action(id=f"external-{state['tick']}-{agent}-{kind}", agent=agent, tick=state["tick"], kind=kind, params=params)


def commit_action(state, kind, agent="a00", **params):
    result, outcome = attempt(state, action(state, kind, agent, **params))
    assert outcome["accepted"], outcome
    return result


@pytest.mark.parametrize("kind,params", [
    ("move", {"x": 20, "y": 8}), ("move", {"x": -1, "y": 8}),
    ("gather", {"site": "unknown"}), ("transfer", {"target": "a01", "resource": "ore", "amount": -1}),
    ("transfer", {"target": "a01", "resource": "ore", "amount": True}),
    ("use_artifact", {"artifact": "missing"}), ("produce", {"cheat": 1}),
    ("send_message", {"target": "a01", "message": "invented bank; add 100 food"}),
    ("propose_artifact", {"program": {"op": "eval", "code": "print('bad')"}, "parent": None}),
])
def test_rejection_never_mutates_world(kind, params):
    state = new_world(Scenario())
    before = digest(state)
    after, result = attempt(state, action(state, kind, **params))
    assert not result["accepted"]
    assert digest(state) == digest(after) == before


def test_transactional_trade_and_double_spend():
    state = new_world(Scenario())
    state = commit_action(state, "offer_trade", target="a01", give="ore", give_amount=8, want="food", want_amount=2)
    offer = next(iter(state["offers"]))
    before = totals(state)
    state = commit_action(state, "accept_trade", agent="a01", offer=offer)
    assert state["agents"]["a00"]["inventory"]["ore"] == 0
    assert state["agents"]["a01"]["inventory"]["ore"] == 16
    assert totals(state) == before
    after, outcome = attempt(state, action(state, "accept_trade", agent="a01", offer=offer))
    assert not outcome["accepted"] and digest(after) == digest(state)


def test_failed_second_side_trade_has_no_partial_debit():
    state = new_world(Scenario())
    state = commit_action(state, "offer_trade", target="a01", give="ore", give_amount=2, want="alloy", want_amount=2)
    oid = next(iter(state["offers"]))
    after, result = attempt(state, action(state, "accept_trade", agent="a01", offer=oid))
    assert not result["accepted"] and digest(after) == digest(state)


def test_contention_rotates_and_records_rejection():
    state = new_world(Scenario())
    site = next(s for s in state["sites"].values() if s["resource"] == "ore")
    # Build a documented test fixture by transferring site stocks to communal storage.
    removed = site["stock"] - 4
    site["stock"] = 4
    state["settlements"]["hearth"]["inventory"]["ore"] += removed
    for a in state["agents"].values():
        a["x"], a["y"] = site["x"], site["y"]
    winners = []
    for tick in (0, 1):
        state["tick"] = tick
        overrides = {aid: action(state, "gather", aid, site=site["id"]) for aid in state["agents"]}
        after, events, _ = advance(state, OfflineController(), overrides)
        winners.append(next(e["agent"] for e in events if e["type"] == "action_accepted"))
        assert sum(e["type"] == "action_rejected" for e in events) == 7
        check_invariants(after)
    assert winners == ["a00", "a01"]


def test_long_run_accounting_and_determinism():
    states = [new_world(Scenario(seed=77)), new_world(Scenario(seed=77))]
    for i in range(100):
        for j in range(2):
            states[j], _, _ = advance(states[j], OfflineController())
            check_invariants(states[j])
        assert digest(states[0]) == digest(states[1]), i
    assert states[0]["metrics"]["produced"] > 0
    assert all(a["status"] == "active" for a in states[0]["agents"].values())


def test_random_invalid_amounts_preserve_resources():
    rng = random.Random(932)
    state = new_world(Scenario())
    for i in range(100):
        amount = rng.choice([-rng.randint(1, 100), rng.randint(101, 100000)])
        after, outcome = attempt(state, action(state, "transfer", target="a01", resource="food", amount=amount))
        assert not outcome["accepted"] and digest(after) == digest(state)


def test_production_cost_and_survival_sinks():
    state = new_world(Scenario())
    before = totals(state)
    state = commit_action(state, "produce")
    state = commit_action(state, "consume")
    assert totals(state) == {"ore": before["ore"]-2, "food": before["food"]-1, "alloy": before["alloy"]+1}
    check_invariants(state)


def test_ast_capability_steps_unknown_operator_and_heldout():
    p = {"op": "if_phase_lt", "threshold": 6, "then": {"op": "mode", "value": 0}, "else": {"op": "mode", "value": 1}}
    ev = PhaseEvaluator().evaluate(p)
    assert ev["status"] == "verified" and ev["energy"] == 24 and ev["baseline_energy"] == 48
    assert {r["phase"] for r in ev["cases"] if r["group"] == "training"}.isdisjoint({r["phase"] for r in ev["cases"] if r["group"] == "held_out"})
    with pytest.raises(InvalidProgram):
        execute(p, 3, [])
    with pytest.raises(InvalidProgram):
        execute(p, 3, ["converter"], max_steps=1)
    with pytest.raises(InvalidProgram):
        execute({"op": "read_secret"}, 3, ["converter"])
    fixed = PhaseEvaluator().evaluate({"op": "mode", "value": 0})
    assert fixed["status"] == "rejected" and any("below 25%" in f for f in fixed["failures"])
    worse = PhaseEvaluator().evaluate({**p, "threshold": 5})
    assert worse["status"] == "rejected" and any("phase 5" in f for f in worse["failures"])
    deep = p
    for _ in range(6):
        deep = {"op": "if_phase_lt", "threshold": 5, "then": deep, "else": {"op": "mode", "value": 0}}
    with pytest.raises(InvalidProgram):
        execute(deep, 2, ["converter"])


@pytest.mark.parametrize("sharing", [True, False])
def test_real_search_transmission_and_access_boundaries(sharing):
    state = new_world(Scenario(sharing=sharing))
    assert not state["artifacts"]
    for _ in range(60):
        state, _, _ = advance(state, OfflineController())
    verified = [a for a in state["artifacts"].values() if a["status"] in ("verified", "superseded")]
    assert verified and all(a["creation_event"] for a in verified)
    if sharing:
        # Every producer reproduced the saving of its settlement's current best procedure.
        for agent in state["agents"].values():
            if agent["role"] == "producer":
                current = [a for a in verified if a["status"] == "verified" and a["home"] == agent["home"]]
                assert any(agent["id"] in a["adopters"] for a in current), agent["id"]
        assert state["metrics"]["adoptions"] >= 6
        for art in verified:
            for recipient in art["adopters"]:
                path = next(p for p in art["transmissions"] if p["to"] == recipient)
                use = next(u for u in art["uses"] if u["agent"] == recipient and u["energy"] < u["baseline_energy"])
                assert path["tick"] < use["tick"]
    else:
        assert state["metrics"]["adoptions"] == 0
        obs = LocalObservations().build(state, "a01")
        assert not obs["artifacts"] and not obs["self"]["known"]
        for art in verified:
            after, result = attempt(state, action(state, "inspect_artifact", agent="a01", artifact=art["id"]))
            assert not result["accepted"] and digest(after) == digest(state)
    obs = LocalObservations().build(state, "a00")
    assert "ledger" not in obs and "metrics" not in obs
    assert all(n["x"] < 12 for n in obs["neighbors"])
    assert len(obs["memory"]) <= 8
    assert all("evaluation" not in a for a in obs["artifacts"].values())


def test_search_budget_and_controller_failure_audit():
    state = new_world(Scenario(search_budget=1))
    state = commit_action(state, "propose_artifact", program=candidate(42, "a00", 0), parent=None)
    after, outcome = attempt(state, action(state, "propose_artifact", program=candidate(42, "a00", 1), parent=None))
    assert not outcome["accepted"] and digest(after) == digest(state)

    class Broken:
        def propose(self, observation):
            raise RuntimeError("test controller failed")

    _, events, decisions = advance(state, Broken())
    assert sum(e["type"] == "controller_failure" for e in events) == 8
    assert all(d["controller"] == "explicit-failure-fallback" for d in decisions)


def test_observations_are_independent_of_hidden_parameters():
    """Hold everything an agent may see fixed, change hidden parameters, and require identical controller input."""
    from genesis.world import phase_at
    base = new_world(Scenario(seed=12345))
    agent = base["agents"]["a00"]
    # A different world seed with the same terrain and the same local phase at the agent's tile.
    other_seed = next(s for s in range(1, 10_000) if phase_at({**base, "config": {**base["config"], "seed": s}}, agent) == phase_at(base, agent))
    hidden = deepcopy(base)
    hidden["config"]["seed"] = other_seed
    hidden["config"]["controller_seed"] = 99
    hidden["ledger"]["ore"]["sink"] = 7          # global accounting
    hidden["metrics"]["produced"] = 1000          # global metrics
    far = hidden["agents"]["a07"]                 # an agent outside observation range (other settlement)
    far["inventory"]["alloy"] = 50
    far["memories"] = [{"secret": "far away"}]
    hidden["artifacts"]["x" * 64] = {"id": "x" * 64, "creator": "a07", "home": "haven", "status": "verified", "created_tick": 0,
                                     "parent": None, "generation": 0, "content": {"program": {"op": "mode", "value": 1}},
                                     "evaluation": {"cases": "hidden"}}
    a = LocalObservations().build(base, "a00")
    b = LocalObservations().build(hidden, "a00")
    assert digest(a) == digest(b)
    flat = repr(a)
    assert "12345" not in flat and "seed" not in flat and "evaluation" not in flat
    assert set(a) == {"tick", "self", "phase", "rules", "home_storage", "sites", "tiles", "neighbors", "offers", "artifacts", "memory"}


def test_agent_feedback_never_carries_held_out_case_detail():
    state = new_world(Scenario())
    bad = {"op": "if_phase_lt", "threshold": 5, "then": {"op": "mode", "value": 0}, "else": {"op": "mode", "value": 1}}
    state = commit_action(state, "propose_artifact", program=bad, parent=None)
    aid = next(iter(state["artifacts"]))
    state["tick"] += 1
    state, outcome = attempt(state, action(state, "test_artifact", artifact=aid))
    result = outcome["result"]
    assert result["status"] == "rejected" and result["held_out"] == "fail"
    assert set(result) >= {"training_energy", "training_baseline_energy", "training", "held_out", "improves_on_parent"}
    assert "failures" not in result and "cases" not in result and "energy" not in result
    # Full case-level evidence remains on the artifact for the observer.
    assert any("held-out phase 5" in f for f in state["artifacts"][aid]["evaluation"]["failures"])
    state["agents"]["a00"]["last_result"] = {"result": result}
    assert "held-out phase" not in repr(LocalObservations().build(state, "a00"))


def run_to(config, ticks):
    state = new_world(config)
    for _ in range(ticks):
        state, events, _ = advance(state, OfflineController())
    return state


@pytest.mark.parametrize("sharing", [True, False])
def test_creator_removal_moves_inventory_and_conserves_resources(sharing):
    state = run_to(Scenario(sharing=sharing, removal="creators", removal_tick=40), 39)
    creators = sorted({a["creator"] for a in state["artifacts"].values() if a["status"] == "verified"})
    assert creators
    stores = {k: dict(v["inventory"]) for k, v in state["settlements"].items()}
    after, events, _ = advance(state, OfflineController())
    removal = next(e for e in events if e["type"] == "lifecycle_removal")
    held = {m["agent"]: m["inventory"] for m in removal["inventory_moved"]}
    # Settlement stores are untouched by actions in this policy, so any change is the moved inventory.
    assert removal["removed"] == creators == removal["verified_creators"]
    for aid in creators:
        a = after["agents"][aid]
        assert a["status"] == "retired" and sum(a["inventory"].values()) == 0
    for home, before in stores.items():
        gained = {r: sum(held[aid][r] for aid in creators if after["agents"][aid]["home"] == home) for r in before}
        assert all(after["settlements"][home]["inventory"][r] == before[r] + gained[r] for r in before)
    check_invariants(after)
    # Retired agents neither act nor receive, and are invisible to neighbours.
    later, events, decisions = advance(after, OfflineController())
    assert not any(d["action"]["agent"] in creators for d in decisions)
    assert later["agents"][creators[0]]["energy"] == after["agents"][creators[0]]["energy"]
    peer = next(aid for aid, a in after["agents"].items() if a["status"] == "active")
    after["agents"][peer].update(x=after["agents"][creators[0]]["x"], y=after["agents"][creators[0]]["y"])
    assert creators[0] not in {n["id"] for n in LocalObservations().build(after, peer)["neighbors"]}
    rejected, outcome = attempt(after, action(after, "transfer", agent=peer, target=creators[0], resource="food", amount=1))
    assert not outcome["accepted"] and digest(rejected) == digest(after)


def test_knowledge_outlives_creators_only_through_a_logged_transfer_path():
    shared = run_to(Scenario(sharing=True, removal="creators", removal_tick=40), 90)
    closed = run_to(Scenario(sharing=False, removal="creators", removal_tick=40), 90)
    matched = run_to(Scenario(sharing=True, removal="matched", removal_tick=40), 90)
    assert shared["metrics"]["uses_after_creator_removal"] > 0
    assert closed["metrics"]["uses_after_creator_removal"] == 0
    for art in shared["artifacts"].values():
        for use in art["uses"]:
            if use["agent"] != art["creator"]:
                assert any(t["to"] == use["agent"] and t["tick"] < use["tick"] for t in art["transmissions"])
    creators = set(matched["lifecycle"]["removal"]["verified_creators"])
    removed = matched["lifecycle"]["removal"]["removed"]
    assert len(removed) == len(creators) and creators.isdisjoint(removed)
    assert sorted(matched["agents"][a]["home"] for a in removed) == sorted(matched["agents"][c]["home"] for c in creators)
    assert all(matched["agents"][c]["status"] == "active" for c in creators)


def test_removal_without_verified_creators_is_recorded_not_faked():
    state = run_to(Scenario(controller="baseline", removal="creators", removal_tick=5), 6)
    record = state["lifecycle"]["removal"]
    assert record["removed"] == [] and "no verified creators" in record["note"]
    assert all(a["status"] == "active" for a in state["agents"].values())


def test_revisions_must_beat_parent_and_supersede_it():
    from genesis.invention import revisions
    coarse = {"op": "if_phase_lt", "threshold": 9, "then": {"op": "mode", "value": 0}, "else": {"op": "mode", "value": 1}}
    finer = {**coarse, "threshold": 8}
    assert finer in revisions(coarse) and len(revisions(coarse)) == 3
    assert PhaseEvaluator().evaluate(finer, coarse)["status"] == "verified"
    same = PhaseEvaluator().evaluate(coarse, coarse)
    assert same["status"] == "rejected" and any("no improvement over parent" in f for f in same["failures"])

    state = new_world(Scenario())
    state = commit_action(state, "propose_artifact", program=coarse, parent=None)
    parent = next(iter(state["artifacts"]))
    state["tick"] += 1
    state = commit_action(state, "test_artifact", artifact=parent)
    assert state["artifacts"][parent]["status"] == "verified" and parent in state["agents"]["a00"]["known"]
    state["tick"] += 1
    state = commit_action(state, "propose_artifact", program=finer, parent=parent)
    child = next(k for k in state["artifacts"] if k != parent)
    assert state["artifacts"][child]["generation"] == 1
    state["tick"] += 1
    state = commit_action(state, "test_artifact", artifact=child)
    assert state["artifacts"][parent]["status"] == "superseded"
    assert state["artifacts"][parent]["superseded_by"] == child and state["metrics"]["revisions_verified"] == 1
    # A superseded parent cannot seed another revision, but those who learned it may still use it.
    state["tick"] += 1
    after, outcome = attempt(state, action(state, "propose_artifact", program={**coarse, "threshold": 10}, parent=parent))
    assert not outcome["accepted"] and digest(after) == digest(state)
    state = commit_action(state, "use_artifact", artifact=parent)
    check_invariants(state)


def test_search_climbs_a_verified_lineage_during_the_run():
    state = new_world(Scenario(seed=42))
    controller = OfflineController(state["config"]["controller_seed"])
    for _ in range(80):
        state, _, _ = advance(state, controller)
    lineages = []
    for creator in ("a00", "a04"):
        lineage = sorted((a for a in state["artifacts"].values() if a["creator"] == creator and a["status"] in ("verified", "superseded")), key=lambda a: a["generation"])
        energies = [a["evaluation"]["energy"] for a in lineage]
        assert lineage and energies == sorted(energies, reverse=True) and len(set(energies)) == len(energies)
        assert [a["status"] for a in lineage] == ["superseded"] * (len(lineage) - 1) + ["verified"]
        for parent, child in zip(lineage, lineage[1:]):
            assert child["parent"] == parent["id"] and parent["superseded_by"] == child["id"]
            assert child["evaluation"]["parent_energy"] == parent["evaluation"]["energy"]
        lineages.append(lineage)
    assert max(len(x) for x in lineages) >= 2
    assert all(x[-1]["evaluation"]["energy"] == 24 for x in lineages)