from copy import deepcopy

import pytest

from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.experiments import physical_view
from genesis.models import Action, Scenario, digest
from genesis.storage import Store
from genesis.world import LocalObservations, check_invariants, new_world, totals


def act(state, kind, agent="a00", suffix="", **params):
    return Action(id=f"t-{state['tick']}-{agent}-{kind}{suffix}", agent=agent, tick=state["tick"], kind=kind, params=params)


def ok(state, kind, agent="a00", **params):
    after, outcome = attempt(state, act(state, kind, agent, **params))
    assert outcome["accepted"], outcome
    return after


def run(state, ticks):
    controller = OfflineController(state["config"]["controller_seed"])
    for _ in range(ticks):
        state, _, _ = advance(state, controller)
    return state


def with_policy(state, **changes):
    """In-memory equivalent of a fork intervention (the Store path is tested separately)."""
    state = deepcopy(state)
    state["config"] = Scenario.model_validate({**state["config"], **changes}).model_dump()
    return state


# --- settlement storage -------------------------------------------------------------------------

def test_deposit_and_withdraw_preserve_the_ledger():
    state = new_world(Scenario())
    before = totals(state)
    state = ok(state, "deposit", settlement="hearth", resource="ore", amount=5)
    assert state["agents"]["a00"]["inventory"]["ore"] == 3 and state["settlements"]["hearth"]["inventory"]["ore"] == 5
    state = ok(state, "withdraw", agent="a01", settlement="hearth", resource="ore", amount=4)
    assert state["agents"]["a01"]["inventory"]["ore"] == 12 and state["settlements"]["hearth"]["inventory"]["ore"] == 1
    assert state["settlements"]["hearth"]["flows"]["deposit"]["ore"] == 5 and state["settlements"]["hearth"]["flows"]["withdraw"]["ore"] == 4
    assert totals(state) == before and state["ledger"] == new_world(Scenario())["ledger"]
    check_invariants(state)


@pytest.mark.parametrize("agent,params,reason", [
    ("a04", {"settlement": "hearth", "resource": "ore", "amount": 1}, "not a member"),      # Haven member at Haven's storage? no: Hearth's
    ("a00", {"settlement": "atlantis", "resource": "ore", "amount": 1}, "unknown settlement"),
    ("a00", {"settlement": "hearth", "resource": "ore", "amount": 0}, "amount must be"),
    ("a00", {"settlement": "hearth", "resource": "gold", "amount": 1}, "unknown resource"),
])
def test_unauthorized_or_invalid_storage_access_changes_nothing(agent, params, reason):
    state = new_world(Scenario())
    state["settlements"]["hearth"]["inventory"]["ore"] = 10
    state["initial_totals"]["ore"] += 10
    state["agents"]["a04"].update(x=state["settlements"]["hearth"]["x"], y=state["settlements"]["hearth"]["y"])
    for kind in ("deposit", "withdraw"):
        after, outcome = attempt(state, act(state, kind, agent, **params))
        assert not outcome["accepted"] and reason in outcome["reason"] and digest(after) == digest(state)


def test_storage_out_of_reach_and_overdraw_are_rejected():
    state = new_world(Scenario())
    state["agents"]["a00"].update(x=state["settlements"]["hearth"]["x"] + 3)
    after, outcome = attempt(state, act(state, "deposit", settlement="hearth", resource="ore", amount=1))
    assert not outcome["accepted"] and "out of reach" in outcome["reason"]
    after, outcome = attempt(state, act(state, "withdraw", "a01", settlement="hearth", resource="ore", amount=1))
    assert not outcome["accepted"] and "insufficient settlement stock" in outcome["reason"] and digest(after) == digest(state)


def test_competing_withdrawals_in_one_tick_never_overdraw():
    state = new_world(Scenario())
    state["settlements"]["hearth"]["inventory"]["ore"] = 6
    state["initial_totals"]["ore"] += 6
    overrides = {aid: act(state, "withdraw", aid, settlement="hearth", resource="ore", amount=5) for aid in ("a01", "a02")}
    after, events, _ = advance(state, OfflineController(), overrides)
    outcomes = [e for e in events if e.get("kind") == "withdraw"]
    assert sorted(e["type"] for e in outcomes) == ["action_accepted", "action_rejected"]
    assert "insufficient settlement stock" in next(e for e in outcomes if e["type"] == "action_rejected")["reason"]
    assert after["settlements"]["hearth"]["inventory"]["ore"] == 1
    check_invariants(after)


def test_production_continues_from_deposited_ore():
    state = new_world(Scenario())
    state = ok(state, "deposit", agent="a01", settlement="hearth", resource="ore", amount=8)
    assert state["agents"]["a01"]["inventory"]["ore"] == 0
    after, outcome = attempt(state, act(state, "produce", "a01"))
    assert not outcome["accepted"]
    state = ok(state, "withdraw", agent="a01", settlement="hearth", resource="ore", amount=2)
    state = ok(state, "produce", agent="a01")
    assert state["agents"]["a01"]["inventory"]["alloy"] == 1 and state["ledger"]["ore"]["sink"] == 2
    check_invariants(state)


