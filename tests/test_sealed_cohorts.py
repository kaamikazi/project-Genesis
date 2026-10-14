import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from genesis import workshop as ws
from genesis.controllers import OfflineController
from genesis.engine import advance, attempt
from genesis.models import Action, Scenario, canonical, digest
from genesis.reducer import Window, reduce_export
from genesis.sealed import SealedEvaluator, create_manifest
from genesis.storage import Store
from genesis.world import LocalObservations, new_world

ROOT = Path(__file__).resolve().parent.parent


def test_no_world_path_module_imports_the_sealed_evaluator():
    for name in ("engine", "world", "controllers", "storage", "api", "experiments", "experiments4", "reducer", "workshop", "invention", "models", "cli"):
        tree = ast.parse((ROOT / "genesis" / f"{name}.py").read_text())
        imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not any("sealed" in m for m in imported) and "sealed" not in names, name


def cohort_store(tmp_path, cross=True, ticks=20, count=3):
    store = Store(tmp_path / f"c{cross}.sqlite")
    rid = store.create(Scenario(seed=101, task="workshop-1", lifecycle="cohorts", cohort_ticks=ticks, cohort_count=count,
                                cross_cohort_access=cross, ore_per_site=900, max_ticks=ticks * count))
    for _ in range(ticks * count):
        store.step(rid)
    return store, rid


def test_sealed_evaluation_needs_a_closed_run_a_freeze_and_a_matching_commitment(tmp_path):
    manifest = create_manifest(tmp_path / "protected" / "sealed.json")
    evaluator = SealedEvaluator(tmp_path / "protected" / "sealed.json")
    assert not set(evaluator.cases) & (set(ws.DEV_CASES) | set(ws.VALIDATION_CASES)) and len(evaluator.cases) == 48
    store, rid = cohort_store(tmp_path)
    export = store.export(rid)
    result = evaluator.evaluate_closed_run(export)
    assert [f["tick"] for f in result["freezes"]] == [20, 40, 60] and result["commitment"] == manifest["commitment"]
    open_run = deepcopy(export)
    open_run["state"]["tick"] -= 1
    with pytest.raises(ValueError, match="closed run"):
        evaluator.evaluate_closed_run(open_run)
    tampered = json.loads((tmp_path / "protected" / "sealed.json").read_text())
    tampered["sealed_seed"] += 1
    (tmp_path / "protected" / "sealed.json").write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="commit"):
        SealedEvaluator(tmp_path / "protected" / "sealed.json")


def test_world_trajectories_never_depend_on_the_sealed_evaluator(tmp_path, monkeypatch):
    import genesis.sealed as sealed
    monkeypatch.setattr(sealed.SealedEvaluator, "score", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sealed used in-run")))
    store, rid = cohort_store(tmp_path, ticks=15)
    state = store.load(rid)
    blob = canonical(state)
    assert '"sealed"' not in blob and "sealed_seed" not in blob and "commitment" not in blob   # no sealed score, seed or case commitment
    for aid in state["agents"]:
        if state["agents"][aid]["status"] == "active":
            obs = repr(LocalObservations().build(state, aid))
            # The submission's role label may appear; no validation record, score, parent score or selection score may.
            assert "'validation':" not in obs and "parent_score" not in obs and "selection_score" not in obs and "sealed" not in obs


def test_freeze_selects_by_validation_before_any_final_score(tmp_path):
    store, rid = cohort_store(tmp_path)
    state = store.load(rid)
    for f in state["lifecycle"]["freezes"]:
        pick = f["cohort_best"]
        if pick is None:
            continue
        candidates = [a for a in state["artifacts"].values() if a.get("cohort") == f["cohort"] and a["status"] in ("admitted", "superseded")
                      and a.get("validation") and a["created_tick"] <= f["tick"]]
        assert pick["selection_score"] == min(a["validation"]["score"] for a in candidates)
        assert '"sealed"' not in json.dumps(f) and "sealed_seed" not in json.dumps(f)


def test_submission_feedback_is_one_bit_and_validation_scores_stay_on_the_record():
    cfg = Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=200)
    state = new_world(cfg)
    c = OfflineController(cfg.controller_seed)
    submits = []
    for _ in range(30):
        state, events, _ = advance(state, c)
        submits += [e for e in events if e.get("kind") == "submit_artifact" and e["type"] == "action_accepted"]
    assert submits
    for e in submits:
        visible = {k: v for k, v in e["result"].items() if k not in ("energy_charged",)}
        assert "score" not in json.dumps(visible) and set(visible) <= {"action", "agent", "artifact", "role", "admitted", "status", "feedback_policy", "epistemic_type", "supersedes"}
        assert state["artifacts"][e["result"]["artifact"]]["validation"]["score"] is not None


