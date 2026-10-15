"""M5c (v0.5.2) protocols on a world manifest of paired blocks.

Primary (admission policy, preserved knowledge): first-improvement and repaired beam, each with fixed admission cases
and with cohort-specific admission panels. Secondary (allocation ablations, fixed admission, preserved): repaired beam,
the full beam-alloc bundle, and the bundle without each of three guards. The secondary study SHARES the primary's
beam/fixed worlds as its control (identical frozen configuration); they are not re-run.

Every condition uses final_selection "selection-panel": the final champion is chosen from a bounded eligible set on one
shared selection panel, so champions are comparable across admission policies. Sealed-4 scoring runs after closure.
"""
from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

from .experiments import VERSIONS, Recorder
from .models import JSON, Scenario, digest
from .reducer import Window, reduce_export
from .storage import Store

BASE: JSON = {"population": 8, "task": "workshop-1", "lifecycle": "cohorts", "cohort_ticks": 60, "cohort_count": 3, "cohort_overlap": 0,
              "ore_per_site": 900, "search_budget": 48, "budget_unit": "credits", "sharing": True, "controller": "search",
              "cross_cohort_access": True, "teaching": False, "panel_queries": 12, "final_selection": "selection-panel",
              "selection_candidates": 16, "max_ticks": 180}
PRIMARY = (
    ("first-improvement/fixed", {"search_policy": "first-improvement", "validation_policy": "fixed"}),
    ("first-improvement/panels", {"search_policy": "first-improvement", "validation_policy": "cohort-panels"}),
    ("beam/fixed", {"search_policy": "beam", "validation_policy": "fixed"}),
    ("beam/panels", {"search_policy": "beam", "validation_policy": "cohort-panels"}),
)
ABLATION = (
    ("beam/fixed", {"search_policy": "beam", "validation_policy": "fixed"}),                                  # shared control
    ("beam-alloc/fixed", {"search_policy": "beam-alloc", "validation_policy": "fixed"}),
    ("beam-alloc-without-stale-frontier/fixed", {"search_policy": "beam-alloc", "alloc_disable": "stale-frontier", "validation_policy": "fixed"}),
    ("beam-alloc-without-reserve/fixed", {"search_policy": "beam-alloc", "alloc_disable": "reserve", "validation_policy": "fixed"}),
    ("beam-alloc-without-novelty/fixed", {"search_policy": "beam-alloc", "alloc_disable": "novelty", "validation_policy": "fixed"}),
)
ALL_CONDITIONS = tuple({n: c for n, c in PRIMARY + ABLATION}.items())
BUDGET: JSON = {"runtime_minutes": 150, "storage_mb": 120, "min_ore_left_fraction": 0.25,
                "conditions_per_study": {"primary": len(PRIMARY), "ablation": len(ABLATION) - 1}}


def block_scenario(block: JSON, overrides: JSON) -> Scenario:
    return Scenario(**{**BASE, "seed": block["label_seed"], "seed_scheme": "streams-1", "hidden_combo": block["hidden_combo"],
                       "terrain_seed": block["terrain_seed"], "controller_seed": block["controller_seed"], **overrides})


def world_summary(export: JSON, red: JSON) -> JSON:
    st = export["state"]
    final = st["lifecycle"]["freezes"][-1]
    pick = final.get("selection_panel_best")
    researchers = [a for a in st["agents"].values() if a["role"] == "researcher"]
    queries = [n for a in researchers for n in (a.get("panel_queries") or {}).values()]
    ore0 = export["initial"]["initial_totals"]["ore"]
    ore_sites = sum(s["stock"] for s in st["sites"].values() if s["resource"] == "ore")
    m = red["metrics"]
    return {"final_pick": pick, "selection_accounting": final.get("selection_accounting"),
            "freezes": [{k: f.get(k) for k in ("tick", "cohort", "reason", "selection_panel_best", "selection_accounting", "held_best", "created_upto_best")} for f in st["lifecycle"]["freezes"]],
            "submissions": m["search.submissions"], "improvement_admissions": m["admission.improvement_admissions"], "refactor_admissions": m["admission.refactor_admissions"],
            "failed_admissions": m["search.submissions"] - m["admission.improvement_admissions"] - m["admission.refactor_admissions"],
            "panel_queries_per_researcher_panel": queries, "panel_query_cap": st["config"]["panel_queries"] if st["config"]["validation_policy"] == "cohort-panels" else None,
            "panel_cap_hits": sum(1 for q in queries if q >= st["config"]["panel_queries"]) if st["config"]["validation_policy"] == "cohort-panels" else None,
            "ore_left_fraction": round(ore_sites / ore0, 4) if ore0 else None,
            "metrics": m, "production_energy_per_alloy": red["overall"]["production_energy_per_alloy"]["value"],
            "produced_alloy": red["overall"]["produced_alloy"]}


