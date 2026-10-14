from __future__ import annotations

import gzip
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

from . import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
from .models import JSON, Scenario, digest
from .storage import Store

# (name, sharing, controller, removal). Every condition shares seed, population, rules, search
# budget and run length; only the listed factors differ. Removal conditions form a 2x2 design.
CONDITIONS = (
    ("sharing", True, "search", "none"),
    ("restricted", False, "search", "none"),
    ("baseline", True, "baseline", "none"),
    ("sharing-remove-creators", True, "search", "creators"),
    ("sharing-remove-matched", True, "search", "matched"),
    ("restricted-remove-creators", False, "search", "creators"),
    ("restricted-remove-matched", False, "search", "matched"),
)


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(state: JSON) -> JSON:
    m = state["metrics"]
    active = sum(a["status"] == "active" for a in state["agents"].values())
    holdings = [sum(a["inventory"].values()) for a in state["agents"].values() if a["status"] == "active"]
    removal = state.get("lifecycle", {}).get("removal")
    return {**m, "active_population": active, "population": len(state["agents"]),
            "verified_artifacts": sum(a["status"] == "verified" for a in state["artifacts"].values()),
            "rejected_artifacts": sum(a["status"] == "rejected" for a in state["artifacts"].values()),
            "energy_per_alloy": ratio(m["production_energy"], m["produced"]),
            "energy_per_alloy_after_removal": ratio(m.get("production_energy_after_removal", 0), m.get("produced_after_removal", 0)),
            "removed_agents": removal["removed"] if removal else [],
            "inventory_range": max(holdings) - min(holdings) if holdings else 0,
            "ledger": state["ledger"], "tick": state["tick"], "state_hash": digest(state)}


def paired(report: JSON, seed: int, left: str, right: str, fields: tuple[str, ...]) -> JSON | None:
    a = next((x for x in report["attempts"] if x["seed"] == seed and x["condition"] == left), None)
    b = next((x for x in report["attempts"] if x["seed"] == seed and x["condition"] == right), None)
    if not a or not b or a["status"] != "completed" or b["status"] != "completed":
        return None
    row: JSON = {"seed": seed, "left": left, "right": right}
    for f in fields:
        x, y = a["metrics"][f], b["metrics"][f]
        row[f] = {"left": x, "right": y, "difference": None if x is None or y is None else round(x - y, 4)}
    return row


class PairedExperiments:
    def run(self, seeds: list[int], ticks: int, output: str, removal_tick: int | None = None) -> JSON:
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        removal_tick = removal_tick or max(1, ticks // 2)
        if removal_tick >= ticks:
            raise ValueError("removal tick must fall inside the run")
        store = Store(out / "experiments.sqlite")
        report: JSON = {
            "protocol": "paired-phase-2", "exploratory": True, "planned_seeds": seeds, "planned_ticks": ticks,
            "removal_tick": removal_tick, "conditions": [c[0] for c in CONDITIONS], "unit": "one world run",
            "versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION},
            "attempts": [], "exclusions": [],
            "interpretation": "Finite designed task and deterministic policies. Differences follow from designed "
                              "mechanics; no emergence or statistical significance claim.",
            "intervention_boundary": "Sharing toggles only library access to other agents' verified artifacts. "
                                     "Trade, transfers and the two-word message vocabulary stay enabled in every condition.",
            "removal_design": "Creator removal retires verified-artifact creators at removal_tick and moves their inventory to "
                              "settlement storage; the matched control retires the same number of non-creators from the same settlements.",
        }

        def save() -> None:
            (out / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

        for seed in seeds:
            for condition, sharing, controller, removal in CONDITIONS:
                config = Scenario(seed=seed, sharing=sharing, controller=controller, max_ticks=ticks,
                                  removal=removal, removal_tick=removal_tick)
                attempt: JSON = {"seed": seed, "condition": condition, "config": config.model_dump(), "status": "started"}
                report["attempts"].append(attempt)
                save()  # Durable intent before work; interrupted attempts remain visible.
                start = time.perf_counter()
                try:
                    rid = store.create(config)
                    attempt["run_id"] = rid
                    for _ in range(ticks):
                        store.step(rid)
                    final = store.load(rid)
                    if digest(final) != digest(store.replay(rid, ticks)):
                        raise ValueError("replay mismatch")
                    attempt.update(status="completed", metrics=metrics(final), wall_seconds=round(time.perf_counter() - start, 3))
                    filename = f"{seed}-{condition}.json.gz"
                    with gzip.open(out / filename, "wt", encoding="utf-8") as handle:
                        json.dump(store.export(rid), handle, separators=(",", ":"))
                    attempt["export"] = filename
                except Exception as exc:
                    attempt.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 3))
                save()
        core = ("produced", "energy_per_alloy", "adoptions", "verified_artifacts", "active_population")
        after = ("produced_after_removal", "energy_per_alloy_after_removal", "uses_after_creator_removal")
        comparisons = {
            "sharing_vs_restricted": [paired(report, s, "sharing", "restricted", core) for s in seeds],
            "creator_removal_vs_matched_with_sharing": [paired(report, s, "sharing-remove-creators", "sharing-remove-matched", after) for s in seeds],
            "creator_removal_vs_matched_restricted": [paired(report, s, "restricted-remove-creators", "restricted-remove-matched", after) for s in seeds],
            "creator_removal_sharing_vs_restricted": [paired(report, s, "sharing-remove-creators", "restricted-remove-creators", after) for s in seeds],
        }
        report["paired"] = {k: [r for r in v if r] for k, v in comparisons.items()}
        report["completed_runs"] = sum(a["status"] == "completed" for a in report["attempts"])
        report["failed_runs"] = sum(a["status"] == "failed" for a in report["attempts"])
        save()
        return report


