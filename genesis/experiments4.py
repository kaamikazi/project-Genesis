"""Milestone 4 protocols: teaching and acquisition (A) and cumulative invention across cohorts (B).

World runs never touch the sealed evaluator; `score_sealed` runs afterwards on closed exports only.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from .experiments import VERSIONS, Recorder, aggregate, physical_view, write_gz
from .models import JSON, Scenario, canonical, digest
from .reducer import Window, reduce_export
from .storage import Store

TEACHING_CONDITIONS = (
    ("teaching", {"successor_access": "none", "teaching": True}),
    ("library", {"successor_access": "library", "teaching": False}),
    ("no-transfer", {"successor_access": "none", "teaching": False}),
    ("direct-control", {"successor_access": "direct", "teaching": False}),
)
COHORT_CONDITIONS = (("preserved", True), ("reset", False))
PERFORMANCE_LEVELS = (11.0, 9.0, 7.5, 6.5)   # validation cost-per-alloy thresholds, fixed before evaluation runs


def ratio_value(r: JSON | None) -> float | None:
    return None if r is None else r.get("value")


class TeachingExperiment:
    """A: matched forks from one checkpoint; successors replace the creators; only knowledge paths differ."""

    def run(self, seeds: list[int], output: str, checkpoint: int, window: int, ore_per_site: int, population: int = 8,
            label: str = "evaluation") -> JSON:
        out = Path(output)
        store = Store(out / "teaching.sqlite")
        boundary = checkpoint + 1
        rec = Recorder(out, "teaching.json", {
            "protocol": "teaching-acquisition-1", "label": label, "exploratory": True, "versions": VERSIONS, "seeds": [],
            "planned_seeds": seeds, "checkpoint_tick": checkpoint, "boundary_tick": boundary,
            "window": Window(boundary, boundary + window, "window").describe(), "ore_per_site": ore_per_site, "population": population,
            "conditions": {name: delta for name, delta in TEACHING_CONDITIONS},
            "design": "One base world per seed (workshop-1, library sharing, bounded search) runs to the checkpoint. Matched continuations are "
                      "forked there; at the boundary the same admitted-workflow creators retire to storage and fresh producers replace them. "
                      "Invention is frozen in every continuation. Only the successors' knowledge path differs: costly teaching by existing "
                      "holders, library inspection (2 energy), no transferable knowledge, or a labelled direct-transfer control.",
            "eligibility": "at the checkpoint, every settlement has an admitted workflow held by at least one non-creator, and remaining ore "
                           ">= 1.5 x ore used per tick so far x window"})
        for seed in seeds:
            row: JSON = {"seed": seed, "status": "started", "continuations": []}
            rec.report["seeds"].append(row)
            rec.save()
            try:
                base = store.create(Scenario(seed=seed, population=population, task="workshop-1", ore_per_site=ore_per_site,
                                             sharing=True, controller="search", max_ticks=checkpoint))
                for _ in range(checkpoint):
                    store.step(base)
                state = store.load(base)
                creators = {a["creator"] for a in state["artifacts"].values() if a["status"] == "admitted"}
                holders = {h: sorted(aid for aid, ag in state["agents"].items() if ag["home"] == h and aid not in creators and any(
                    state["artifacts"][k]["status"] in ("admitted", "superseded") for k in ag["known"] if k in state["artifacts"]))
                    for h in state["settlements"]}
                ore_left = sum(s["stock"] for s in state["sites"].values() if s["resource"] == "ore") + sum(a["inventory"]["ore"] for a in state["agents"].values())
                needed = 1.5 * (state["initial_totals"]["ore"] - ore_left) / checkpoint * window
                row["checkpoint"] = {"tick": checkpoint, "state_hash": digest(state), "creators": sorted(creators), "holders": holders,
                                     "ore_remaining": ore_left, "ore_needed_estimate": round(needed, 1)}
                if not creators or not all(holders.values()) or ore_left < needed:
                    row.update(status="ineligible", reason="no admitted workflow holder in some settlement" if not all(holders.values()) or not creators else "insufficient ore")
                    rec.save()
                    continue
                for name, delta in TEACHING_CONDITIONS:
                    intervention = {"removal": "creators", "removal_tick": boundary, "succession": "fresh", "successor_role": "producer",
                                    "invention": "frozen", "max_ticks": boundary + window, **delta}
                    row["continuations"].append(self._continuation(store, out, seed, base, checkpoint, name, intervention, Window(boundary, boundary + window, "window")))
                    rec.save()
                hashes = {c["label"]: c.get("physical_hash_at_boundary") for c in row["continuations"]}
                row["physical_parity"] = {"hashes": hashes, "identical": len(set(hashes.values())) == 1 and None not in hashes.values()}
                failed = [c["label"] for c in row["continuations"] if c["status"] != "completed"]
                row["status"] = "completed" if not failed else f"partial: {failed} failed"
            except Exception as exc:  # noqa: BLE001 - every failure is recorded
                row.update(status="failed", failure=f"{type(exc).__name__}: {exc}")
            rec.save()
        rec.report["aggregates"] = self._aggregates(rec.report)
        rec.save()
        return rec.report

    def _continuation(self, store: Store, out: Path, seed: int, base: str, tick: int, label: str, intervention: JSON, window: Window) -> JSON:
        item: JSON = {"label": label, "intervention": intervention, "status": "started"}
        start = time.perf_counter()
        try:
            rid = store.fork(base, tick, intervention, f"A-{label}")
            item["run_id"] = rid
            for _ in range(intervention["max_ticks"] - tick):
                store.step(rid)
            at_boundary = store.replay(rid, intervention["removal_tick"])
            item["physical_hash_at_boundary"] = physical_view(at_boundary)
            final = store.load(rid)
            if digest(final) != digest(store.replay(rid, final["tick"])):
                raise ValueError("replay mismatch")
            export = store.export(rid)
            red = reduce_export(export, [window])
            if not red["reconciliation"]["holdings_match_final_state"] or not red["reconciliation"]["statuses_match_final_state"]:
                raise ValueError(f'reducer reconciliation failed: {red["reconciliation"]}')
            w = red["windows"]["window"]
            heirs = []
            for s in red["successors"]:
                acquired = s["first_library_acquisition"] or s["first_acquisition_by_teaching"]
                acquired_tick = acquired["tick"] if acquired else (window.start if s["package"] else None)
                heirs.append({**{k: s[k] for k in ("successor", "predecessor", "policy", "package", "first_library_acquisition",
                                                   "first_acquisition_by_teaching", "first_use_with_saving", "use_executions", "uses_with_saving",
                                                   "produced_alloy", "production_energy_per_alloy")},
                              "acquired_tick": acquired_tick, "ticks_to_acquisition": None if acquired_tick is None else acquired_tick - window.start,
                              "ticks_to_use_with_saving": None if not s["first_use_with_saving"] else s["first_use_with_saving"]["tick"] - window.start,
                              "active_at_end": final["agents"][s["successor"]]["status"] == "active"})
            sessions = red["sessions"]
            item.update(status="completed", wall_seconds=round(time.perf_counter() - start, 2),
                        summary={"successors": heirs,
                                 "sessions": {"offered": len(sessions), "acquired": sum(x["outcome"] == "acquired" for x in sessions),
                                              "failed": sum(x["outcome"] == "failed" for x in sessions),
                                              "interrupted_or_expired": sum(x["outcome"] in ("interrupted", "expired") for x in sessions),
                                              "open_at_end": sum(x["outcome"] is None for x in sessions),
                                              "teacher_energy": sum(x["teacher_energy"] for x in sessions), "learner_energy": sum(x["learner_energy"] for x in sessions),
                                              "teacher_ticks": sum(x["teacher_ticks"] for x in sessions), "learner_ticks": sum(x["learner_ticks"] for x in sessions),
                                              "reasons": sorted({x["reason"] for x in sessions if x["reason"]})},
                                 "settlement": {"produced_alloy": w["produced_alloy"], "production_energy_per_alloy": w["production_energy_per_alloy"],
                                                "charged_energy_per_alloy": w["charged_energy_per_alloy"], "energy_by_category": w["energy_by_category"],
                                                "active_at_end": sum(a["status"] == "active" for a in final["agents"].values())},
                                 "ore_on_sites_at_end": sum(s["stock"] for s in final["sites"].values() if s["resource"] == "ore")},
                        export=write_gz(out / f"{seed}-A-{label}.json.gz", export))
            (out / f"{seed}-A-{label}.reducer.json").write_text(json.dumps(red, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            item.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 2))
        return item

    @staticmethod
    def _aggregates(report: JSON) -> JSON:
        result = {}
        for name, _ in TEACHING_CONDITIONS:
            items = [c for s in report["seeds"] for c in s["continuations"] if c["label"] == name and c["status"] == "completed"]
            heirs = [h for c in items for h in c["summary"]["successors"]]
            acq = [h["ticks_to_acquisition"] for h in heirs if h["ticks_to_acquisition"] is not None]
            use = [h["ticks_to_use_with_saving"] for h in heirs if h["ticks_to_use_with_saving"] is not None]
            result[name] = {
                "worlds": len(items), "successors": len(heirs), "acquired": len(acq), "used_with_saving": len(use),
                "median_ticks_to_acquisition": statistics.median(acq) if acq else None,
                "median_ticks_to_use_with_saving": statistics.median(use) if use else None,
                "successor_production_energy_per_alloy": aggregate([{"r": h["production_energy_per_alloy"]} for h in heirs], "r"),
                "settlement_production_energy_per_alloy": aggregate([{"r": c["summary"]["settlement"]["production_energy_per_alloy"]} for c in items], "r"),
                "settlement_charged_energy_per_alloy": aggregate([{"r": c["summary"]["settlement"]["charged_energy_per_alloy"]} for c in items], "r"),
                "teaching_energy_teacher": sum(c["summary"]["sessions"]["teacher_energy"] for c in items),
                "teaching_energy_learner": sum(c["summary"]["sessions"]["learner_energy"] for c in items),
                "sessions_failed": sum(c["summary"]["sessions"]["failed"] for c in items),
                "sessions_interrupted": sum(c["summary"]["sessions"]["interrupted_or_expired"] for c in items),
                "successors_active_at_end": sum(h["active_at_end"] for h in heirs),
                "note": "successors pooled across worlds are not independent samples"}
        return result


class CumulativeExperiment:
    """B: scheduled cohorts from tick 0; preserved vs reset cross-cohort library access; equal budgets."""

    def run(self, seeds: list[int], output: str, cohort_ticks: int, cohort_count: int, ore_per_site: int, search_budget: int,
            population: int = 8, label: str = "evaluation") -> JSON:
        out = Path(output)
        store = Store(out / "cumulative.sqlite")
        rec = Recorder(out, "cumulative.json", {
            "protocol": "cumulative-invention-1", "label": label, "exploratory": True, "versions": VERSIONS, "planned_seeds": seeds,
            "cohort_ticks": cohort_ticks, "cohort_count": cohort_count, "ore_per_site": ore_per_site, "search_budget_per_researcher_lifetime": search_budget,
            "population": population, "performance_levels": PERFORMANCE_LEVELS, "conditions": {n: {"cross_cohort_access": c} for n, c in COHORT_CONDITIONS},
            "design": "Both conditions start from the same world (workshop-1, library sharing within a cohort, bounded search, teaching off). Every "
                      f"{cohort_ticks} ticks the whole cohort retires to storage and an identical fresh cohort replaces it. 'preserved' lets the "
                      "library show admitted workflows of earlier cohorts; 'reset' hides them. Each researcher has the same proposal budget. "
                      "Freezes select artifacts by validation evidence at each boundary and at the end; sealed scores are computed after the run closes.",
            "selection_rule": "lowest validation score among admitted or superseded workflows; ties by creation tick then id",
            "worlds": []})
        for seed in seeds:
            for name, cross in COHORT_CONDITIONS:
                config = Scenario(seed=seed, population=population, task="workshop-1", lifecycle="cohorts", cohort_ticks=cohort_ticks,
                                  cohort_count=cohort_count, cross_cohort_access=cross, ore_per_site=ore_per_site, search_budget=search_budget,
                                  sharing=True, controller="search", max_ticks=cohort_ticks * cohort_count)
                item: JSON = {"seed": seed, "condition": name, "config": config.model_dump(), "config_hash": digest(config.model_dump()), "status": "started"}
                rec.report["worlds"].append(item)
                rec.save()
                start = time.perf_counter()
                try:
                    rid = store.create(config)
                    item["run_id"] = rid
                    for _ in range(config.max_ticks):
                        store.step(rid)
                    final = store.load(rid)
                    if digest(final) != digest(store.replay(rid, final["tick"])):
                        raise ValueError("replay mismatch")
                    boundary = store.replay(rid, cohort_ticks)
                    masked = json.loads(canonical(boundary))
                    masked["config"].pop("cross_cohort_access")
                    for agent in masked["agents"].values():       # successor records name the declared policy; mask only that text
                        if agent.get("inheritance"):
                            agent["inheritance"].pop("policy", None)
                    item["parity_hash_at_first_boundary"] = digest(masked)
                    export = store.export(rid)
                    red = reduce_export(export, [Window(k * cohort_ticks, (k + 1) * cohort_ticks, f"cohort-{k}") for k in range(cohort_count)])
                    if not red["reconciliation"]["holdings_match_final_state"] or not red["reconciliation"]["statuses_match_final_state"]:
                        raise ValueError(f'reducer reconciliation failed: {red["reconciliation"]}')
                    item.update(status="completed", wall_seconds=round(time.perf_counter() - start, 2), summary=self._summary(final, red, cohort_ticks, cohort_count),
                                export=write_gz(out / f"{seed}-B-{name}.json.gz", export))
                    (out / f"{seed}-B-{name}.reducer.json").write_text(json.dumps(red, indent=2), encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    item.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 2))
                rec.save()
            pair = [w for w in rec.report["worlds"] if w["seed"] == seed and w.get("parity_hash_at_first_boundary")]
            rec.report.setdefault("parity", []).append({"seed": seed, "identical_at_first_boundary": len(pair) == 2 and len({w["parity_hash_at_first_boundary"] for w in pair}) == 1})
            rec.save()
        return rec.report

    @staticmethod
    def _summary(final: JSON, red: JSON, cohort_ticks: int, cohort_count: int) -> JSON:
        arts = final["artifacts"]
        per_cohort = []
        for k in range(cohort_count):
            w = red["windows"][f"cohort-{k}"]
            mine = [x for x in red["lineage"] if x["cohort"] == k]
            per_cohort.append({"cohort": k, "proposals": len(mine), "admitted": sum(bool(x["admitted"]) for x in mine),
                               "cross_generation_attempts": sum(1 for x in mine if x["parent_cohort"] is not None and x["parent_cohort"] < k),
                               "cross_generation_admitted": sum(1 for x in mine if x["parent_cohort"] is not None and x["parent_cohort"] < k and x["admitted"]),
                               "search_energy": w["energy_by_category"].get("search", 0), "evaluation_energy": w["energy_by_category"].get("evaluation", 0),
                               "learning_energy": w["energy_by_category"].get("learning", 0), "production_energy": w["production_energy"],
                               "produced_alloy": w["produced_alloy"], "production_energy_per_alloy": w["production_energy_per_alloy"],
                               "charged_energy_per_alloy": w["charged_energy_per_alloy"]})
        admitted = sorted(((a["validation"]["score"], a["created_tick"], a["id"]) for a in arts.values()
                           if a.get("task") == "workshop-1" and a["status"] in ("admitted", "superseded") and a.get("validation")), key=lambda t: (t[1], t[0]))
        levels = {}
        for level in PERFORMANCE_LEVELS:
            hit = next((t for s, t, _ in admitted if s <= level), None)
            levels[str(level)] = hit
        return {"freezes": red["freezes"], "per_cohort": per_cohort, "cross_generation": red["cross_generation"],
                "first_tick_reaching_validation_level": levels,
                "overall": {k: red["overall"][k] for k in ("produced_alloy", "production_energy", "charged_action_energy", "proposals", "submissions", "admitted",
                                                           "dev_tests", "energy_by_category", "production_energy_per_alloy", "charged_energy_per_alloy")},
                "ore_on_sites_at_end": sum(s["stock"] for s in final["sites"].values() if s["resource"] == "ore"),
                "remaining": red["remaining"], "lineage": red["lineage"]}


def score_sealed(evaluator, report_path: Path, export_dir: Path) -> JSON:
    """After every run is closed: sealed scores for frozen artifacts. Writes a separate report."""
    import gzip
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = {"version": evaluator.manifest["version"], "commitment": evaluator.commitment, "worlds": []}
    for item in report["worlds"]:
        if item["status"] != "completed":
            results["worlds"].append({"seed": item["seed"], "condition": item["condition"], "status": item["status"]})
            continue
        export = json.loads(gzip.decompress((export_dir / item["export"]["file"]).read_bytes()))
        results["worlds"].append({"seed": item["seed"], "condition": item["condition"], "status": "scored", **evaluator.evaluate_closed_run(export)})
    return results
