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
from .workshop import BASELINE, DEV_CASES, VALIDATION_CASES, all_panel_cases, partition, score_cases, world_params

SEALED_VERSION = "workshop-sealed-1"
SEALED_SIZE = 48


def _cases_of(manifest: JSON) -> list:
    """Recompute a manifest's case list, excluding development, validation and every earlier sealed set it names."""
    exclude = set(DEV_CASES) | set(VALIDATION_CASES)
    if manifest.get("excludes_panels"):
        exclude |= all_panel_cases()          # v0.5.1: the precommitted cohort admission panels
    for earlier in manifest.get("excludes", []):
        earlier_cases = _cases_of(earlier)
        if digest([list(c) for c in earlier_cases]) != earlier["commitment"]:
            raise ValueError(f"excluded sealed set {earlier['version']} does not match its commitment")
        exclude |= set(earlier_cases)
    return partition("sealed", manifest["size"], exclude, seed=manifest["sealed_seed"])


def create_manifest(path: Path, version: str = SEALED_VERSION, excludes: list[JSON] | None = None, exclude_panels: bool = False) -> JSON:
    """Draw a fresh sealed seed (from the OS, not from any world stream) and commit to the case list.
    `excludes` lists earlier (already used, now public) sealed manifests whose cases must not be reused."""
    seed = secrets.randbelow(2**31)
    excluded = [{k: m[k] for k in ("version", "sealed_seed", "size", "commitment", "excludes", "excludes_panels") if k in m} for m in (excludes or [])]
    manifest = {"version": version, "task": "workshop-1", "sealed_seed": seed, "size": SEALED_SIZE,
                "disjoint_from": ["dev-24", "validation-24"] + (["cohort-panels-0..9"] if exclude_panels else []) + [m["version"] for m in excluded],
                "excludes": excluded}
    if exclude_panels:
        manifest["excludes_panels"] = True
    manifest["commitment"] = digest([list(c) for c in _cases_of(manifest)])
    if not excluded:
        manifest.pop("excludes")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


class SealedEvaluator:
    def __init__(self, manifest_path: Path):
        self.manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        self.cases = _cases_of(self.manifest)
        if digest([list(c) for c in self.cases]) != self.manifest["commitment"]:
            raise ValueError("sealed cases do not match the committed hash")
        if set(self.cases) & (set(DEV_CASES) | set(VALIDATION_CASES)):
            raise ValueError("sealed cases overlap development or validation cases")
        if self.manifest.get("excludes_panels") and set(self.cases) & all_panel_cases():
            raise ValueError("sealed cases overlap the admission panels")
        for earlier in self.manifest.get("excludes", []):
            if set(self.cases) & set(_cases_of(earlier)):
                raise ValueError(f"sealed cases overlap the earlier sealed set {earlier['version']}")

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
            for key in ("cohort_best", "accessible_best", "held_best", "created_upto_best"):
                pick = f.get(key)
                if pick is None:
                    row[key] = None
                    continue
                art = artifacts[pick["artifact"]]
                if digest(art["content"]) != pick["artifact"]:
                    raise ValueError("frozen artifact hash mismatch")
                for dep in pick.get("closure") or []:      # frozen closures resolve by immutable hash
                    if dep not in artifacts or digest(artifacts[dep]["content"]) != dep:
                        raise ValueError("frozen closure component missing or hash mismatch")
                row[key] = {**pick, "sealed": self.score(seed, art["content"]["program"], components)}
            rows.append(row)
        return {"version": self.manifest["version"], "commitment": self.commitment, "world_seed": seed, "run_closed_at": state["tick"],
                "baseline_sealed": baseline, "freezes": rows,
                "independence": "artifacts were selected by validation evidence inside the run; sealed cases never influenced any run"}
