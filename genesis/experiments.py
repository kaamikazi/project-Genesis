from __future__ import annotations

import gzip
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

from . import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
from .models import JSON, Scenario, canonical, digest
from .reducer import Window, post_removal_window, reduce_export
from .storage import Store

VERSIONS = {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION}

# (name, sharing, controller, removal). Every condition shares seed, population, rules, search budget,
# controller seed and run length; only the listed factors differ.
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
    """Engine-side counters for the UI. Experiments report the independent reducer instead."""
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


def write_gz(path: Path, value: JSON) -> JSON:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(raw, 9))
    return {"file": path.name, "uncompressed_bytes": len(raw), "compressed_bytes": path.stat().st_size}


def aggregate(rows: list[JSON], key: str) -> JSON:
    """Per-world ratios first; then both the mean of world ratios and the pooled ratio, labelled separately."""
    available = [r[key] for r in rows if r[key]["value"] is not None]
    numerator = sum(r[key]["numerator"] for r in rows)
    denominator = sum(r[key]["denominator"] for r in rows)
    return {"worlds": len(rows), "worlds_with_value": len(available),
            "mean_of_world_ratios": round(statistics.mean(x["value"] for x in available), 6) if available else None,
            "pooled_ratio": round(numerator / denominator, 6) if denominator else None,
            "pooled_numerator": numerator, "pooled_denominator": denominator,
            "note": "unavailable world ratios are excluded from the mean and counted in worlds - worlds_with_value"}


class Recorder:
    """Durable report writer: intent is saved before work so interrupted attempts stay visible."""

    def __init__(self, out: Path, name: str, report: JSON):
        self.path, self.report = out / name, report
        out.mkdir(parents=True, exist_ok=True)
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.report, indent=2), encoding="utf-8")


class PairedExperiments:
    """Descriptive whole-run comparison. Retirement conditions here are NOT a controlled knowledge-retention test:
    creators and matched workers differ in role and labour (see the inheritance diagnostic for the controlled design)."""

    def run(self, seeds: list[int], ticks: int, output: str, removal_tick: int | None = None) -> JSON:
        out = Path(output)
        removal_tick = removal_tick or max(1, ticks // 2)
        if removal_tick >= ticks:
            raise ValueError("removal tick must fall inside the run")
        store = Store(out / "experiments.sqlite")
        rec = Recorder(out, "comparison.json", {
            "protocol": "paired-phase-3", "exploratory": True, "planned_seeds": seeds, "planned_ticks": ticks,
            "stopping_rule": f"fixed length: {ticks} ticks per world", "removal_tick": removal_tick,
            "conditions": [c[0] for c in CONDITIONS], "unit": "one world run", "versions": VERSIONS,
            "attempts": [], "exclusions": [],
            "interpretation": "Finite designed task and deterministic policies. Differences follow from designed mechanics; "
                              "no emergence or statistical significance claim.",
            "intervention_boundary": "Sharing toggles only the library capability for verified procedures. Trade, transfers, settlement "
                                     "storage and the two-word message vocabulary stay enabled in every condition.",
            "removal_design": "DESCRIPTIVE ONLY. Creator retirement and matched ordinary-worker retirement differ in role and labour; "
                              "retiree inventory moves to settlement storage, which members can withdraw.",
        })
        for seed in seeds:
            for condition, sharing, controller, removal in CONDITIONS:
                config = Scenario(seed=seed, sharing=sharing, controller=controller, max_ticks=ticks, removal=removal, removal_tick=removal_tick)
                attempt: JSON = {"seed": seed, "condition": condition, "config": config.model_dump(),
                                 "config_hash": digest(config.model_dump()), "status": "started"}
                rec.report["attempts"].append(attempt)
                rec.save()
                start = time.perf_counter()
                try:
                    rid = store.create(config)
                    attempt["run_id"] = rid
                    for _ in range(ticks):
                        store.step(rid)
                    final = store.load(rid)
                    if digest(final) != digest(store.replay(rid, ticks)):
                        raise ValueError("replay mismatch")
                    export = store.export(rid)
                    window = post_removal_window(export)
                    reduced = reduce_export(export, [window] if window else [])
                    if not reduced["reconciliation"]["holdings_match_final_state"]:
                        raise ValueError(f'reducer reconciliation failed: {reduced["reconciliation"]}')
                    attempt.update(status="completed", metrics=metrics(final), reducer=reduced,
                                   wall_seconds=round(time.perf_counter() - start, 3),
                                   export=write_gz(out / f"{seed}-{condition}.json.gz", export))
                except Exception as exc:  # noqa: BLE001 - every failure is recorded
                    attempt.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 3))
                rec.save()
        rec.report["completed_runs"] = sum(a["status"] == "completed" for a in rec.report["attempts"])
        rec.report["failed_runs"] = sum(a["status"] == "failed" for a in rec.report["attempts"])
        done = [a for a in rec.report["attempts"] if a["status"] == "completed"]
        rec.report["aggregates"] = {
            c[0]: {"production_energy_per_alloy": aggregate([{"r": a["reducer"]["overall"]["production_energy_per_alloy"]} for a in done if a["condition"] == c[0]], "r"),
                   "charged_energy_per_alloy": aggregate([{"r": a["reducer"]["overall"]["charged_energy_per_alloy"]} for a in done if a["condition"] == c[0]], "r")}
            for c in CONDITIONS}
        rec.save()
        return rec.report


