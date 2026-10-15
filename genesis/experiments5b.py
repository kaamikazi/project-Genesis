"""M5b (v0.5.1) protocols, kept separate so their results are never merged:

- RepairedRerun: the v0.5.0 P and T world configurations re-run under the repaired engine and controllers
  (retrospective; labelled "repaired rerun", never a replacement for the v0.5.0 evidence).
- AllocationExperiment: repaired beam vs repaired beam + allocation bundle, crossed with preserved vs reset access;
  first-improvement as a fixed reference (prospective; frozen protocol).
- MentorshipExperiment: library vs teaching-only vs none under one declared mentorship schedule that is identical in
  every condition (prospective; frozen protocol).

World runs never touch the sealed evaluator; sealed-3 scoring runs after every run is closed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .experiments import VERSIONS, Recorder, write_gz
from .experiments5 import _parity_hash, _summary
from .models import JSON, Scenario, digest
from .reducer import Window, reduce_export
from .storage import Store

ALLOCATION_CONDITIONS = (
    ("beam/preserved", {"search_policy": "beam", "cross_cohort_access": True}),
    ("beam/reset", {"search_policy": "beam", "cross_cohort_access": False}),
    ("beam-alloc/preserved", {"search_policy": "beam-alloc", "cross_cohort_access": True}),
    ("beam-alloc/reset", {"search_policy": "beam-alloc", "cross_cohort_access": False}),
    ("first-improvement/preserved", {"search_policy": "first-improvement", "cross_cohort_access": True}),
    ("first-improvement/reset", {"search_policy": "first-improvement", "cross_cohort_access": False}),
)
MENTORSHIP_CONDITIONS = (
    ("library", {"cross_cohort_access": True, "teaching": False}),
    ("teaching-only", {"cross_cohort_access": False, "teaching": True, "teaching_policy": "package-scheduled"}),
    ("none", {"cross_cohort_access": False, "teaching": False}),
)


def run_world(store: Store, out: Path, file: str, seed: int, condition: str, config: Scenario, settings: JSON) -> JSON:
    """Run one world to closure, verify replay and reducer reconciliation, write export and reducer output."""
    item: JSON = {"seed": seed, "condition": condition, "config": config.model_dump(), "config_hash": digest(config.model_dump()), "status": "started"}
    start = time.perf_counter()
    try:
        rid = store.create(config)
        item["run_id"] = rid
        for _ in range(config.max_ticks):
            store.step(rid)
        final = store.load(rid)
        if digest(final) != digest(store.replay(rid, final["tick"])):
            raise ValueError("replay mismatch")
        item["parity_hash_initial"] = _parity_hash(store.replay(rid, 0), ("cross_cohort_access", "search_policy", "teaching", "teaching_policy"))
        arrival = config.cohort_ticks - config.cohort_overlap
        item["access_parity_tick"] = arrival
        item["access_parity_hash"] = _parity_hash(store.replay(rid, arrival), ("cross_cohort_access",))
        export = store.export(rid)
        ct, cc = config.cohort_ticks, config.cohort_count
        red = reduce_export(export, [Window(k * ct, (k + 1) * ct, f"cohort-{k}") for k in range(cc)])
        if not red["reconciliation"]["holdings_match_final_state"] or not red["reconciliation"]["statuses_match_final_state"]:
            raise ValueError(f'reducer reconciliation failed: {red["reconciliation"]}')
        tag = condition.replace("/", "-")
        summary = _summary(final, red, ct, cc)
        summary["metrics"] = red["metrics"]
        summary["population"] = {"base": red["metrics"]["population.base"], "peak_active": red["metrics"]["population.peak_active"]}
        item.update(status="completed", wall_seconds=round(time.perf_counter() - start, 2), summary=summary,
                    export=write_gz(out / f"{seed}-{file}-{tag}.json.gz", export))
        (out / f"{seed}-{file}-{tag}.reducer.json").write_text(json.dumps(red, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001  -- failures are recorded, never hidden
        item.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 2))
    return item


class _Protocol:
    protocol = file = ""
    conditions: tuple = ()

    def base(self, s: JSON) -> JSON:
        return {"population": s["population"], "task": "workshop-1", "lifecycle": "cohorts", "cohort_ticks": s["cohort_ticks"],
                "cohort_count": s["cohort_count"], "cohort_overlap": s["cohort_overlap"], "ore_per_site": s["ore_per_site"],
                "search_budget": s["search_budget"], "budget_unit": "credits", "sharing": True, "controller": "search",
                "max_ticks": s["cohort_ticks"] * s["cohort_count"]}

    def run(self, seeds: list[int], output: str, settings: JSON, label: str = "evaluation") -> JSON:
        out = Path(output)
        store = Store(out / f"{self.file}.sqlite")
        rec = Recorder(out, f"{self.file}.json", {"protocol": self.protocol, "label": label, "versions": VERSIONS, "planned_seeds": seeds,
                                                    "settings": settings, "conditions": {n: c for n, c in self.conditions},
                                                    "design": self.design(settings), "worlds": []})
        for seed in seeds:
            for name, overrides in self.conditions:
                config = Scenario(**{**self.base(settings), "seed": seed, **overrides})
                item = run_world(store, out, self.file, seed, name, config, settings)
                rec.report["worlds"].append(item)
                rec.save()
            rec.report.setdefault("parity", []).append(self.parity(rec.report["worlds"], seed))
            rec.save()
        return rec.report

    def design(self, s: JSON) -> str:
        return ""

    def parity(self, worlds: list[JSON], seed: int) -> JSON:
        rows = [w for w in worlds if w["seed"] == seed and w.get("parity_hash_initial")]
        return {"seed": seed, "identical_initial_state": len({w["parity_hash_initial"] for w in rows}) == 1 and len(rows) == len(self.conditions)}


class AllocationExperiment(_Protocol):
    protocol, file, conditions = "allocation-1", "allocation", ALLOCATION_CONDITIONS

    def base(self, s: JSON) -> JSON:
        return {**super().base(s), "cohort_overlap": s.get("allocation_overlap", 0), "teaching": False}

    def design(self, s: JSON) -> str:
        return ("Primary contrast: repaired beam vs repaired beam plus the allocation bundle (reserve, exact novelty, bounded generation, no spending on "
                "stale lineages), each with preserved and reset cross-cohort access. first-improvement (repaired) is a fixed reference, not tuned. "
                "Grammar, admission policy, world rules, budgets (48 credits), lifecycle and resources are identical. The design identifies the "
                "bundle's combined effect, not the effect of each guard.")

    def parity(self, worlds: list[JSON], seed: int) -> JSON:
        out = super().parity(worlds, seed)
        by = {w["condition"]: w.get("access_parity_hash") for w in worlds if w["seed"] == seed}
        for policy in ("beam", "beam-alloc", "first-improvement"):
            out[f"{policy}_preserved_vs_reset_identical_at_first_arrival"] = by.get(f"{policy}/preserved") is not None and by.get(f"{policy}/preserved") == by.get(f"{policy}/reset")
        return out


class MentorshipExperiment(_Protocol):
    protocol, file, conditions = "mentorship-1", "mentorship", MENTORSHIP_CONDITIONS

    def base(self, s: JSON) -> JSON:
        return {**super().base(s), "search_policy": "beam"}

    def design(self, s: JSON) -> str:
        return (f"Cohorts of {s['cohort_ticks']} ticks; each successor cohort arrives {s['cohort_overlap']} ticks before its seniors retire, identically in "
                "every condition (same physical population, resources and action time). Repaired beam search. 'teaching-only' uses the declared "
                "package-scheduled mentorship: juniors re-request lessons from earlier-cohort neighbours at a bounded interval, teachers skip workflows "
                "already offered to that learner and never start a lesson that cannot finish before their scheduled retirement; dependencies are taught "
                "inside the lesson at separately charged work. Retirement is never delayed.")

    def parity(self, worlds: list[JSON], seed: int) -> JSON:
        by = {w["condition"]: w.get("access_parity_hash") for w in worlds if w["seed"] == seed}
        return {"seed": seed, "library_and_none_identical_at_first_arrival": by.get("library") is not None and by.get("library") == by.get("none"),
                "note": "teaching-only also teaches within cohort 0, so it is not expected to match"}


class RepairedRerun:
    """Re-run stored v0.5.0 world configurations under the repaired v0.5.1 code. Retrospective and labelled as such."""
    protocol = "repaired-rerun-1"

    def run(self, source_reports: list[Path], output: str) -> JSON:
        out = Path(output)
        store = Store(out / "rerun.sqlite")
        rec = Recorder(out, "rerun.json", {"protocol": self.protocol, "label": "repaired retrospective rerun (not prospective evidence)",
                                           "versions": VERSIONS, "sources": [str(p) for p in source_reports], "worlds": [],
                                           "note": "same scenario configurations as v0.5.0; the engine and controllers include the v0.5.1 repairs"})
        for path in source_reports:
            report = json.loads(Path(path).read_text(encoding="utf-8"))
            for w in report["worlds"]:
                config = Scenario.model_validate(w["config"])
                item = run_world(store, out, f"rerun-{report['protocol']}", w["seed"], w["condition"], config, {})
                item["source_protocol"] = report["protocol"]
                rec.report["worlds"].append(item)
                rec.save()
        return rec.report
