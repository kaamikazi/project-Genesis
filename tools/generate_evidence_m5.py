"""Milestone 5 evidence, in a fixed order: calibration, protocol freeze (sealed-2 commitment), evaluation runs, sealed
scoring of closed runs, demonstration fixture, restart, search CPU, profiles, summaries.

Usage (repo root): python tools/generate_evidence_m5.py [step names...]
Every step's command, exit code and duration go to evidence/v0.5.0/runs.json with the git commit, whether runtime code
was dirty (and the dirty file list), and a SHA-256 over all runtime sources. A failed step is recorded, not hidden.
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
OUT = Path("evidence/v0.5.0")
PY = sys.executable
CALIBRATION_SEEDS = [300, 301, 302]
EVALUATION_SEEDS = [201, 202, 203, 204, 205]     # never run before this milestone's evaluation; hidden parameters differ per seed
SETTINGS = {"population": 8, "cohort_ticks": 60, "cohort_count": 3, "cohort_overlap": 30, "policy_overlap": 0, "ore_per_site": 900, "search_budget": 48}
PROFILE = {"task": "workshop-1", "ore_per_site": 900, "lifecycle": "cohorts", "cohort_ticks": 50, "cohort_count": 2, "cohort_overlap": 20,
           "teaching": True, "teaching_policy": "package", "search_policy": "beam", "budget_unit": "credits", "search_budget": 48,
           "cross_cohort_access": False}


def source_fingerprint() -> dict:
    files = sorted([*ROOT.glob("genesis/*.py"), *ROOT.glob("tools/*.py")])
    h = hashlib.sha256()
    for f in files:
        h.update(f.relative_to(ROOT).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "genesis", "tools", "frontend/src"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"git_commit": commit, "runtime_code_dirty": bool(dirty), "dirty_files": dirty.splitlines(), "source_sha256": h.hexdigest(), "files": len(files)}


def freeze_protocol() -> None:
    from genesis import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
    from genesis.experiments5 import POLICY_CONDITIONS, TEACHING_CONDITIONS
    from genesis.sealed import SealedEvaluator, create_manifest
    manifest_path = ROOT / OUT / "protected" / "sealed-2-manifest.json"
    if not manifest_path.exists():
        sealed1 = json.loads((ROOT / "evidence" / "v0.4.0" / "protected" / "sealed-manifest.json").read_text(encoding="utf-8"))
        create_manifest(manifest_path, "workshop-sealed-2", [sealed1])
    sealed = SealedEvaluator(manifest_path)
    protocol = {
        "milestone": "v0.5.0", "frozen_at": datetime.now(timezone.utc).isoformat(), "source": source_fingerprint(),
        "versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION, "sealed": sealed.manifest["version"]},
        "calibration_seeds": CALIBRATION_SEEDS, "evaluation_seeds": EVALUATION_SEEDS, "settings": SETTINGS,
        "partitions": {"development": 24, "validation": 24, "sealed": sealed.manifest["size"], "sealed_disjoint_from": sealed.manifest["disjoint_from"]},
        "sealed_commitment": sealed.commitment,
        "selection_rule": "freeze: lowest validation score among admitted or superseded workflows (components excluded); ties by creation tick then id; "
                          "cohort_best (created by the cohort), accessible_best (created by the cohort or visible earlier cohorts), held_best (held by the cohort's members)",
        "experiments": {
            "P": {"conditions": {n: c for n, c in POLICY_CONDITIONS},
                  "primary": "final-freeze held_best: validation score and sealed-2 score, beam vs first-improvement, paired by seed within each access condition",
                  "secondary": ["stop reasons", "proposals/admissions", "components admitted", "calling-workflow admissions",
                                "beam vs beam-nocomponents (language capability, preserved access)"],
                  "claim_rule": "a direction is reported as consistent only if it holds in at least 4 of 5 paired seeds; otherwise 'no consistent difference'. "
                                "No significance test is claimed with 5 seeds."},
            "T": {"conditions": {n: c for n, c in TEACHING_CONDITIONS},
                  "primary": ["cross-generation acquisitions by teaching", "dependencies taught and acquired", "final-freeze held_best sealed-2 score by condition"],
                  "further_improvement": "cohort k's own best admitted workflow strictly better (validation) than the best workflow cohort k-1's members held at their freeze",
                  "claim_rule": "same 4-of-5 rule; teaching-only vs none is the teaching contrast, library vs none the library contrast"},
            "direct_transfer_diagnostic": "not run in this milestone (optional in the specification)"},
        "no_tuning_after_freeze": "settings, policies and seeds above are fixed; sealed scores are computed only after every run is closed"}
    path = ROOT / OUT / "protocol" / "protocol.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit("protocol already frozen; refusing to overwrite")
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")


def sealed_scoring() -> None:
    from genesis.experiments4 import score_sealed
    from genesis.sealed import SealedEvaluator
    evaluator = SealedEvaluator(ROOT / OUT / "protected" / "sealed-2-manifest.json")
    for name in ("policy", "teaching"):
        folder = ROOT / OUT / name
        result = score_sealed(evaluator, folder / f"{name}.json", folder)
        (folder / "sealed-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def demonstration() -> None:
    from genesis.demo5 import component_chain, summary
    result = component_chain(101)
    path = ROOT / OUT / "demonstration" / "component-chain.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**result, "summary": summary(result)}, indent=2), encoding="utf-8")


S = SETTINGS
STEPS = [
    ("calibration (development seeds only)", [PY, "tools/calibrate_m5.py", str(OUT / "calibration"), json.dumps(S)]),
    ("freeze protocol and sealed-2 commitment", "freeze_protocol"),
    ("experiment P: search policy x access", [PY, "-c", "from genesis.experiments5 import PolicyExperiment as P; import json; "
                                             f"P().run({EVALUATION_SEEDS}, r'{OUT / 'policy'}', json.loads('{json.dumps(S)}'))"]),
    ("experiment T: teaching across overlapping generations", [PY, "-c", "from genesis.experiments5 import OverlapTeachingExperiment as T; import json; "
                                                              f"T().run({EVALUATION_SEEDS}, r'{OUT / 'teaching'}', json.loads('{json.dumps(S)}'))"]),
    ("sealed-2 scoring of closed runs", "sealed_scoring"),
    ("deterministic demonstration fixture", "demonstration"),
    ("restart during mentorship and search", [PY, "tools/verify_restart_m5.py", str(OUT / "verification" / "restart.json")]),
    ("search CPU by policy", [PY, "tools/benchmark_search_m5.py", str(OUT / "benchmark" / "search-cpu.json"), "300", "301"]),
    ("profile 8/20 agents, v0.5 features active", [PY, "-m", "genesis.profiling", str(OUT / "benchmark" / "profile-v05-features.json"), "100", "3", "scoped",
                                                    json.dumps(PROFILE)]),
    ("summaries", [PY, "tools/summarize_m5.py", str(OUT)]),
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