def benchmark(store: Store, ticks: int) -> JSON:
    """Timing pass without instrumentation, then a separate short tracemalloc pass (it slows allocation)."""
    from .controllers import OfflineController
    from .engine import advance
    from .world import new_world

    rid = store.create(Scenario(max_ticks=ticks))
    samples = []
    start = time.perf_counter()
    for _ in range(ticks):
        then = time.perf_counter()
        store.step(rid)
        samples.append((time.perf_counter() - then) * 1000)
    seconds = time.perf_counter() - start
    state, engine_samples = new_world(Scenario(max_ticks=ticks)), []
    for _ in range(ticks):
        then = time.perf_counter()
        state, _, _ = advance(state, OfflineController())
        engine_samples.append((time.perf_counter() - then) * 1000)
    memory_ticks = min(ticks, 40)
    state = new_world(Scenario(max_ticks=ticks))
    tracemalloc.start()
    for _ in range(memory_ticks):
        state, _, _ = advance(state, OfflineController())
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    telemetry = store.telemetry(rid)
    return {"run_id": rid, "ticks": ticks, "population": 8, "platform": platform.platform(),
            "processor": platform.processor(), "python": platform.python_version(), "engine": ENGINE_VERSION,
            "committed": {"total_seconds": round(seconds, 3), "ticks_per_second": round(ticks / seconds, 2),
                          "median_tick_ms": round(statistics.median(samples), 2),
                          "p95_tick_ms": round(sorted(samples)[min(len(samples) - 1, int(len(samples) * .95))], 2),
                          "note": "store.step wall time: load + validate + engine + delta + SQLite commit with fsync"},
            "engine_only": {"median_tick_ms": round(statistics.median(engine_samples), 2),
                            "p95_tick_ms": round(sorted(engine_samples)[min(len(engine_samples) - 1, int(len(engine_samples) * .95))], 2),
                            "note": "advance() in memory, no persistence"},
            "memory": {"peak_traced_python_bytes": peak, "ticks": memory_ticks,
                       "note": "tracemalloc Python allocations during engine-only ticks, not process RSS"},
            "storage": {"record_bytes_total": telemetry["bytes"], "record_bytes_per_tick": round((telemetry["bytes"] or 0) / ticks),
                        "database_bytes": telemetry["database_bytes"]},
            "model_overhead_ms": 0, "model_calls": 0, "cost_usd": 0}
