"""M5c world manifest and preflight (declared before any calibration or evaluation run).

Usage:
  python tools/world_manifest_m5c.py manifest OUT.json            # write the manifest (deterministic)
  python tools/world_manifest_m5c.py preflight MANIFEST.json OUT.json [CALIBRATION_REPORT ...]

Sampling design (declared):
- Target family: the 45 hidden parameterisations of workshop-1 (split 4-8 x offset 0-2 x flux_threshold 4-6), with the
  fixed v0.5.x world size, 8 agents and 3 cohorts of 60 ticks. Results apply to this finite task family only.
- Strata: the 5 values of `split`. Within a stratum, combinations are ordered by keyed(MANIFEST_SEED, "combo-order", combo).
  The draw is round-robin across strata in split order, WITHOUT replacement: the first 3 drawn are calibration blocks,
  the next 12 are evaluation blocks. Nothing about policies, inventions, admissions or scores enters the selection.
- Per block: terrain_seed = keyed(MANIFEST_SEED, "terrain", block) mod 2^31 and controller_seed = keyed(MANIFEST_SEED,
  "controller", block) mod 2^31. All conditions in a block share both; no stream is derived from a condition label.
- One controller realisation per combination: controller-by-environment variation is partly confounded with the
  combination. No nested controller replication is run (not predeclared).
"""
from __future__ import annotations

import json
import shutil
import statistics
import sys
from pathlib import Path

from genesis import workshop as ws
from genesis.models import Scenario, canonical, digest, keyed
from genesis.world import new_world

MANIFEST_SEED = 5205
MANIFEST_VERSION = "m5c-worlds-1"
CALIBRATION_BLOCKS, EVALUATION_BLOCKS = 3, 12


def draw() -> list[tuple[int, int, int]]:
    strata = {s: sorted((c for c in ws.FAMILY if c[0] == s), key=lambda c: keyed(MANIFEST_SEED, "combo-order", *c)) for s in range(4, 9)}
    order, rank = [], 0
    while len(order) < len(ws.FAMILY):
        for s in range(4, 9):
            if rank < len(strata[s]):
                order.append(strata[s][rank])
        rank += 1
    return order


def manifest() -> dict:
    order = draw()
    blocks = []
    for i, combo in enumerate(order[:CALIBRATION_BLOCKS + EVALUATION_BLOCKS]):
        role = "calibration" if i < CALIBRATION_BLOCKS else "evaluation"
        bid = f"{'c' if role == 'calibration' else 'e'}{i + 1 - (0 if role == 'calibration' else CALIBRATION_BLOCKS):02d}"
        blocks.append({"block": bid, "role": role, "label_seed": 5200 + i, "hidden_combo": list(combo),
                       "terrain_seed": keyed(MANIFEST_SEED, "terrain", bid) % 2**31, "controller_seed": keyed(MANIFEST_SEED, "controller", bid) % 2**31})
    return {"version": MANIFEST_VERSION, "manifest_seed": MANIFEST_SEED, "sampling": __doc__,
            "family": {"name": "workshop-1 hidden parameterisations", "size": len(ws.FAMILY), "dimensions": {"split": [4, 8], "offset": [0, 2], "flux_threshold": [4, 6]}},
            "partitions": {"development": "dev-24 (PARTITION_SEED)", "validation": "validation-24", "admission_panels": "panel-0..9",
                           "selection_panel": "selection-0", "final": "sealed-4 (OS-drawn at protocol freeze)"},
            "teaching_randomness": "none (teaching is deterministic given state)",
            "blocks": blocks}


def scenario(block: dict, overrides: dict, base: dict) -> Scenario:
    return Scenario(**{**base, "seed": block["label_seed"], "seed_scheme": "streams-1", "hidden_combo": block["hidden_combo"],
                       "terrain_seed": block["terrain_seed"], "controller_seed": block["controller_seed"], **overrides})


PHYSICAL_KEYS = ("terrain", "sites", "settlements", "agents", "initial_totals")


def physical_hash(state: dict) -> str:
    return digest({k: json.loads(canonical(state[k])) for k in PHYSICAL_KEYS})