# --- retirement and succession ------------------------------------------------------------------

def at_boundary(access="library", succession="fresh", role="producer", ticks=60):
    state = run(new_world(Scenario(max_ticks=400)), ticks)
    state = with_policy(state, removal="creators", removal_tick=ticks + 1, succession=succession,
                        successor_access=access, successor_role=role, invention="frozen")
    held = {aid: dict(a["inventory"]) for aid, a in state["agents"].items()}
    after, events, _ = advance(state, OfflineController(state["config"]["controller_seed"]))
    return state, after, events, held


def test_retirement_moves_inventory_to_withdrawable_storage():
    before, state, events, _ = at_boundary(succession="none")
    removal = next(e for e in events if e["type"] == "lifecycle_removal")
    assert removal["removed"] and removal["successors"] == []
    for moved in removal["inventory_moved"]:
        a = state["agents"][moved["agent"]]
        assert a["status"] == "retired" and a["retired_tick"] == removal["tick"] and sum(a["inventory"].values()) == 0
        flows = state["settlements"][moved["to"]]["flows"]["retirement"]
        assert all(flows[r] >= n for r, n in moved["inventory"].items())
    check_invariants(state)
    # A remaining member can withdraw what the retiree left.
    member = next(aid for aid, a in state["agents"].items() if a["status"] == "active" and a["home"] == "hearth")
    store = state["settlements"]["hearth"]
    res = next((r for r in ("ore", "food", "alloy") if store["inventory"][r] > 0), None)
    assert res is not None
    state["agents"][member].update(x=store["x"], y=store["y"])
    ok(state, "withdraw", agent=member, settlement="hearth", resource=res, amount=1)


def test_retired_agents_cannot_act_by_any_path():
    _, state, events, _ = at_boundary()
    retired = next(aid for aid, a in state["agents"].items() if a["status"] == "retired")
    after, outcome = attempt(state, act(state, "produce", retired))
    assert not outcome["accepted"] and "not active (retired)" in outcome["reason"] and digest(after) == digest(state)
    nxt, events, decisions = advance(state, OfflineController(), {retired: act(state, "wait", retired)})
    rejection = next(e for e in events if e["agent"] == retired)
    assert rejection["type"] == "action_rejected" and "not active" in rejection["reason"]
    assert not any(d["action"]["agent"] == retired and d["observation_hash"] for d in decisions)
    peer = next(aid for aid, a in state["agents"].items() if a["status"] == "active")
    assert retired not in {n["id"] for n in LocalObservations().build(state, peer)["neighbors"]}


def test_successors_start_fresh_with_only_the_declared_package():
    before, state, events, _ = at_boundary(access="library")
    removal = next(e for e in events if e["type"] == "lifecycle_removal")
    assert len(removal["successors"]) == len(removal["removed"]) >= 1
    for s in removal["successors"]:
        heir, old = state["agents"][s["successor"]], state["agents"][s["predecessor"]]
        assert s["successor"] not in before["agents"] and heir["name"] != old["name"]
        assert heir["predecessor"] == old["id"] and old["successor"] == heir["id"]
        assert heir["created_tick"] == removal["tick"] and heir["energy"] == 30 and sum(heir["inventory"].values()) == 0
        assert heir["known"] == heir["seen"] == heir["used"] == heir["memories"] == heir["beliefs"] == []
        assert heir["relationships"] == {} and heir["search_count"] == 0 and heir["role"] == "producer"
        assert heir["inheritance"]["memories_inherited"] == 0 and heir["inheritance"]["package"] == []
        assert "library" in heir["capabilities"]
        # The predecessor's history is archived, not erased or copied to the heir.
        assert old["memories"] and all(m["tick"] <= removal["tick"] for m in old["memories"])


def test_library_successor_discovers_learns_and_uses_with_logged_evidence():
    _, state, _, _ = at_boundary(access="library")
    heirs = [a["id"] for a in state["agents"].values() if a["predecessor"]]
    obs = LocalObservations().build(state, heirs[0])
    assert any(v["status"] == "verified" and "program" not in v for v in obs["artifacts"].values())  # visible via library, not yet held
    state = run(state, 30)
    for heir in heirs:
        learned = [(aid, t) for aid, art in state["artifacts"].items() for t in art["transmissions"] if t["to"] == heir]
        assert learned and all(t["via"] == "settlement library" for _, t in learned)
        aid, path = learned[0]
        use = state["artifacts"][aid]["first_uses"][heir]
        assert use["tick"] > path["tick"] - 1 and use["agent"] == heir
        assert any(u["agent"] == heir and u["energy"] < u["baseline_energy"] for u in state["artifacts"][aid]["uses"])


