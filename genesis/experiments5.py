"""Milestone 5 protocols: search policy under matched budgets (P) and teaching across overlapping generations (T).

World runs never touch the sealed evaluator; sealed scoring runs afterwards on closed exports only
(`experiments4.score_sealed`, with the sealed-2 manifest).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .experiments import VERSIONS, Recorder, write_gz
from .models import JSON, Scenario, canonical, digest
from .reducer import Window, reduce_export
from .storage import Store

# Primary comparison: search policy x cross-cohort access. Separate language-capability comparison: beam with vs
# without component operators, both preserved. All conditions share one per-lifetime search-credit pool.
POLICY_CONDITIONS = (
    ("first-improvement/preserved", {"search_policy": "first-improvement", "cross_cohort_access": True}),
    ("first-improvement/reset", {"search_policy": "first-improvement", "cross_cohort_access": False}),
    ("beam/preserved", {"search_policy": "beam", "cross_cohort_access": True}),
    ("beam/reset", {"search_policy": "beam", "cross_cohort_access": False}),
    ("beam-nocomponents/preserved", {"search_policy": "beam-nocomponents", "cross_cohort_access": True}),
)
# Secondary: knowledge transfer route across overlapping generations (beam search, dependency-aware lessons).
TEACHING_CONDITIONS = (
    ("library", {"cross_cohort_access": True, "teaching": False}),
    ("teaching-only", {"cross_cohort_access": False, "teaching": True}),
    ("none", {"cross_cohort_access": False, "teaching": False}),
)


def _parity_hash(state: JSON, mask: tuple[str, ...]) -> str:
    """Physical state with the condition's declared differences masked (config keys and policy text)."""
    masked = json.loads(canonical(state))
    for key in mask:
        masked["config"].pop(key, None)
    for agent in masked["agents"].values():
        if agent.get("inheritance"):
            agent["inheritance"].pop("policy", None)
    return digest(masked)


def _summary(final: JSON, red: JSON, cohort_ticks: int, cohort_count: int) -> JSON:
    per_cohort = []
    for k in range(cohort_count):
        w = red["windows"][f"cohort-{k}"]
        mine = [x for x in red["lineage"] if x["cohort"] == k]
        per_cohort.append({
            "cohort": k, "proposals": len(mine), "admitted": sum(bool(x["admitted"]) for x in mine),
            "improvement_admissions": sum(1 for x in mine if x.get("admission_path") == "improvement"),
            "refactor_admissions": sum(1 for x in mine if x.get("admission_path") == "refactor"),
            "components_proposed": sum(1 for x in mine if x.get("kind") == "component"),
            "components_admitted": sum(1 for x in mine if x.get("kind") == "component" and x["admitted"]),
            "cross_generation_attempts": sum(1 for x in mine if x["parent_cohort"] is not None and x["parent_cohort"] < k),
            "cross_generation_admitted": sum(1 for x in mine if x["parent_cohort"] is not None and x["parent_cohort"] < k and x["admitted"]),
            "search_energy": w["energy_by_category"].get("search", 0), "evaluation_energy": w["energy_by_category"].get("evaluation", 0),
            "teaching_energy": w["energy_by_category"].get("teaching", 0) + w["energy_by_category"].get("instruction", 0) + w["energy_by_category"].get("practice", 0),
            "produced_alloy": w["produced_alloy"], "production_energy_per_alloy": w["production_energy_per_alloy"]})
    freezes = red["freezes"]
    further = []
    score = lambda pick: pick["selection_score"] if pick else None   # noqa: E731
    for prev, cur in zip(freezes, freezes[1:]):
        before, own, held = score(prev.get("held_best")), score(cur.get("cohort_best")), cur.get("held_best")
        further.append({"cohort": cur["cohort"], "previous_cohort_held_best": before, "own_cohort_best": own, "held_best": score(held),
                        "held_best_created_by_cohort": held["cohort"] if held else None,
                        "improved_beyond_previous_held": own is not None and before is not None and own < before,
                        "definition": "own cohort's best admitted workflow vs the best workflow the previous cohort's members held at their freeze"})
    return {"freezes": freezes, "per_cohort": per_cohort, "further_improvement": further, "search": red["search"], "components": red["components"],
            "inherited": red["inherited"], "cross_generation": red["cross_generation"], "cohort_transitions": red["cohort_transitions"],
            "sessions": [{k: s[k] for k in ("teacher", "learner", "teacher_cohort", "learner_cohort", "outcome", "reason", "closure", "package",
                                             "already_known", "dependencies_acquired", "offered_tick", "ended_tick")} for s in red["sessions"]],
            "overall": {k: red["overall"][k] for k in ("produced_alloy", "production_energy", "charged_action_energy", "proposals", "submissions",
                                                       "admitted", "dev_tests", "energy_by_category", "production_energy_per_alloy")},
            "remaining": red["remaining"]}