def preflight(man: dict, conditions: dict, base: dict, calibration_reports: list[Path], budget: dict) -> dict:
    checks = []
    ev = [b for b in man["blocks"] if b["role"] == "evaluation"]
    cal = [b for b in man["blocks"] if b["role"] == "calibration"]
    combos = [tuple(b["hidden_combo"]) for b in ev]
    checks.append({"check": "evaluation combinations are distinct", "passed": len(set(combos)) == len(combos) >= 12, "distinct": len(set(combos))})
    checks.append({"check": "calibration and evaluation share no combination, terrain or controller seed",
                   "passed": not ({tuple(b["hidden_combo"]) for b in cal} & set(combos))
                   and not ({b["terrain_seed"] for b in cal} & {b["terrain_seed"] for b in ev}) and not ({b["controller_seed"] for b in cal} & {b["controller_seed"] for b in ev})})
    checks.append({"check": "controller seeds differ across all blocks", "passed": len({b["controller_seed"] for b in man["blocks"]}) == len(man["blocks"])})
    checks.append({"check": "terrain seeds differ across all blocks", "passed": len({b["terrain_seed"] for b in man["blocks"]}) == len(man["blocks"])})
    matched = True
    for b in man["blocks"]:
        hashes = {physical_hash(new_world(scenario(b, o, base))) for o in conditions.values()}
        params = {canonical(ws.hidden_params(scenario(b, o, base).model_dump())) for o in conditions.values()}
        matched &= len(hashes) == 1 and len(params) == 1
    checks.append({"check": "within each block every condition starts from the same physical state and hidden parameters", "passed": matched})
    terrains = {physical_hash(new_world(scenario(b, {}, base))) for b in ev}
    checks.append({"check": "physical worlds differ across evaluation blocks", "passed": len(terrains) == len(ev), "distinct_physical_worlds": len(terrains)})
    parts = [set(ws.DEV_CASES), set(ws.VALIDATION_CASES), ws.all_panel_cases(), set(ws.selection_cases())]
    disjoint = all(not (parts[i] & parts[j]) for i in range(len(parts)) for j in range(i + 1, len(parts)))
    checks.append({"check": "development, validation, admission panels and selection panel are pairwise disjoint", "passed": disjoint})
    if calibration_reports:
        worlds = [w for p in calibration_reports for w in json.loads(Path(p).read_text(encoding="utf-8"))["worlds"]]
        done = [w for w in worlds if w["status"] == "completed"]
        ore_left = [w["summary"]["ore_left_fraction"] for w in done]
        seconds = statistics.mean(w["wall_seconds"] for w in done) if done else None
        size = statistics.mean(w["stored_bytes"] for w in done) if done else None
        checks.append({"check": "calibration worlds all completed", "passed": len(done) == len(worlds), "completed": len(done), "planned": len(worlds)})
        checks.append({"check": f"resource horizon: every calibration world ends with at least {budget['min_ore_left_fraction']:.0%} of its ore", "passed": bool(ore_left) and min(ore_left) >= budget["min_ore_left_fraction"],
                       "min_ore_left_fraction": min(ore_left) if ore_left else None})
        runs = {k: len(ev) * n for k, n in budget["conditions_per_study"].items()}
        minutes = {k: round(v * seconds * 1.15 / 60, 1) for k, v in runs.items()} if seconds else {}
        megabytes = {k: round(v * size / 1e6, 1) for k, v in runs.items()} if size else {}
        free_gb = shutil.disk_usage(Path.cwd()).free / 1e9
        checks.append({"check": "primary study fits the runtime and storage budget", "passed": minutes.get("primary", 1e9) <= budget["runtime_minutes"] and megabytes.get("primary", 1e9) <= budget["storage_mb"],
                       "estimated_minutes": minutes.get("primary"), "estimated_mb": megabytes.get("primary")})
        both = minutes.get("primary", 1e9) + minutes.get("ablation", 1e9)
        both_mb = megabytes.get("primary", 1e9) + megabytes.get("ablation", 1e9)
        checks.append({"check": "ablation study also fits (otherwise it is deferred, not run)", "passed": both <= budget["runtime_minutes"] and both_mb <= budget["storage_mb"],
                       "estimated_minutes_both": round(both, 1), "estimated_mb_both": round(both_mb, 1), "informational": True})
        checks.append({"check": "disk has at least 20x the estimated evidence size free", "passed": free_gb * 1e3 >= 20 * both_mb, "free_gb": round(free_gb, 1)})
    required = [c for c in checks if not c.get("informational")]
    return {"manifest": man["version"], "checks": checks, "passed": all(c["passed"] for c in required),
            "run_ablation": all(c["passed"] for c in checks)}


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "manifest":
        out = Path(sys.argv[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest(), indent=2), encoding="utf-8")
        print(json.dumps([(b["block"], b["hidden_combo"]) for b in manifest()["blocks"]]))
    else:
        from genesis.experiments5c import ALL_CONDITIONS, BASE, BUDGET
        man = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        result = preflight(man, dict(ALL_CONDITIONS), BASE, [Path(p) for p in sys.argv[4:]], BUDGET)
        Path(sys.argv[3]).parent.mkdir(parents=True, exist_ok=True)
        Path(sys.argv[3]).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"passed": result["passed"], "run_ablation": result["run_ablation"], "failed": [c["check"] for c in result["checks"] if not c["passed"]]}, indent=1))
        if not result["passed"]:
            sys.exit(1)