DIAGNOSTIC = (("successor-library", "library"), ("successor-no-library", "none"), ("successor-direct-control", "direct"))
LIVE = (("live-library", "library"), ("live-no-library", "none"))
# Fields that legitimately differ between matched continuations; everything else must be identical at the boundary.
PARITY_MASK = "successor_access, successor capabilities/known/inheritance, succession-package transmissions, lifecycle package/policy"


def physical_view(state: JSON) -> str:
    """State hash with the declared knowledge-policy differences masked out."""
    s = json.loads(canonical(state))
    s["config"].pop("successor_access")
    successors = {x["successor"] for x in s["lifecycle"]["successions"]}
    for aid in successors:
        for k in ("capabilities", "known", "inheritance"):
            s["agents"][aid].pop(k)
    for art in s["artifacts"].values():
        art["transmissions"] = [t for t in art["transmissions"] if not t["via"].startswith("succession package")]
    for item in s["lifecycle"]["successions"] + (s["lifecycle"]["removal"] or {}).get("successors", []):
        item.pop("policy", None)
        item.pop("package", None)
    return digest(s)


class InheritanceExperiment:
    """Controlled succession: matched continuations forked from one committed checkpoint per seed."""

    def run(self, seeds: list[int], output: str, checkpoint_tick: int = 60, window: int = 40, live_window: int = 100,
            ore_margin: float = 1.5, population: int = 8, ore_per_site: int = 240) -> JSON:
        out = Path(output)
        store = Store(out / "inheritance.sqlite")
        boundary = checkpoint_tick + 1
        rec = Recorder(out, "inheritance.json", {
            "protocol": "inheritance-diagnostic-1", "exploratory": True, "versions": VERSIONS, "planned_seeds": seeds, "population": population, "ore_per_site": ore_per_site,
            "checkpoint_tick": checkpoint_tick, "removal_boundary_tick": boundary,
            "diagnostic_window": Window(boundary, boundary + window, "diagnostic").describe() | {"label": "diagnostic"},
            "live_window_ticks": live_window,
            "stopping_rule": f"diagnostic forks run to tick {boundary + window}; live forks to tick {boundary + live_window}",
            "eligibility": f"at the checkpoint: >=1 verified procedure, and remaining ore >= {ore_margin} x (ore consumed per tick so far) x window",
            "design": "Each seed runs one base world (sharing on, bounded search) to the checkpoint. Matched continuations are forked "
                      "from that committed state. At the boundary the same verified creators retire under the same inventory rule "
                      "(to settlement storage) and are replaced by the same number of fresh producers. Only the successors' "
                      "knowledge policy differs. Invention is frozen identically in all diagnostic forks so relearning cannot "
                      "mask inherited retention. The live continuation (successor researchers, invention open) is a separate experiment.",
            "parity_mask": PARITY_MASK, "seeds": [],
        })
        for seed in seeds:
            row: JSON = {"seed": seed, "status": "started", "diagnostic": [], "live": []}
            rec.report["seeds"].append(row)
            rec.save()
            try:
                base = store.create(Scenario(seed=seed, population=population, ore_per_site=ore_per_site, sharing=True, controller="search", max_ticks=checkpoint_tick))
                row["base_run"] = base
                for _ in range(checkpoint_tick):
                    store.step(base)
                cp = store.checkpoint(base)
                state = store.load(base)
                verified = sorted(a["id"] for a in state["artifacts"].values() if a["status"] == "verified")
                ore_left = sum(s["stock"] for s in state["sites"].values() if s["resource"] == "ore") + \
                    sum(a["inventory"]["ore"] for a in state["agents"].values()) + sum(s["inventory"]["ore"] for s in state["settlements"].values())
                ore_used = state["initial_totals"]["ore"] - ore_left
                needed = ore_margin * ore_used / checkpoint_tick * window
                row["checkpoint"] = {**cp, "verified_procedures": verified, "ore_remaining": ore_left, "ore_needed_estimate": round(needed, 1)}
                if not verified or ore_left < needed:
                    row.update(status="ineligible", reason="no verified procedure" if not verified else "insufficient ore for the window")
                    rec.save()
                    continue
                for label, access in DIAGNOSTIC:
                    row["diagnostic"].append(self._continuation(store, out, seed, base, checkpoint_tick, label, {
                        "removal": "creators", "removal_tick": boundary, "succession": "fresh", "successor_role": "producer",
                        "successor_access": access, "invention": "frozen", "max_ticks": boundary + window},
                        Window(boundary, boundary + window, "diagnostic")))
                    rec.save()
                parity = {c["label"]: c.get("physical_hash_at_boundary") for c in row["diagnostic"]}
                removed = {c["label"]: c.get("removed") for c in row["diagnostic"]}
                row["physical_parity"] = {"hashes": parity, "identical": len(set(parity.values())) == 1 and None not in parity.values(),
                                          "same_retirees": len({json.dumps(v) for v in removed.values()}) == 1, "retirees": removed}
                for label, access in LIVE:
                    row["live"].append(self._continuation(store, out, seed, base, checkpoint_tick, label, {
                        "removal": "creators", "removal_tick": boundary, "succession": "fresh", "successor_role": "researcher",
                        "successor_access": access, "invention": "open", "max_ticks": boundary + live_window},
                        Window(boundary, boundary + live_window, "live")))
                    rec.save()
                failed = [c["label"] for c in row["diagnostic"] + row["live"] if c["status"] != "completed"]
                row["status"] = "completed" if not failed else f"partial: {failed} failed"
            except Exception as exc:  # noqa: BLE001
                row.update(status="failed", failure=f"{type(exc).__name__}: {exc}")
            rec.save()
        rec.report["aggregates"] = self._aggregates(rec.report)
        rec.save()
        return rec.report

    def _continuation(self, store: Store, out: Path, seed: int, base: str, tick: int, label: str, intervention: JSON, window: Window) -> JSON:
        item: JSON = {"label": label, "intervention": intervention, "status": "started"}
        start = time.perf_counter()
        try:
            rid = store.fork(base, tick, intervention, label)
            item["run_id"] = rid
            for _ in range(intervention["max_ticks"] - tick):
                store.step(rid)
            at_boundary = store.replay(rid, intervention["removal_tick"])
            item["physical_hash_at_boundary"] = physical_view(at_boundary)
            item["removed"] = at_boundary["lifecycle"]["removal"]["removed"]
            item["successors_at_boundary"] = [{"id": s["successor"], "known": at_boundary["agents"][s["successor"]]["known"],
                                               "capabilities": at_boundary["agents"][s["successor"]]["capabilities"],
                                               "memories": len(at_boundary["agents"][s["successor"]]["memories"])}
                                              for s in at_boundary["lifecycle"]["successions"]]
            final = store.load(rid)
            if digest(final) != digest(store.replay(rid, final["tick"])):
                raise ValueError("replay mismatch")
            export = store.export(rid)
            reduced = reduce_export(export, [window])
            if not reduced["reconciliation"]["holdings_match_final_state"]:
                raise ValueError(f'reducer reconciliation failed: {reduced["reconciliation"]}')
            w = reduced["windows"][window.label]
            sites_ore = sum(s["stock"] for s in final["sites"].values() if s["resource"] == "ore")
            own_verified = sorted({a["creator"] for a in final["artifacts"].values() if a["status"] in ("verified", "superseded")
                                   and a["created_tick"] > intervention["removal_tick"]})
            item.update(status="completed", reducer=reduced, window=w["label"] if "label" in w else window.label,
                        summary={"settlement_production_energy_per_alloy": w["production_energy_per_alloy"],
                                 "settlement_charged_energy_per_alloy": w["charged_energy_per_alloy"],
                                 "produced_alloy_in_window": w["produced_alloy"], "library_acquisitions_in_window": w["library_acquisitions"],
                                 "successors": reduced["successors"], "ore_on_sites_at_end": sites_ore, "depleted": sites_ore == 0,
                                 "remaining": reduced["remaining"], "new_verified_creators_after_boundary": own_verified},
                        wall_seconds=round(time.perf_counter() - start, 3),
                        export=write_gz(out / f"{seed}-{label}.json.gz", export))
            (out / f"{seed}-{label}.reducer.json").write_text(json.dumps(reduced, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            item.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 3))
        return item

    @staticmethod
    def _aggregates(report: JSON) -> JSON:
        result: JSON = {}
        for label, _ in DIAGNOSTIC + LIVE:
            items = [c for s in report["seeds"] for c in s["diagnostic"] + s["live"] if c["label"] == label and c["status"] == "completed"]
            successor_rows = [{"r": x["production_energy_per_alloy"]} for c in items for x in c["summary"]["successors"]]
            result[label] = {
                "settlement_production_energy_per_alloy": aggregate([{"r": c["summary"]["settlement_production_energy_per_alloy"]} for c in items], "r"),
                "successor_production_energy_per_alloy": aggregate(successor_rows, "r"),
                "successors": len(successor_rows),
                "successors_with_library_acquisition": sum(1 for c in items for x in c["summary"]["successors"] if x["first_library_acquisition"]),
                "successors_with_use_with_saving": sum(1 for c in items for x in c["summary"]["successors"] if x["first_use_with_saving"]),
                "note": "successor ratios pool agents across worlds; agents within one world are not independent samples",
            }
        return result