def run_world(store: Store, out: Path, file: str, block: JSON, condition: str, config: Scenario, keep_export: bool) -> JSON:
    item: JSON = {"block": block["block"], "seed": int(block["block"][1:]), "condition": condition, "hidden_combo": block["hidden_combo"],
                  "config": config.model_dump(), "config_hash": digest(config.model_dump()), "status": "started"}
    start = time.perf_counter()
    try:
        rid = store.create(config)
        for _ in range(config.max_ticks):
            store.step(rid)
        final = store.load(rid)
        if digest(final) != digest(store.replay(rid, final["tick"])):
            raise ValueError("replay mismatch")
        export = store.export(rid)
        red = reduce_export(export, [Window(k * config.cohort_ticks, (k + 1) * config.cohort_ticks, f"cohort-{k}") for k in range(config.cohort_count)])
        if not red["reconciliation"]["holdings_match_final_state"] or not red["reconciliation"]["statuses_match_final_state"]:
            raise ValueError(f'reducer reconciliation failed: {red["reconciliation"]}')
        item["summary"] = world_summary(export, red)
        item["initial_physical_hash"] = digest({k: export["initial"][k] for k in ("terrain", "sites", "settlements", "agents", "initial_totals")})
        stored = 0
        tag = condition.replace("/", "-")
        if keep_export:
            raw = json.dumps(export, separators=(",", ":")).encode("utf-8")
            (out / f"{block['block']}-{tag}.json.gz").write_bytes(gzip.compress(raw, 9))
            (out / f"{block['block']}-{tag}.reducer.json.gz").write_bytes(gzip.compress(json.dumps(red, separators=(",", ":")).encode("utf-8"), 9))
            stored = (out / f"{block['block']}-{tag}.json.gz").stat().st_size + (out / f"{block['block']}-{tag}.reducer.json.gz").stat().st_size
            item["export"] = {"file": f"{block['block']}-{tag}.json.gz", "reducer": f"{block['block']}-{tag}.reducer.json.gz"}
        else:
            stored = len(gzip.compress(json.dumps(export, separators=(",", ":")).encode("utf-8"), 6))   # size estimate only
        item.update(status="completed", wall_seconds=round(time.perf_counter() - start, 2), stored_bytes=stored)
    except Exception as exc:  # noqa: BLE001 -- recorded, never hidden
        item.update(status="failed", failure=f"{type(exc).__name__}: {exc}", wall_seconds=round(time.perf_counter() - start, 2))
    return item


def run_study(protocol: str, blocks: list[JSON], conditions: tuple, output: str, label: str, keep_exports: bool = True,
              shared: dict | None = None) -> JSON:
    """`shared` maps a condition name to an existing report whose identical-config worlds are reused (recorded, not re-run)."""
    out = Path(output)
    store = Store(out / f"{protocol}.sqlite")
    rec = Recorder(out, f"{protocol}.json", {"protocol": protocol, "label": label, "versions": VERSIONS, "base": BASE,
                                             "conditions": {n: c for n, c in conditions}, "blocks": [b["block"] for b in blocks], "worlds": [],
                                             "shared_controls": {k: str(v["path"]) for k, v in (shared or {}).items()}})
    for block in blocks:
        for name, overrides in conditions:
            config = block_scenario(block, overrides)
            if shared and name in shared:
                src = next((w for w in shared[name]["report"]["worlds"] if w["block"] == block["block"] and w["condition"] == name), None)
                if src is not None and src.get("config_hash") == digest(config.model_dump()):
                    rec.report["worlds"].append({**src, "shared_from": str(shared[name]["path"])})
                    rec.save()
                    continue
            rec.report["worlds"].append(run_world(store, out, protocol, block, name, config, keep_exports))
            rec.save()
        rows = [w for w in rec.report["worlds"] if w["block"] == block["block"] and w.get("initial_physical_hash")]
        rec.report.setdefault("parity", []).append({"block": block["block"], "matched_initial_physical_state": len({w["initial_physical_hash"] for w in rows}) == 1})
        rec.save()
    return rec.report
