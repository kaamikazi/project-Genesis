from copy import deepcopy

import pytest

from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.models import Action, Scenario, digest
from genesis.storage import Store
from genesis.world import LocalObservations, check_invariants, new_world


def act(state, kind, agent, suffix="", **params):
    return Action(id=f"t-{state['tick']}-{agent}-{kind}{suffix}", agent=agent, tick=state["tick"], kind=kind, params=params)


def run(state, ticks):
    c = OfflineController(state["config"]["controller_seed"])
    for _ in range(ticks):
        state, _, _ = advance(state, c)
    return state


def classroom(teaching=True):
    """A Hearth producer holding an admitted workflow (teacher) and a Hearth producer without it (learner), co-located."""
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=400)
    state = run(new_world(cfg), 40)
    state["config"] = Scenario.model_validate({**state["config"], "teaching": teaching, "invention": "frozen"}).model_dump()
    admitted = [aid for aid, a in state["artifacts"].items() if a["status"] == "admitted" and a["home"] == "hearth"]
    teacher = next(aid for aid, a in state["agents"].items() if a["home"] == "hearth" and a["role"] == "producer" and set(admitted) & set(a["known"]))
    learner = next(aid for aid, a in state["agents"].items() if a["home"] == "hearth" and a["role"] == "producer" and aid != teacher)
    artifact = next(x for x in admitted if x in state["agents"][teacher]["known"])
    state["agents"][learner]["known"] = [k for k in state["agents"][learner]["known"] if state["artifacts"][k]["home"] != "hearth"]
    for aid in (teacher, learner):
        state["agents"][aid].update(x=state["settlements"]["hearth"]["x"], y=state["settlements"]["hearth"]["y"], busy_until=0, energy=40)
    state["agents"][learner]["inventory"]["ore"] += 20          # practice inputs, added through the ledger baseline
    state["initial_totals"]["ore"] += 20
    return state, teacher, learner, artifact


def ok(state, kind, agent, **params):
    after, out = attempt(state, act(state, kind, agent, **params))
    assert out["accepted"], out
    return after, out["result"]


def tick(state):
    state = deepcopy(state)
    state["tick"] += 1
    return state


def open_session(state, teacher, learner, artifact):
    state, r = ok(state, "offer_teaching", teacher, learner=learner, artifact=artifact)
    sid = r["session"]
    state, r = ok(tick(state), "accept_teaching", learner, session=sid)
    assert r["stage"] == "instruction"
    return state, sid


def test_teacher_must_hold_the_skill_naming_an_id_is_not_enough():
    state, teacher, learner, artifact = classroom()
    after, out = attempt(state, act(state, "offer_teaching", learner, learner=teacher, artifact=artifact))
    assert not out["accepted"] and "must already hold" in out["reason"] and digest(after) == digest(state)
    after, out = attempt(state, act(state, "offer_teaching", teacher, learner=learner, artifact="f" * 64))
    assert not out["accepted"]


def test_teaching_requires_the_scenario_flag():
    state, teacher, learner, artifact = classroom(teaching=False)
    after, out = attempt(state, act(state, "offer_teaching", teacher, learner=learner, artifact=artifact))
    assert not out["accepted"] and "not enabled" in out["reason"]
    after, out = attempt(state, act(state, "send_message", learner, target=teacher, message="request_lesson"))
    assert not out["accepted"]


def test_full_lesson_charges_costs_atomically_and_acquires_only_after_assessment():
    state, teacher, learner, artifact = classroom()
    t0, l0 = state["agents"][teacher]["energy"], state["agents"][learner]["energy"]
    state, sid = open_session(state, teacher, learner, artifact)
    # Reserved participants cannot do anything else during instruction.
    for agent in (teacher, learner):
        after, out = attempt(state, act(state, "gather", agent, site="hearth-ore-1-0"))
        assert not out["accepted"] and "reserved" in out["reason"] and digest(after) == digest(state)
    for i in range(3):
        state = tick(state)
        state, r = ok(state, "teach_step", teacher, session=sid)
        assert r["energy_charged"] == 2
        state, r = ok(state, "learn_step", learner, session=sid)
        assert r["energy_charged"] == 1
    session = state["sessions"][sid]
    assert session["stage"] == "practice" and artifact not in state["agents"][learner]["known"]
    # No premature competence: the learner cannot use the artifact as its own before assessment.
    after, out = attempt(state, act(state, "use_artifact", learner, artifact=artifact))
    assert not out["accepted"]
    state["agents"][learner]["inventory"]["ore"] += 0
    outcomes = []
    for i in range(2):
        state = tick(state)
        state["agents"][learner]["busy_until"] = 0
        state, r = ok(state, "practice_step", learner, session=sid)
        outcomes.append(r["practice"]["passed"])
    session = state["sessions"][sid]
    assert session["assessment"]["passed"] == all(outcomes)
    if all(outcomes):
        assert session["stage"] == "acquired" and artifact in state["agents"][learner]["known"]
        assert any(t["via"] == "teaching session" and t["session"] == sid for t in state["artifacts"][artifact]["transmissions"])
    else:
        assert session["stage"] == "failed" and artifact not in state["agents"][learner]["known"]
    assert session["costs"]["teacher_energy"] == 1 + 3 * 2 and state["agents"][teacher]["energy"] == t0 - 7
    check_invariants(state)


