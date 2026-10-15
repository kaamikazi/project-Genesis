"""M5b (v0.5.1) evidence, in a fixed order that keeps every kind of result separate:

regression/bugfix evidence -> post-hoc corrections to v0.5.0 -> repaired retrospective rerun -> calibration (seeds
310-312) -> protocol freeze with sealed-3 commitment -> prospective allocation and mentorship experiments -> sealed-3
scoring of closed runs -> production accounting -> demonstration fixture, restart, CPU, server speed, profiles -> summaries.

Usage (repo root): python tools/generate_evidence_m5b.py [step names...]
Every step's command, exit code and duration go to evidence/v0.5.1/runs.json with the git commit, whether runtime code
was dirty (and which files), and a SHA-256 over runtime sources. A failed step is recorded, not hidden.
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
OUT = Path("evidence/v0.5.1")
PY = sys.executable
EVALUATION_SEED_POOL = list(range(221, 231))     # never run before this protocol
BASE = {"population": 8, "cohort_ticks": 60, "cohort_count": 3, "cohort_overlap": 30, "allocation_overlap": 0, "ore_per_site": 900, "search_budget": 48}
PROFILE = {"task": "workshop-1", "ore_per_site": 900, "lifecycle": "cohorts", "cohort_ticks": 50, "cohort_count": 2, "cohort_overlap": 25,
           "teaching": True, "teaching_policy": "package-scheduled", "search_policy": "beam-alloc", "budget_unit": "credits", "search_budget": 48,
           "cross_cohort_access": False}


def fingerprint(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for f in sorted(paths):
        h.update(f.relative_to(ROOT).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def source_fingerprint() -> dict:
    files = sorted([*ROOT.glob("genesis/*.py"), *ROOT.glob("tools/*.py")])
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "genesis", "tools", "frontend/src"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"git_commit": commit, "runtime_code_dirty": bool(dirty), "dirty_files": dirty.splitlines(), "source_sha256": fingerprint(files), "files": len(files),
            "controller_sha256": fingerprint([ROOT / "genesis" / "controllers.py"]), "engine_sha256": fingerprint([ROOT / "genesis" / "engine.py"])}


def rerun() -> None:
    from genesis.experiments5b import RepairedRerun
    RepairedRerun().run([ROOT / "evidence/v0.5.0/policy/policy.json", ROOT / "evidence/v0.5.0/teaching/teaching.json"], str(ROOT / OUT / "rerun"))


def rerun_sealed() -> None:
    from genesis.experiments4 import score_sealed
    from genesis.sealed import SealedEvaluator
    evaluator = SealedEvaluator(ROOT / "evidence/v0.5.0/protected/sealed-2-manifest.json")     # already known: retrospective only
    result = score_sealed(evaluator, ROOT / OUT / "rerun" / "rerun.json", ROOT / OUT / "rerun")
    result["label"] = "retrospective: sealed-2 cases were already known before this rerun"
    (ROOT / OUT / "rerun" / "sealed-2-retrospective.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def freeze_protocol() -> None:
    from genesis import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
    from genesis.experiments5b import ALLOCATION_CONDITIONS, MENTORSHIP_CONDITIONS
    from genesis.metrics_dictionary import METRICS_VERSION
    from genesis.sealed import SealedEvaluator, create_manifest
    from tools.summarize_m5b import RULE
    path = ROOT / OUT / "protocol" / "protocol.json"
    if path.exists():
        raise SystemExit("protocol already frozen; refusing to overwrite")
    decision = json.loads((ROOT / OUT / "calibration" / "calibration-decision.json").read_text(encoding="utf-8"))
    manifest_path = ROOT / OUT / "protected" / "sealed-3-manifest.json"
    if not manifest_path.exists():
        s1 = json.loads((ROOT / "evidence/v0.4.0/protected/sealed-manifest.json").read_text(encoding="utf-8"))
        s2 = json.loads((ROOT / "evidence/v0.5.0/protected/sealed-2-manifest.json").read_text(encoding="utf-8"))
        create_manifest(manifest_path, "workshop-sealed-3", [s1, s2], exclude_panels=True)
    sealed = SealedEvaluator(manifest_path)
    n = decision["sample_size"]["chosen_n"]
    schedule = decision["chosen_schedule"]
    protocol = {
        "milestone": "M5b", "release": "v0.5.1", "frozen_at": datetime.now(timezone.utc).isoformat(), "source": source_fingerprint(),
        "versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION, "sealed": sealed.manifest["version"], "metrics": METRICS_VERSION},
        "calibration_seeds": decision["seeds"], "evaluation_seeds": EVALUATION_SEED_POOL[:n], "sample_size_rule": decision["rules"],
        "allocation_settings": {**BASE, "cohort_overlap": BASE["allocation_overlap"]},
        "mentorship_settings": {**BASE, "cohort_ticks": schedule["cohort_ticks"], "cohort_overlap": schedule["overlap"]},
        "mentorship_schedule_decision": schedule,
        "sealed_commitment": sealed.commitment, "sealed_disjoint_from": sealed.manifest["disjoint_from"],
        "selection_rules": {"freeze": "lowest validation score among admitted or superseded workflows (components excluded); ties by creation tick then id",
                            "held_best": "held by the cohort's members at its freeze", "created_upto_best": "created by this or earlier cohorts by the freeze tick (creation attribution)",
                            "cohort_best": "created by this cohort"},
        "experiments": {
            "allocation": {"conditions": {k: v for k, v in ALLOCATION_CONDITIONS},
                           "primary": "final held_best sealed-3 score: beam-alloc vs beam, paired by seed, separately for preserved and reset",
                           "secondary": ["final held_best validation", "final created_upto_best sealed-3", "allocation counters (genesis-metrics-1)",
                                         "creation-attributed further improvement", "first-improvement reference contrasts"],
                           "identifies": "the bundle's combined effect, not each guard's"},
            "mentorship": {"conditions": {k: v for k, v in MENTORSHIP_CONDITIONS},
                           "primary": ["dependency lessons: eligible transitions, offered, acquired, failed, interrupted; dependencies acquired; independent post-retirement execution",
                                       "final held_best sealed-3: teaching-only vs none"],
                           "secondary": ["library vs none, library vs teaching-only", "creation-attributed further improvement"]},
            "validation_panels": "infrastructure implemented and tested; experiment deferred (not run)"},
        "missing_data": RULE["text"] + " Missing selections are never scored as zero; failed worlds are reported and excluded from pairs with the reason.",
        "stopping_and_exclusion": "all planned worlds run; no early stopping; no world excluded except as failed (recorded)",
        "no_tuning_after_freeze": "settings, policies, seeds and rules above are fixed; sealed-3 scores are computed only after every run is closed"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")


def _protocol() -> dict:
    return json.loads((ROOT / OUT / "protocol" / "protocol.json").read_text(encoding="utf-8"))


def allocation() -> None:
    from genesis.experiments5b import AllocationExperiment
    p = _protocol()
    AllocationExperiment().run(p["evaluation_seeds"], str(ROOT / OUT / "allocation"), p["allocation_settings"])


def mentorship() -> None:
    from genesis.experiments5b import MentorshipExperiment
    p = _protocol()
    MentorshipExperiment().run(p["evaluation_seeds"], str(ROOT / OUT / "mentorship"), p["mentorship_settings"])


def sealed_scoring() -> None:
    from genesis.experiments4 import score_sealed
    from genesis.sealed import SealedEvaluator
    evaluator = SealedEvaluator(ROOT / OUT / "protected" / "sealed-3-manifest.json")
    for name in ("allocation", "mentorship"):
        result = score_sealed(evaluator, ROOT / OUT / name / f"{name}.json", ROOT / OUT / name)
        (ROOT / OUT / name / "sealed-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def demonstration() -> None:
    from genesis.demo5 import component_chain, summary
    result = component_chain(101)
    path = ROOT / OUT / "demonstration" / "component-chain-v0.5.1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**result, "summary": summary(result)}, indent=2), encoding="utf-8")


def metrics_doc() -> None:
    from genesis.metrics_dictionary import as_markdown
    (ROOT / OUT / "METRICS.md").write_text(as_markdown(), encoding="utf-8")


PROD = [PY, "tools/production_accounting.py"]
STEPS = [
    ("bugfix evidence (v0.5.0 vs v0.5.1, minimal reproductions)", [PY, "tools/bugfix_evidence_m5b.py", str(OUT / "bugfix" / "bugfix-evidence.json")]),
    ("post-hoc corrections to v0.5.0 summaries", [PY, "tools/corrections_v05.py", str(OUT / "corrections-v0.5.0")]),
    ("production accounting: v0.5.0 P", PROD + ["evidence/v0.5.0/policy/policy.json", str(OUT / "production" / "production-v0.5.0-policy.json"),
                                               "first-improvement/preserved", "beam/preserved", "beam-nocomponents/preserved", "beam/preserved",
                                               "first-improvement/reset", "beam/reset"]),
    ("production accounting: v0.5.0 T", PROD + ["evidence/v0.5.0/teaching/teaching.json", str(OUT / "production" / "production-v0.5.0-teaching.json"),
                                               "none", "library", "none", "teaching-only"]),
    ("repaired retrospective rerun of v0.5.0 worlds", "rerun"),
    ("retrospective sealed-2 scoring of the rerun", "rerun_sealed"),
    ("production accounting: rerun", PROD + [str(OUT / "rerun" / "rerun.json"), str(OUT / "production" / "production-rerun.json"),
                                            "first-improvement/preserved", "beam/preserved", "none", "library", "none", "teaching-only"]),
    ("calibration (development seeds 310-312)", [PY, "tools/calibrate_m5b.py", str(OUT / "calibration"), json.dumps(BASE)]),
    ("freeze protocol and sealed-3 commitment", "freeze_protocol"),
    ("allocation experiment (prospective)", "allocation"),
    ("mentorship experiment (prospective)", "mentorship"),
    ("sealed-3 scoring of closed runs", "sealed_scoring"),
    ("production accounting: allocation", PROD + [str(OUT / "allocation" / "allocation.json"), str(OUT / "production" / "production-allocation.json"),
                                                 "beam/preserved", "beam-alloc/preserved", "beam/reset", "beam-alloc/reset", "first-improvement/preserved", "beam/preserved"]),
    ("production accounting: mentorship", PROD + [str(OUT / "mentorship" / "mentorship.json"), str(OUT / "production" / "production-mentorship.json"),
                                                 "none", "teaching-only", "none", "library"]),
    ("deterministic demonstration fixture (labelled)", "demonstration"),
    ("restart with pending submission and mentorship", [PY, "tools/verify_restart_m5b.py", str(OUT / "verification" / "restart.json")]),
    ("search CPU by policy", [PY, "tools/benchmark_search_m5.py", str(OUT / "benchmark" / "search-cpu.json"), "310", "311"]),
    ("server speed (target vs achieved)", [PY, "tools/measure_server_speed.py", str(OUT / "benchmark" / "server-speed.json"), "10"]),
    ("profile base 8/20 agents with overlap (peak doubles)", [PY, "-m", "genesis.profiling", str(OUT / "benchmark" / "profile-overlap.json"), "100", "3", "scoped",
                                                              json.dumps(PROFILE)]),
    ("metric dictionary", "metrics_doc"),
    ("summaries", [PY, "tools/summarize_m5b.py", str(OUT)]),
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