def test_cohort_reset_hides_earlier_cohorts_and_preserved_shows_them(tmp_path):
    for cross in (True, False):
        store, rid = cohort_store(tmp_path, cross=cross, ticks=25, count=2)
        state = store.load(rid)
        earlier = [a for a in state["artifacts"].values() if a.get("cohort") == 0 and a["status"] == "admitted"]
        if not earlier:
            pytest.skip("no admitted cohort-0 head to test against")
        heirs = [aid for aid, a in state["agents"].items() if a["status"] == "active" and a["cohort"] == 1]
        for aid in heirs:
            visible = set(LocalObservations().build(state, aid)["artifacts"])
            learned = set(state["agents"][aid]["known"])
            for art in earlier:
                if cross:
                    continue
                assert art["id"] not in visible and art["id"] not in learned
                probe = deepcopy(state)
                probe["agents"][aid].update(x=state["settlements"][art["home"]]["x"], y=state["settlements"][art["home"]]["y"], busy_until=0)
                after, out = attempt(probe, Action(id="probe", agent=aid, tick=probe["tick"], kind="inspect_artifact", params={"artifact": art["id"]}))
                assert not out["accepted"]
        if cross:
            assert any(set(state["agents"][aid]["known"]) & {a["id"] for a in state["artifacts"].values() if a.get("cohort") == 0} for aid in heirs)


def test_cohort_transitions_retire_everyone_and_keep_roles_homes_and_budgets(tmp_path):
    store, rid = cohort_store(tmp_path)
    state = store.load(rid)
    transitions = state["lifecycle"]["transitions"]
    assert [t["tick"] for t in transitions] == [20, 40]
    for t in transitions:
        for s in t["successors"]:
            old, new = state["agents"][s["predecessor"]], state["agents"][s["successor"]]
            assert old["status"] == "retired" and old["role"] == new["role"] and old["home"] == new["home"]
            assert new["memories"] == [] or new["memories"][0]["tick"] > t["tick"]
            assert new["inheritance"]["memories_inherited"] == 0
    for agent in state["agents"].values():
        assert agent["search_count"] <= state["config"]["search_budget"]


def test_cumulative_conditions_are_identical_until_the_first_boundary(tmp_path):
    hashes = []
    for cross in (True, False):
        store, rid = cohort_store(tmp_path, cross=cross, ticks=20, count=2)
        s = json.loads(canonical(store.replay(rid, 20)))
        s["config"].pop("cross_cohort_access")
        for a in s["agents"].values():
            if a.get("inheritance"):
                a["inheritance"].pop("policy")
        hashes.append(digest(s))
    assert hashes[0] == hashes[1]


def test_v030_scenarios_reproduce_under_v040_rules(tmp_path):
    """Re-run a v0.3.0 evidence configuration and compare with the stored v0.3.0 reducer output."""
    stored = json.loads((ROOT / "evidence" / "v0.3.0" / "inheritance" / "42-successor-library.reducer.json").read_text())
    store = Store(tmp_path / "v3.sqlite")
    base = store.create(Scenario(seed=42, sharing=True, controller="search", max_ticks=60))
    for _ in range(60):
        store.step(base)
    fork = store.fork(base, 60, {"removal": "creators", "removal_tick": 61, "succession": "fresh", "successor_role": "producer",
                                 "successor_access": "library", "invention": "frozen", "max_ticks": 101})
    for _ in range(41):
        store.step(fork)
    now = reduce_export(store.export(fork), [Window(61, 101, "diagnostic")])
    for key in ("produced_alloy", "production_energy", "library_acquisitions", "use_executions", "accepted_actions", "rejected_actions"):
        assert now["overall"][key] == stored["overall"][key], key
    for category, energy in stored["overall"]["energy_by_category"].items():
        assert now["overall"]["energy_by_category"].get(category, 0) == energy, category
    pairs = zip(sorted(now["successors"], key=lambda r: r["successor"]), sorted(stored["successors"], key=lambda r: r["successor"]))
    for a, b in pairs:
        assert a["first_library_acquisition"]["tick"] == b["first_library_acquisition"]["tick"]
        assert a["first_use_with_saving"]["tick"] == b["first_use_with_saving"]["tick"]