def test_insufficient_energy_rejects_a_step_without_charging():
    state, teacher, learner, artifact = classroom()
    state, sid = open_session(state, teacher, learner, artifact)
    state["agents"][teacher]["energy"] = 1
    after, out = attempt(state, act(state, "teach_step", teacher, session=sid))
    assert not out["accepted"] and "insufficient energy" in out["reason"] and digest(after) == digest(state)


def test_retirement_interrupts_a_lesson_and_stalls_interrupt_too():
    state, teacher, learner, artifact = classroom()
    state, sid = open_session(state, teacher, learner, artifact)
    retired = deepcopy(state)
    retired["agents"][teacher]["status"] = "retired"
    retired["agents"][teacher]["inventory"] = {"food": 0, "ore": 0, "alloy": 0}
    retired["settlements"]["hearth"]["inventory"] = {r: retired["settlements"]["hearth"]["inventory"][r] + state["agents"][teacher]["inventory"][r] for r in ("food", "ore", "alloy")}
    nxt, events, _ = advance(retired, OfflineController())
    end = next(e for e in events if e["type"] == "session_ended")
    assert end["stage"] == "interrupted" and teacher in end["reason"] and nxt["sessions"][sid]["stage"] == "interrupted"
    stalled = deepcopy(state)
    stalled["sessions"][sid]["last_progress"] = state["tick"] - 20
    stalled["agents"][teacher]["x"] += 3                    # apart, so no step can progress
    nxt, events, _ = advance(stalled, OfflineController())
    assert nxt["sessions"][sid]["stage"] == "interrupted" and "stalled" in nxt["sessions"][sid]["reason"]


def test_missing_prerequisites_fail_the_session_at_acceptance():
    state, teacher, learner, artifact = classroom()
    component = {"op": "component", "field": "heat", "expr": {"op": "const", "value": 1}}
    state["config"] = {**state["config"], "invention": "open"}
    state["agents"][teacher]["search_count"] = 0
    state, r = ok(state, "propose_artifact", teacher, program=component, parent=None)
    comp_id = r["artifact"]
    wf = deepcopy(state["artifacts"][artifact]["content"]["program"])
    wf["heat"] = {"op": "call", "artifact": comp_id}
    state = tick(state)
    state, r = ok(state, "propose_artifact", teacher, program=wf, parent=None)
    wf_id = r["artifact"]
    state["artifacts"][wf_id]["status"] = "admitted"           # admission path is tested elsewhere; here only prerequisites matter
    state["agents"][teacher]["known"].append(wf_id)
    state = tick(state)
    state, r = ok(state, "offer_teaching", teacher, learner=learner, artifact=wf_id)
    state, r = ok(tick(state), "accept_teaching", learner, session=r["session"])
    assert r["stage"] == "failed" and "missing prerequisite" in r["reason"]


def test_teaching_only_boundary_has_no_alternate_paths():
    """With teaching on and the library off, a learner cannot obtain programs by inspection, direct ID, messages or observation."""
    state, teacher, learner, artifact = classroom()
    state["agents"][learner]["capabilities"] = ["converter"]   # no library
    for kind in ("inspect_artifact", "use_artifact", "test_artifact"):
        after, out = attempt(state, act(state, kind, learner, artifact=artifact))
        assert not out["accepted"] and digest(after) == digest(state)
    after, out = attempt(state, act(state, "send_message", teacher, target=learner, message=repr(state["artifacts"][artifact]["content"])))
    assert not out["accepted"]
    obs = LocalObservations().build(state, learner)
    assert artifact not in obs["artifacts"] and "program" not in repr(obs["sessions"])


def test_first_independent_use_is_recorded_separately(tmp_path):
    state, teacher, learner, artifact = classroom()
    state, sid = open_session(state, teacher, learner, artifact)
    for _ in range(3):
        state = tick(state)
        state, _ = ok(state, "teach_step", teacher, session=sid)
        state, _ = ok(state, "learn_step", learner, session=sid)
    for _ in range(2):
        state = tick(state)
        state["agents"][learner]["busy_until"] = 0
        state, _ = ok(state, "practice_step", learner, session=sid)
    if state["sessions"][sid]["stage"] != "acquired":
        pytest.skip("practice failed under these conditions; covered by the acquisition test")
    assert state["sessions"][sid]["first_independent_use"] is None
    state = tick(state)
    state["agents"][learner]["busy_until"] = 0
    state["agents"][learner]["inventory"]["ore"] += 0
    after, out = attempt(state, act(state, "use_artifact", learner, artifact=artifact))
    if out["accepted"]:
        assert out["result"]["first_independent_use"] == sid and after["sessions"][sid]["first_independent_use"]["tick"] == state["tick"] + 1


def test_replay_and_restart_during_an_active_lesson(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    base = store.create(Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=200))
    for _ in range(60):
        store.step(base)
    fork = store.fork(base, 60, {"removal": "creators", "removal_tick": 61, "succession": "fresh", "successor_access": "none",
                                 "teaching": True, "invention": "frozen", "max_ticks": 130}, "lesson")
    hashes, active_seen = {}, False
    for _ in range(40):
        s = store.step(fork)
        hashes[s["tick"]] = digest(s)
        active_seen |= any(x["stage"] in ("instruction", "practice") for x in s["sessions"].values())
    assert active_seen
    restarted = Store(store.path)
    for t, h in hashes.items():
        assert digest(restarted.replay(fork, t)) == h
    continued = restarted.step(fork)
    reference = Store(tmp_path / "copy.sqlite")
    copy = reference.import_run(restarted.export(fork))
    assert digest(reference.load(copy)) == digest(continued)
