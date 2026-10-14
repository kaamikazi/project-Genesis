import ast
from pathlib import Path

import pytest

from genesis.models import Scenario
from genesis.reducer import Window, post_removal_window, ratio, reduce_export
from genesis.storage import Store


def export_of(tmp_path, ticks, **config):
    store = Store(tmp_path / "r.sqlite")
    rid = store.create(Scenario(max_ticks=max(ticks, 1), **config))
    for _ in range(ticks):
        store.step(rid)
    return store, rid, store.export(rid)


def test_reducer_is_implemented_independently():
    source = Path(__file__).resolve().parent.parent / "genesis" / "reducer.py"
    imports = {n.module or "" for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, ast.ImportFrom)}
    imports |= {a.name for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith((".", "genesis")) for m in imports - {"__future__"}), imports


@pytest.mark.parametrize("config", [{}, {"sharing": False}, {"removal": "creators", "removal_tick": 40},
                                    {"removal": "matched", "removal_tick": 40, "succession": "fresh"}])
def test_reducer_reconciles_holdings_and_matches_engine_counters(tmp_path, config):
    _, _, export = export_of(tmp_path, 70, **config)
    reduced = reduce_export(export, [w for w in [post_removal_window(export)] if w])
    assert reduced["reconciliation"]["holdings_match_final_state"], reduced["reconciliation"]
    assert reduced["reconciliation"]["statuses_match_final_state"]
    final = export["state"]["metrics"]
    assert reduced["overall"]["produced_alloy"] == final["produced"]
    assert reduced["overall"]["production_energy"] == final["production_energy"]
    assert reduced["final_alloy_inventory"] == sum(o["inventory"]["alloy"] for o in [*export["state"]["agents"].values(), *export["state"]["settlements"].values()])
    if config.get("removal"):
        window = reduced["windows"]["post_removal"]
        assert window["produced_alloy"] == final["produced_after_removal"]
        assert window["production_energy"] == final["production_energy_after_removal"]


def test_every_energy_change_is_accounted_for(tmp_path):
    """initial energy + restored - action-charged - fatigue == final energy, per agent, from events alone."""
    _, _, export = export_of(tmp_path, 60, removal="creators", removal_tick=30, succession="fresh")
    energy = {aid: a["energy"] for aid, a in export["initial"]["agents"].items()}
    for entry in export["ticks"]:
        for e in entry["record"]["events"]:
            if e["type"] == "action_accepted":
                energy[e["agent"]] += e["result"].get("energy_restored", 0) - e["result"]["energy_charged"]
            elif e["type"] == "environment":
                for aid, n in e["fatigue"].items():
                    energy[aid] -= n
            elif e["type"] == "lifecycle_removal":
                for s in e["successors"]:
                    energy[s["successor"]] = 30
    assert energy == {aid: a["energy"] for aid, a in export["state"]["agents"].items()}


def test_fork_origin_counts_only_events_after_the_fork(tmp_path):
    store, rid, _ = export_of(tmp_path, 30)
    fork = store.fork(rid, 30, {"max_ticks": 50})
    for _ in range(20):
        store.step(fork)
    export = store.export(fork)
    reduced = reduce_export(export)
    assert reduced["origin_tick"] == 30 and reduced["last_tick"] == 50
    assert reduced["overall"]["produced_alloy"] == export["state"]["metrics"]["produced"] - export["initial"]["metrics"]["produced"]
    assert "excluded" in reduced["starting_inventory"]


def test_zero_denominators_are_unavailable_not_zero(tmp_path):
    assert ratio(0, 0, "x")["value"] is None and ratio(0, 0, "x")["status"].startswith("unavailable")
    _, _, export = export_of(tmp_path, 5)
    reduced = reduce_export(export, [Window(5, 5, "empty")])
    empty = reduced["windows"]["empty"]
    assert empty["ticks"] == 0 and empty["produced_alloy"] == 0
    for key in ("production_energy_per_alloy", "charged_energy_per_alloy", "total_energy_per_alloy"):
        assert empty[key]["value"] is None and empty[key]["denominator"] == 0


def test_successor_evidence_is_derived_from_events(tmp_path):
    store, rid, _ = export_of(tmp_path, 60)
    fork = store.fork(rid, 60, {"removal": "creators", "removal_tick": 61, "succession": "fresh", "successor_access": "library",
                                "invention": "frozen", "max_ticks": 95})
    for _ in range(35):
        store.step(fork)
    reduced = reduce_export(store.export(fork))
    assert reduced["successors"]
    for row in reduced["successors"]:
        assert row["first_library_acquisition"]["tick"] <= row["first_use_with_saving"]["tick"]
        assert row["first_use_with_saving"]["energy"] < row["first_use_with_saving"]["baseline_energy"]