def test_restricted_successor_has_no_alternate_path_to_procedures():
    _, state, _, _ = at_boundary(access="none")
    heirs = [a["id"] for a in state["agents"].values() if a["predecessor"]]
    verified = [aid for aid, a in state["artifacts"].items() if a["status"] == "verified"]
    for heir in heirs:
        a = state["agents"][heir]
        assert a["known"] == [] and "library" not in a["capabilities"]
        assert LocalObservations().build(state, heir)["artifacts"] == {}
        for aid in verified:   # direct IDs, even standing at the library
            for kind in ("inspect_artifact", "use_artifact", "test_artifact"):
                after, outcome = attempt(state, act(state, kind, heir, artifact=aid))
                assert not outcome["accepted"] and digest(after) == digest(state)
    state = run(state, 30)
    for heir in heirs:
        assert state["agents"][heir]["known"] == [] and state["agents"][heir]["used"] == []
        assert not any(t["to"] == heir for art in state["artifacts"].values() for t in art["transmissions"])


def test_direct_transfer_control_is_labelled():
    _, state, events, _ = at_boundary(access="direct")
    removal = next(e for e in events if e["type"] == "lifecycle_removal")
    for s in removal["successors"]:
        heir = state["agents"][s["successor"]]
        assert s["package"] and heir["known"] == s["package"] and "library" not in heir["capabilities"]
        for aid in s["package"]:
            assert any(t["to"] == heir["id"] and t["via"].startswith("succession package (direct-transfer control)")
                       for t in state["artifacts"][aid]["transmissions"])


def test_invention_freeze_rejects_new_proposals():
    _, state, _, _ = at_boundary(role="researcher")
    heir = next(a["id"] for a in state["agents"].values() if a["predecessor"])
    program = {"op": "mode", "value": 1}
    after, outcome = attempt(state, act(state, "propose_artifact", heir, program=program, parent=None))
    assert not outcome["accepted"] and "frozen" in outcome["reason"]
    assert LocalObservations().build(state, heir)["rules"]["invention_open"] is False


# --- forks, parity and replay -------------------------------------------------------------------

def test_forked_continuations_share_physical_conditions(tmp_path):
    store = Store(tmp_path / "w.sqlite")
    base = store.create(Scenario(max_ticks=40))
    for _ in range(40):
        store.step(base)
    views, retirees = {}, {}
    for access in ("library", "none", "direct"):
        fork = store.fork(base, 40, {"removal": "creators", "removal_tick": 41, "succession": "fresh", "successor_access": access,
                                     "invention": "frozen", "max_ticks": 45}, f"diag-{access}")
        manifest = next(r for r in store.list_runs() if r["id"] == fork)["manifest"]
        assert manifest["parent"]["run_id"] == base and manifest["parent"]["label"] == f"diag-{access}"
        assert manifest["parent"]["intervention"]["successor_access"] == access
        store.step(fork)
        boundary = store.load(fork)
        views[access], retirees[access] = physical_view(boundary), boundary["lifecycle"]["removal"]["removed"]
    assert len(set(views.values())) == 1 and len({tuple(v) for v in retirees.values()}) == 1 and retirees["none"]
    assert store.load(base)["tick"] == 40   # parent history untouched


def test_fork_interventions_are_validated(tmp_path):
    store = Store(tmp_path / "w.sqlite")
    base = store.create(Scenario())
    for _ in range(5):
        store.step(base)
    with pytest.raises(ValueError, match="may not change"):
        store.fork(base, 5, {"seed": 1})
    with pytest.raises(ValueError, match="after the fork tick"):
        store.fork(base, 5, {"removal": "creators", "removal_tick": 5})


def test_replay_reconstructs_lifecycle_and_storage_at_every_tick(tmp_path):
    store = Store(tmp_path / "w.sqlite")
    rid = store.create(Scenario(removal="creators", removal_tick=30, succession="fresh", snapshot_every=7, max_ticks=60))
    hashes = {}
    for _ in range(50):
        s = store.step(rid)
        hashes[s["tick"]] = digest(s)
    restarted = Store(store.path)
    for tick, expected in hashes.items():
        replayed = restarted.replay(rid, tick)
        assert digest(replayed) == expected
    final = restarted.replay(rid, 50)
    assert final["lifecycle"]["removal"]["successors"] and any(a["status"] == "retired" for a in final["agents"].values())
    assert sum(s["flows"]["retirement"]["food"] + s["flows"]["retirement"]["ore"] for s in final["settlements"].values()) >= 0
    imported = Store(tmp_path / "copy.sqlite").import_run(restarted.export(rid))
    assert digest(Store(tmp_path / "copy.sqlite").load(imported)) == hashes[50]
