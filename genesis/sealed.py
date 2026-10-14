"""Sealed final evaluation for `workshop-1`.

Isolation contract (tested in tests/test_sealed.py):
- The sealed case seed lives only in a protected manifest file outside world state, configuration and observations.
- No module on the world path imports this one (engine, world, controllers, storage, api, experiments' world runners).
- It scores only artifacts named in a freeze record (selected by validation evidence), only for closed runs, and
  writes results only to experiment reports. Nothing here feeds back into any run.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from .models import JSON, digest
from .workshop import BASELINE, DEV_CASES, VALIDATION_CASES, partition, score_cases, world_params

SEALED_VERSION = "workshop-sealed-1"
SEALED_SIZE = 48


def create_manifest(path: Path) -> JSON:
    """Draw a fresh sealed seed (from the OS, not from any world stream) and commit to the case list."""
    seed = secrets.randbelow(2**31)
    cases = partition("sealed", SEALED_SIZE, set(DEV_CASES) | set(VALIDATION_CASES), seed=seed)
    manifest = {"version": SEALED_VERSION, "task": "workshop-1", "sealed_seed": seed, "size": SEALED_SIZE,
                "disjoint_from": ["dev-24", "validation-24"], "commitment": digest([list(c) for c in cases])}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


class SealedEvaluator:
    def __init__(self, manifest_path: Path):
        self.manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        self.cases = partition("sealed", self.manifest["size"], set(DEV_CASES) | set(VALIDATION_CASES), seed=self.manifest["sealed_seed"])
        if digest([list(c) for c in self.cases]) != self.manifest["commitment"]:
            raise ValueError("sealed cases do not match the committed hash")
        if set(self.cases) & (set(DEV_CASES) | set(VALIDATION_CASES)):
            raise ValueError("sealed cases overlap development or validation cases")

    @property
    def commitment(self) -> str:
        return self.manifest["commitment"]

    def score(self, world_seed: int, program: JSON, components: dict[str, JSON]) -> JSON:
        own = score_cases(program, world_params(world_seed), self.cases, components)
        return {"score": own["score"], "cost": own["cost"], "alloy": own["alloy"],
                "infeasible_cases": sum(1 for r in own["cases"] if not r["feasible"])}

    def evaluate_closed_run(self, export: JSON) -> JSON:
        """Score every artifact named in the run's freeze records. Requires the run to be closed (at max_ticks)."""
        state = export["state"]
        if state["tick"] != state["config"]["max_ticks"]:
            raise ValueError("sealed evaluation requires a closed run (tick == max_ticks)")
        freezes = state["lifecycle"].get("freezes", [])
        if not freezes:
            raise ValueError("no freeze record: selection must precede final evaluation")
        seed = state["config"]["seed"]
        artifacts = state["artifacts"]
        components = {k: a["content"]["program"] for k, a in artifacts.items() if a.get("kind") == "component"}
        baseline = self.score(seed, BASELINE, {})
        rows = []
        for f in freezes:
            row = {"tick": f["tick"], "cohort": f["cohort"], "reason": f["reason"]}
            for key in ("cohort_best", "accessible_best"):
                pick = f.get(key)
                if pick is None:
                    row[key] = None
                    continue
                art = artifacts[pick["artifact"]]
                if digest(art["content"]) != pick["artifact"]:
                    raise ValueError("frozen artifact hash mismatch")
                row[key] = {**pick, "sealed": self.score(seed, art["content"]["program"], components)}
            rows.append(row)
        return {"version": SEALED_VERSION, "commitment": self.commitment, "world_seed": seed, "run_closed_at": state["tick"],
                "baseline_sealed": baseline, "freezes": rows,
                "independence": "artifacts were selected by validation evidence inside the run; sealed cases never influenced any run"}
