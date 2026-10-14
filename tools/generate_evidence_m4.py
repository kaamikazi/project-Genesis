"""Milestone 4 evidence, in a fixed order that keeps calibration, protocol freeze, evaluation and sealed scoring separate.

Usage (repo root): python tools/generate_evidence_m4.py
Every step's command, exit code and duration go to evidence/v0.4.0/runs.json, with the git commit, whether runtime code was
dirty, and a SHA-256 over all runtime sources. A failed step is recorded, not hidden.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("evidence/v0.4.0")
PY = sys.executable
CALIBRATION_SEEDS = [100, 101, 103]
EVALUATION_SEEDS = [11, 42, 77, 5, 23]
SETTINGS = {"cohort_ticks": 60, "cohort_count": 3, "ore_per_site": 900, "search_budget": 16, "checkpoint": 60, "window": 60, "population": 8}


def source_fingerprint() -> dict:
    files = sorted([*ROOT.glob("genesis/*.py"), *ROOT.glob("tools/*.py")])
    h = hashlib.sha256()
    for f in files:
        h.update(f.relative_to(ROOT).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "genesis", "tools"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"git_commit": commit, "runtime_code_dirty": bool(dirty), "dirty_files": dirty.splitlines(), "source_sha256": h.hexdigest(), "files": len(files)}


def freeze_protocol() -> None:
    from genesis import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
    from genesis.experiments4 import PERFORMANCE_LEVELS
    from genesis.sealed import SealedEvaluator, create_manifest
    from genesis.workshop import OBJECTIVE, PARTITION_SEED
    manifest_path = ROOT / OUT / "protected" / "sealed-manifest.json"
    if not manifest_path.exists():
        create_manifest(manifest_path)
    sealed = SealedEvaluator(manifest_path)
    path = ROOT / OUT / "protocol" / "frozen-protocol.json"
    if path.exists():
        raise SystemExit("protocol already frozen; refusing to overwrite")
    protocol = {
        "frozen_at": datetime.now(timezone.utc).isoformat(), "source": source_fingerprint(),
        "versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION, "sealed": sealed.manifest["version"]},
        "calibration_seeds": CALIBRATION_SEEDS, "evaluation_seeds": EVALUATION_SEEDS,
        "calibration_note": "calibration seeds have hidden world parameters different from every evaluation seed; evaluation seeds were not run before this freeze",
        "settings": SETTINGS, "objective": OBJECTIVE, "partition_seed": PARTITION_SEED,
        "partitions": {"development": 24, "validation": 24, "sealed": sealed.manifest["size"]},
        "sealed_commitment": sealed.commitment,
        "selection_rule": "freeze: lowest validation score among admitted or superseded workflows; ties by creation tick then id; no sealed input",
        "admission_rule": "original: validation score >= 5% below baseline; revision: validation score strictly below parent's on the same cases",
        "performance_levels": PERFORMANCE_LEVELS,
        "experiment_A": {"protocol": "teaching-acquisition-1", "conditions": ["teaching", "library", "no-transfer", "direct-control"],
                         "checkpoint": SETTINGS["checkpoint"], "window": SETTINGS["window"],
                         "metrics": ["instruction cost by role", "ticks to acquisition", "session failures/interruptions", "ticks to use with saving",
                                     "successor and settlement production energy per alloy", "charged energy per alloy", "survival"]},
        "experiment_B": {"protocol": "cumulative-invention-1", "conditions": ["preserved", "reset"],
                         "metrics": ["frozen cohort-best and accessible-best validation scores", "sealed scores of frozen artifacts (after close)",
                                     "cross-generation revision attempts and admissions", "ticks to reach performance levels", "costs by category"]},
        "stopping_rules": "fixed run lengths; no early stopping; every attempted world is reported",
        "exclusions": "none planned; failures and ineligible seeds are reported, never dropped",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")


def sealed_scoring() -> None:
    from genesis.experiments4 import score_sealed
    from genesis.sealed import SealedEvaluator
    evaluator = SealedEvaluator(ROOT / OUT / "protected" / "sealed-manifest.json")
    result = score_sealed(evaluator, ROOT / OUT / "cumulative" / "cumulative.json", ROOT / OUT / "cumulative")
    (ROOT / OUT / "cumulative" / "sealed-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


S = SETTINGS
STEPS = [
    ("calibration (development seeds only)", [PY, "tools/calibrate_m4.py", str(OUT / "calibration"), str(S["cohort_ticks"]), str(S["ore_per_site"]),
                                              str(S["search_budget"]), str(S["checkpoint"]), str(S["window"])]),
    ("freeze protocol and sealed commitment", "freeze_protocol"),
    ("experiment A: teaching and acquisition", [PY, "-c", "import sys; from genesis.experiments4 import TeachingExperiment as T; "
                                               f"T().run({EVALUATION_SEEDS}, r'{OUT / 'teaching'}', {S['checkpoint']}, {S['window']}, {S['ore_per_site']})"]),
    ("experiment B: cumulative invention", [PY, "-c", "from genesis.experiments4 import CumulativeExperiment as C; "
                                           f"C().run({EVALUATION_SEEDS}, r'{OUT / 'cumulative'}', {S['cohort_ticks']}, {S['cohort_count']}, {S['ore_per_site']}, {S['search_budget']})"]),
    ("sealed scoring of closed runs", "sealed_scoring"),
    ("restart during active teaching", [PY, "tools/verify_restart_m4.py", str(OUT / "verification" / "restart-teaching.json")]),
    ("profile 8/20 agents, workshop-1 with teaching active", [PY, "-m", "genesis.profiling", str(OUT / "benchmark" / "profile-workshop-teaching.json"), "100", "3", "scoped",
                                                             json.dumps({"task": "workshop-1", "teaching": True, "sharing": False, "ore_per_site": 900})]),
    ("profile 8/20 agents, legacy phase-1", [PY, "-m", "genesis.profiling", str(OUT / "benchmark" / "profile-phase1.json"), "100", "3", "scoped"]),
]


def main() -> None:
    os.chdir(ROOT)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    only = set(sys.argv[1:])
    log_path = ROOT / OUT / "runs.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"steps": []}
    log["source_at_start"] = source_fingerprint()
    for name, command in STEPS:
        if only and name not in only:
            continue
        start = time.perf_counter()
        if isinstance(command, str):
            try:
                globals()[command]()
                code, err, shown = 0, "", f"(in-process) {command}()"
            except SystemExit as exc:
                code, err, shown = 1, str(exc), f"(in-process) {command}()"
            except Exception as exc:  # noqa: BLE001
                code, err, shown = 1, f"{type(exc).__name__}: {exc}", f"(in-process) {command}()"
        else:
            proc = subprocess.run(command, env=env, capture_output=True, text=True)
            code, err = proc.returncode, proc.stderr[-1500:] if proc.returncode else ""
            shown = " ".join("python" if c == PY else c for c in command)
        entry = {"step": name, "command": shown, "exit_code": code, "seconds": round(time.perf_counter() - start, 1), "stderr_tail": err,
                 "finished_at": datetime.now(timezone.utc).isoformat()}
        log["steps"] = [s for s in log["steps"] if s["step"] != name] + [entry]
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
        print(f"{name}: exit {code} in {entry['seconds']}s", flush=True)
        if code and name.startswith(("calibration", "freeze")):
            raise SystemExit("stopping: evaluation must not run without calibration and a frozen protocol")
    log["source_at_end"] = source_fingerprint()
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
