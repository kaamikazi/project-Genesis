import random

import pytest

import genesis.engine as engine
from genesis.controllers import OfflineController
from genesis.engine import advance
from genesis.models import Action, Scenario, digest
from genesis.world import new_world

KINDS = ["wait", "move", "gather", "consume", "transfer", "offer_trade", "accept_trade", "send_message", "inspect_artifact",
         "propose_artifact", "test_artifact", "use_artifact", "produce", "deposit", "withdraw",
         "submit_artifact", "offer_teaching", "accept_teaching", "teach_step", "learn_step", "practice_step", "abandon_session"]


def random_action(rng: random.Random, state, aid: str) -> Action:
    agents, a = list(state["agents"]), state["agents"][aid]
    arts = list(state["artifacts"]) or ["missing"]
    kind = rng.choice(KINDS)
    params = {
        "move": lambda: {"x": a["x"] + rng.choice([-1, 0, 1]), "y": a["y"] + rng.choice([-1, 0, 1])},
        "gather": lambda: {"site": rng.choice(list(state["sites"]))},
        "transfer": lambda: {"target": rng.choice(agents + ["hearth"]), "resource": rng.choice(["food", "ore", "alloy"]), "amount": rng.randint(1, 3)},
        "offer_trade": lambda: {"target": rng.choice(agents), "give": "ore", "give_amount": 1, "want": "food", "want_amount": 1},
        "accept_trade": lambda: {"offer": rng.choice(list(state["offers"]) or ["none"])},
        "send_message": lambda: {"target": rng.choice(agents), "message": rng.choice(["greeting", "request_food"])},
        "inspect_artifact": lambda: {"artifact": rng.choice(arts)}, "test_artifact": lambda: {"artifact": rng.choice(arts)},
        "use_artifact": lambda: {"artifact": rng.choice(arts)},
        "propose_artifact": lambda: {"program": {"op": "if_phase_lt", "threshold": rng.randint(0, 12), "then": {"op": "mode", "value": 0},
                                                 "else": {"op": "mode", "value": 1}}, "parent": None},
        "deposit": lambda: {"settlement": rng.choice(["hearth", "haven"]), "resource": "ore", "amount": rng.randint(1, 3)},
        "withdraw": lambda: {"settlement": rng.choice(["hearth", "haven"]), "resource": rng.choice(["ore", "food"]), "amount": rng.randint(1, 3)},
        "submit_artifact": lambda: {"artifact": rng.choice(arts)},
        "offer_teaching": lambda: {"learner": rng.choice(agents), "artifact": rng.choice(arts)},
        **{k: (lambda: {"session": rng.choice(list(state.get("sessions", {})) or ["none"])}) for k in ("accept_teaching", "teach_step", "learn_step", "practice_step", "abandon_session")},
    }.get(kind, lambda: {})()
    return Action(id=f"fuzz-{state['tick']}-{aid}", agent=aid, tick=state["tick"], kind=kind, params=params)


def trajectory(strategy: str, config: Scenario, ticks: int, fuzz_seed: int | None) -> list[str]:
    engine.COPY_STRATEGY, engine.VERIFY_SHARED = strategy, True
    try:
        state, rng, hashes = new_world(config), random.Random(fuzz_seed), []
        controller = OfflineController(config.controller_seed)
        for _ in range(ticks):
            overrides = {}
            if fuzz_seed is not None:
                active = [aid for aid, a in state["agents"].items() if a["status"] == "active"]
                for aid in rng.sample(active, k=min(3, len(active))):
                    overrides[aid] = random_action(rng, state, aid)
            state, _, _ = advance(state, controller, overrides)
            hashes.append(digest(state))
        return hashes
    finally:
        engine.COPY_STRATEGY, engine.VERIFY_SHARED = "scoped", False


@pytest.mark.parametrize("config,fuzz", [
    (Scenario(seed=42, max_ticks=500), None),
    (Scenario(seed=11, sharing=False, max_ticks=500), None),
    (Scenario(seed=77, removal="creators", removal_tick=40, succession="fresh", max_ticks=500), None),
    (Scenario(seed=5, population=20, removal="matched", removal_tick=30, succession="fresh", successor_access="direct", max_ticks=500), None),
    (Scenario(seed=42, max_ticks=500), 1),
    (Scenario(seed=9, population=12, removal="creators", removal_tick=25, succession="fresh", max_ticks=500), 2),
    (Scenario(seed=101, task="workshop-1", teaching=True, lifecycle="cohorts", cohort_ticks=25, sharing=False, ore_per_site=900, max_ticks=500), None),
    (Scenario(seed=103, task="workshop-1", teaching=True, ore_per_site=900, max_ticks=500), 3),
    # v0.5: beam search with components, shared credits, dependency-aware lessons, overlapping cohorts
    (Scenario(seed=101, task="workshop-1", lifecycle="cohorts", cohort_ticks=30, cohort_count=3, cohort_overlap=12, teaching=True,
              teaching_policy="package", search_policy="beam", budget_unit="credits", search_budget=48, cross_cohort_access=False,
              ore_per_site=900, max_ticks=500), None),
    (Scenario(seed=103, task="workshop-1", lifecycle="cohorts", cohort_ticks=25, cohort_count=3, cohort_overlap=10, teaching=True,
              teaching_policy="package", search_policy="beam", budget_unit="credits", search_budget=48, ore_per_site=900, max_ticks=500), 4),
])
def test_scoped_copy_matches_full_copy_reference(config, fuzz):
    ticks = 70 if fuzz is None else 50
    reference = trajectory("full", config, ticks, fuzz)
    optimized = trajectory("scoped", config, ticks, fuzz)
    assert optimized == reference