def benchmark(store: Store, ticks: int, population: int = 8) -> JSON:
    """Timing pass without instrumentation, then a separate short tracemalloc pass (it slows allocation)."""
    from .controllers import OfflineController
    from .engine import advance
    from .world import new_world

    config = Scenario(max_ticks=ticks, population=population)
    rid = store.create(config)
    samples = []
    start = time.perf_counter()
    for _ in range(ticks):
        then = time.perf_counter()
        store.step(rid)
        samples.append((time.perf_counter() - then) * 1000)
    seconds = time.perf_counter() - start
    state, engine_samples = new_world(config), []
    controller = OfflineController(config.controller_seed)
    for _ in range(ticks):
        then = time.perf_counter()
        state, _, _ = advance(state, controller)
        engine_samples.append((time.perf_counter() - then) * 1000)
    memory_ticks = min(ticks, 40)
    state = new_world(config)
    tracemalloc.start()
    for _ in range(memory_ticks):
        state, _, _ = advance(state, controller)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    telemetry = store.telemetry(rid)
    p95 = lambda xs: round(sorted(xs)[min(len(xs) - 1, int(len(xs) * .95))], 2)  # noqa: E731
    return {"run_id": rid, "ticks": ticks, "population": population, "platform": platform.platform(),
            "processor": platform.processor(), "python": platform.python_version(), "versions": VERSIONS,
            "committed": {"total_seconds": round(seconds, 3), "ticks_per_second": round(ticks / seconds, 2),
                          "median_tick_ms": round(statistics.median(samples), 2), "p95_tick_ms": p95(samples),
                          "stdev_tick_ms": round(statistics.stdev(samples), 2) if len(samples) > 1 else None,
                          "note": "store.step wall time: load + validate + engine + delta + SQLite commit with fsync"},
            "engine_only": {"median_tick_ms": round(statistics.median(engine_samples), 2), "p95_tick_ms": p95(engine_samples),
                            "note": "advance() in memory, no persistence"},
            "memory": {"peak_traced_python_bytes": peak, "ticks": memory_ticks,
                       "note": "tracemalloc Python allocations during engine-only ticks, not process RSS; measured separately from timing"},
            "storage": {"record_bytes_total": telemetry["bytes"], "record_bytes_per_tick": round((telemetry["bytes"] or 0) / ticks),
                        "database_bytes": telemetry["database_bytes"]},
            "model_overhead_ms": 0, "model_calls": 0, "cost_usd": 0}