class _CohortProtocol:
    protocol = ""
    file = ""
    conditions: tuple = ()
    mask: tuple[str, ...] = ()

    def base(self, settings: JSON) -> JSON:
        raise NotImplementedError

    def parity_tick(self, settings: JSON) -> int:
        return settings["cohort_ticks"] - settings.get("cohort_overlap", 0)

    def run(self, seeds: list[int], output: str, settings: JSON, label: str = "evaluation") -> JSON:
        out = Path(output)
        store = Store(out / f"{self.file}.sqlite")
        rec = Recorder(out, f"{self.file}.json", {
            "protocol": self.protocol, "label": label, "exploratory": True, "versions": VERSIONS, "planned_seeds": seeds, "settings": settings,
            "conditions": {n: c for n, c in self.conditions}, "design": self.design(settings),
            "selection_rule": "freeze: lowest validation score among admitted or superseded workflows (components excluded); ties by creation tick then id; "
                              "the frozen record includes the workflow's dependency closure by hash",
            "worlds": []})
        for seed in seeds:
            for name, overrides in self.conditions:
                config = Scenario(**{**self.base(settings), "seed": seed, **overrides})
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
                    item["parity_tick"] = self.parity_tick(settings)
                    item["parity_hash"] = _parity_hash(store.replay(rid, item["parity_tick"]), self.mask)
                    arrival = settings["cohort_ticks"] - config.cohort_overlap
                    item["access_parity_tick"] = arrival
                    item["access_parity_hash"] = _parity_hash(store.replay(rid, arrival), ("cross_cohort_access",))
                    export = store.export(rid)
                    ct, cc = settings["cohort_ticks"], settings["cohort_count"]
                    red = reduce_export(export, [Window(k * ct, (k + 1) * ct, f"cohort-{k}") for k in range(cc)])
                    if not red["reconciliation"]["holdings_match_final_state"] or not red["reconciliation"]["statuses_match_final_state"]:
                        raise ValueError(f'reducer reconciliation failed: {red["reconciliation"]}')
                    tag = name.replace("/", "-")
                    item.update(status="completed", wall_seconds=round(time.perf_counter() - start, 2), summary=_summary(final, red, ct, cc),
                                export=write_gz(out / f"{seed}-{self.file}-{tag}.json.gz", export))
                    (out / f"{seed}-{self.file}-{tag}.reducer.json").write_text(json.dumps(red, indent=2), encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    item.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 2))
                rec.save()
            rec.report.setdefault("parity", []).append(self.parity(rec.report["worlds"], seed))
            rec.save()
        return rec.report

    def parity(self, worlds: list[JSON], seed: int) -> JSON:
        raise NotImplementedError

    def design(self, settings: JSON) -> str:
        raise NotImplementedError


