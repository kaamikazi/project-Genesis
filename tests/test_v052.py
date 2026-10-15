"""v0.5.2 (M5c): versioned random streams, paired world manifests and preflight, admission panels with a shared
final-selection panel, leave-one-out allocation flags, sealed-4 isolation."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from genesis import workshop as ws
from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.experiments5c import ALL_CONDITIONS, BASE, PRIMARY, block_scenario
from genesis.models import Action, Scenario, canonical, digest
from genesis.reducer import reduce_export
from genesis.sealed import SealedEvaluator, create_manifest
from genesis.storage import Store
from genesis.world import LocalObservations, check_invariants, new_world, physical_seed
from tools.world_manifest_m5c import manifest, physical_hash, preflight

ROOT = Path(__file__).resolve().parent.parent
BLOCK = {"block": "e99", "label_seed": 9901, "hidden_combo": [6, 1, 5], "terrain_seed": 123456, "controller_seed": 654321}


def streams(**kw):
    base = dict(seed=1, task="workshop-1", ore_per_site=900, seed_scheme="streams-1", hidden_combo=[6, 1, 5], terrain_seed=11, controller_seed=21, max_ticks=200)
    return Scenario(**{**base, **kw})


# --- streams ------------------------------------------------------------------------------------------------

def test_streams_are_independent_and_the_label_seed_is_not_a_source():
    a = new_world(streams())
    assert physical_hash(new_world(streams(controller_seed=99))) == physical_hash(a)          # controller stream only
    assert physical_hash(new_world(streams(seed=777))) == physical_hash(a)                   # label seed is not randomness
    assert physical_hash(new_world(streams(hidden_combo=[8, 2, 6]))) == physical_hash(a)    # hidden params only
    assert physical_hash(new_world(streams(terrain_seed=12))) != physical_hash(a)
    assert ws.hidden_params(streams().model_dump()) == {"split": 6, "offset": 1, "flux_threshold": 5}
    assert ws.hidden_params(streams(terrain_seed=12, controller_seed=5).model_dump()) == ws.hidden_params(streams().model_dump())


def test_legacy_scheme_reproduces_seed_derived_worlds():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900)
    assert physical_seed(cfg.model_dump()) == 101 and ws.hidden_params(cfg.model_dump()) == ws.world_params(101)
    with pytest.raises(ValueError):
        Scenario(seed=1, terrain_seed=3)                                  # stream fields require streams-1
    with pytest.raises(ValueError):
        streams(hidden_combo=[9, 0, 4])                                   # outside the workshop-1 family


def test_paired_conditions_share_initial_world_and_controller_stream():
    configs = [block_scenario(BLOCK, o) for _, o in ALL_CONDITIONS]
    assert len({physical_hash(new_world(c)) for c in configs}) == 1
    assert len({c.controller_seed for c in configs}) == 1 and len({canonical(c.hidden_combo) for c in configs}) == 1


def test_observations_never_carry_hidden_parameters_seeds_or_selection_scores():
    s = new_world(block_scenario(BLOCK, dict(PRIMARY)["beam/panels"]))
    c = OfflineController(s["config"]["controller_seed"])
    for _ in range(25):
        s, _, _ = advance(s, c)
    for aid in s["agents"]:
        text = repr(LocalObservations().build(s, aid))
        for secret in ("hidden_combo", "terrain_seed", "controller_seed", "654321", "123456", "selection_panel", "flux_threshold", "'split'"):
            assert secret not in text, secret


# --- manifest and preflight ----------------------------------------------------------------------------------

def test_manifest_draw_is_deterministic_distinct_and_role_separated():
    m1, m2 = manifest(), manifest()
    assert m1 == m2
    ev = [b for b in m1["blocks"] if b["role"] == "evaluation"]
    cal = [b for b in m1["blocks"] if b["role"] == "calibration"]
    assert len(ev) == 12 and len({tuple(b["hidden_combo"]) for b in ev}) == 12 and len(cal) == 3
    assert not {tuple(b["hidden_combo"]) for b in cal} & {tuple(b["hidden_combo"]) for b in ev}
    assert {b["hidden_combo"][0] for b in ev} == {4, 5, 6, 7, 8}                              # every split stratum represented


def test_preflight_catches_duplicates_reused_calibration_and_shared_controller_seeds():
    base = manifest()
    assert preflight(base, {"a": {}}, BASE, [], {})["passed"]
    dup = deepcopy(base)
    ev = [b for b in dup["blocks"] if b["role"] == "evaluation"]
    ev[1]["hidden_combo"] = list(ev[0]["hidden_combo"])
    assert not preflight(dup, {"a": {}}, BASE, [], {})["passed"]
    reuse = deepcopy(base)
    reuse["blocks"][3]["hidden_combo"] = list(reuse["blocks"][0]["hidden_combo"])          # evaluation reuses calibration
    assert not preflight(reuse, {"a": {}}, BASE, [], {})["passed"]
    shared = deepcopy(base)
    shared["blocks"][5]["controller_seed"] = shared["blocks"][4]["controller_seed"]
    assert not preflight(shared, {"a": {}}, BASE, [], {})["passed"]


# --- admission panels and final selection -------------------------------------------------------------------

def run(cfg, ticks):
    s = new_world(cfg)
    c = OfflineController(cfg.controller_seed)
    for _ in range(ticks):
        s, _, _ = advance(s, c)
    return s


def test_panels_activate_at_cohort_boundaries_and_compare_parent_and_child_on_the_same_cases():
    s = run(block_scenario(BLOCK, {"search_policy": "first-improvement", "validation_policy": "cohort-panels"}), 180)
    params = ws.hidden_params(s["config"])
    comps = {k: v["content"]["program"] for k, v in s["artifacts"].items() if v.get("kind") == "component"}
    seen = set()
    for a in s["artifacts"].values():
        val = a.get("validation")
        if not val or a.get("kind") != "workflow":
            continue
        k = int(val["partition"].split("-")[1])
        seen.add(k)
        assert k == (a["created_tick"] - 1) // 60 or k == a["created_tick"] // 60 or k <= 2      # the panel active at submission
        assert val["score"] == ws.score_cases(a["content"]["program"], params, ws.panel_cases(k), comps)["score"]
        if a["parent"] and val["parent_score"] is not None:
            ref = s["artifacts"][a["parent"]]
            node = ref
            while node["status"] in ("dev-tested", "not-admitted", "proposed", "withdrawn"):
                node = s["artifacts"][node["parent"]]
            assert val["parent_score"] == ws.score_cases(node["content"]["program"], params, ws.panel_cases(k), comps)["score"]
    assert len(seen) >= 2
    assert all(n <= 12 for a in s["agents"].values() for n in (a.get("panel_queries") or {}).values())


def test_final_selection_uses_one_shared_panel_with_bounded_accounting():
    s = run(block_scenario(BLOCK, {"search_policy": "first-improvement", "validation_policy": "cohort-panels"}), 180)
    f = s["lifecycle"]["freezes"][-1]
    pick, acc = f["selection_panel_best"], f["selection_accounting"]
    assert acc["evaluated"] <= 16 and acc["case_evaluations"] == acc["evaluated"] * 24
    params = ws.hidden_params(s["config"])
    comps = {k: v["content"]["program"] for k, v in s["artifacts"].items() if v.get("kind") == "component"}
    held = {k for a in s["agents"].values() if a.get("cohort", 0) == f["cohort"] for k in a["known"]}
    eligible = sorted((s["artifacts"][k] for k in held if s["artifacts"][k].get("kind") == "workflow" and s["artifacts"][k]["status"] in ("admitted", "superseded")),
                      key=lambda x: (-x["created_tick"], x["id"]))[:16]
    scores = {x["id"]: ws.score_cases(x["content"]["program"], params, ws.selection_cases(), comps)["score"] for x in eligible}
    assert pick["artifact"] in scores and pick["selection_panel_score"] == min(v for v in scores.values() if v is not None)


# --- allocation leave-one-out flags --------------------------------------------------------------------------

@pytest.mark.parametrize("disabled", ["stale-frontier", "reserve", "novelty"])
def test_leave_one_out_flags_never_disable_stale_submission_safety(disabled):
    from tests.test_v051 import stale_world
    s, pending, ref, head = stale_world("beam-alloc", alloc_disable=disabled)
    c = OfflineController(s["config"]["controller_seed"])
    rejected = 0
    for _ in range(8):
        a = c.propose(LocalObservations().build(s, "a00"))
        nxt, out = attempt(s, a)
        rejected += not out["accepted"]
        s = deepcopy(nxt)
        s["tick"] += 1
    assert rejected == 0 and s["artifacts"][pending]["status"] in ("withdrawn", "dev-tested")


def test_disabled_guard_actually_changes_behaviour():
    cfg = dict(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, search_policy="beam-alloc", max_ticks=300)
    s = new_world(Scenario(**cfg, alloc_disable="reserve"))
    s["agents"]["a00"]["search_spent"] = 46
    s["agents"]["a00"]["dev_notes"] = {"baseline": 14.0}
    c = OfflineController(7)
    a = c.propose(LocalObservations().build(s, "a00"))
    assert a.kind == "propose_artifact" and c.diagnostic.get("stop") != "reserve"


# --- persistence, reducer, final evaluation ----------------------------------------------------------------

def test_streams_and_panel_state_survive_restart_and_replay(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    rid = store.create(block_scenario(BLOCK, {"search_policy": "beam", "validation_policy": "cohort-panels"}))
    state = None
    for _ in range(70):
        state = store.step(rid)
    assert any(a.get("panel_queries") for a in state["agents"].values())
    ref = Store(tmp_path / "ref.sqlite")
    rr = ref.import_run(store.export(rid))
    del store
    reopened = Store(tmp_path / "s.sqlite")
    assert reopened.load(rid)["config"]["controller_seed"] == BLOCK["controller_seed"]
    for _ in range(20):
        a, b = reopened.step(rid), ref.step(rr)
    assert digest(a) == digest(b) and digest(reopened.replay(rid, 70)) == digest(state)


def test_reducer_reconciles_and_invariants_hold_in_a_streams_world(tmp_path):
    store = Store(tmp_path / "r.sqlite")
    rid = store.create(block_scenario(BLOCK, {"search_policy": "beam-alloc", "alloc_disable": "novelty", "validation_policy": "fixed"}))
    for _ in range(180):
        st = store.step(rid)
    check_invariants(st)
    red = reduce_export(store.export(rid))
    assert red["reconciliation"]["holdings_match_final_state"] and red["reconciliation"]["statuses_match_final_state"]
    assert "selection_panel_best" in st["lifecycle"]["freezes"][-1]


def test_sealed4_excludes_the_selection_panel_and_scores_streams_worlds(tmp_path):
    earlier = [json.loads((ROOT / p).read_text(encoding="utf-8")) for p in ("evidence/v0.4.0/protected/sealed-manifest.json",
               "evidence/v0.5.0/protected/sealed-2-manifest.json", "evidence/v0.5.1/protected/sealed-3-manifest.json")]
    m = create_manifest(tmp_path / "s4.json", "workshop-sealed-4", earlier, exclude_panels=True, exclude_selection=True)
    e = SealedEvaluator(tmp_path / "s4.json")
    assert "selection-0" in m["disjoint_from"] and not set(e.cases) & (set(ws.selection_cases()) | ws.all_panel_cases())
    cfg = block_scenario(BLOCK, {}).model_dump()
    assert e.score(cfg, ws.BASELINE, {})["score"] == ws.score_cases(ws.BASELINE, ws.hidden_params(cfg), e.cases, {})["score"]


def test_distinct_parameter_denominators():
    from tools.summarize_m5c import pair_table
    rows = [{"block": b, "seed": i, "condition": c, "status": "completed", "hidden_combo": combo, "x": v}
            for i, (b, combo) in enumerate((("e01", [4, 0, 4]), ("e02", [5, 0, 4]), ("e03", [6, 0, 4]))) for c, v in (("a", 1.0 + i), ("b", 2.0))]
    rows[-1]["x"] = None
    out = pair_table(rows, "a", "b", "x")
    assert out["expected_worlds"] == 3 and out["eligible_pairs"] == 2 and out["distinct_parameter_combinations_eligible"] == 2