class PolicyExperiment(_CohortProtocol):
    """P: legacy first-improvement vs beam search, preserved vs reset access; plus beam without component operators."""
    protocol, file, conditions, mask = "search-policy-1", "policy", POLICY_CONDITIONS, ("cross_cohort_access", "search_policy")

    def base(self, s: JSON) -> JSON:
        return {"population": s["population"], "task": "workshop-1", "lifecycle": "cohorts", "cohort_ticks": s["cohort_ticks"],
                "cohort_count": s["cohort_count"], "cohort_overlap": s.get("policy_overlap", 0), "ore_per_site": s["ore_per_site"],
                "search_budget": s["search_budget"], "budget_unit": "credits", "sharing": True, "controller": "search", "teaching": False,
                "max_ticks": s["cohort_ticks"] * s["cohort_count"]}

    def parity_tick(self, s: JSON) -> int:
        return 0     # policies differ from the first decision; physical parity is checked on the initial state

    def design(self, s: JSON) -> str:
        return ("Cohorts from tick 0 (workshop-1, library sharing within a cohort, teaching off). Every researcher has the same per-lifetime pool of "
                f"{s['search_budget']} search credits; proposals, development tests, component tests and submissions each cost one credit. "
                "Primary comparison: first-improvement (v0.4 reference policy) vs beam, each with preserved and reset cross-cohort access. "
                "Separate language-capability comparison: beam vs beam-nocomponents, both preserved. Policies differ from the first decision, so "
                "physical parity is checked on the initial state; access parity (preserved vs reset, same policy) is checked at the first boundary.")

    def parity(self, worlds: list[JSON], seed: int) -> JSON:
        rows = [w for w in worlds if w["seed"] == seed and w.get("parity_hash")]
        by = {w["condition"]: w["access_parity_hash"] for w in rows}
        return {"seed": seed, "identical_initial_state": len({w["parity_hash"] for w in rows}) == 1 and len(rows) == len(self.conditions),
                "first-improvement_preserved_vs_reset_identical_at_first_arrival": by.get("first-improvement/preserved") is not None
                and by.get("first-improvement/preserved") == by.get("first-improvement/reset"),
                "beam_preserved_vs_reset_identical_at_first_arrival": by.get("beam/preserved") is not None and by.get("beam/preserved") == by.get("beam/reset"),
                "note": "initial physical state with search_policy and cross_cohort_access masked; access pairs compared at the first arrival"}


class OverlapTeachingExperiment(_CohortProtocol):
    """T: library vs teaching-only vs neither, with overlapping generations and dependency-aware lessons."""
    protocol, file, conditions, mask = "overlap-teaching-1", "teaching", TEACHING_CONDITIONS, ("cross_cohort_access", "teaching")

    def base(self, s: JSON) -> JSON:
        return {"population": s["population"], "task": "workshop-1", "lifecycle": "cohorts", "cohort_ticks": s["cohort_ticks"],
                "cohort_count": s["cohort_count"], "cohort_overlap": s["cohort_overlap"], "ore_per_site": s["ore_per_site"],
                "search_budget": s["search_budget"], "budget_unit": "credits", "search_policy": "beam", "teaching_policy": "package",
                "sharing": True, "controller": "search", "max_ticks": s["cohort_ticks"] * s["cohort_count"]}

    def parity_tick(self, s: JSON) -> int:
        return s["cohort_ticks"] - s["cohort_overlap"]   # the first arrival: earlier cohorts' work is complete, nothing has transferred yet

    def design(self, s: JSON) -> str:
        return (f"Cohorts of {s['cohort_ticks']} ticks; each successor cohort arrives {s['cohort_overlap']} ticks before its seniors retire "
                "(same schedule in every condition; retirement is never delayed for unfinished lessons). Beam search, same credit pool. "
                "'library': earlier cohorts' admitted artifacts visible, no teaching. 'teaching-only': library hidden across cohorts, "
                "teaching sessions on (dependency-aware lessons: missing components are taught inside the session at extra cost). "
                "'none': neither. Teaching is also available within a cohort in 'teaching-only', so its cohort-0 trajectory differs from the "
                "other two; library and none share a trajectory until the first arrival (checked).")

    def parity(self, worlds: list[JSON], seed: int) -> JSON:
        rows = {w["condition"]: w.get("parity_hash") for w in worlds if w["seed"] == seed}
        return {"seed": seed, "library_and_none_identical_at_first_arrival": rows.get("library") is not None and rows.get("library") == rows.get("none"),
                "note": "teaching-only enables within-cohort teaching from tick 0, so it is not expected to match"}
