"""M5c (v0.5.2) evidence: manifest -> calibration -> preflight -> protocol freeze (sealed-4, ablation decision) -> primary
admission study -> allocation ablations (only if the declared budget allows) -> sealed-4 scoring of closed runs ->
restart, server speed, profile -> evidence sizes -> summaries.

Usage (repo root): python tools/generate_evidence_m5c.py [step names...]
Every step is logged to evidence/v0.5.2/runs.json with the git commit, runtime dirtiness and source fingerprints.
"""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("evidence/v0.5.2")
PY = sys.executable
sys.path.insert(0, str(ROOT))
from tools.generate_evidence_m5b import source_fingerprint  # noqa: E402


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return _json(ROOT / OUT / "manifest" / "world-manifest.json")


def calibration() -> None:
    from genesis.experiments5c import ALL_CONDITIONS, run_study
    blocks = [b for b in _manifest()["blocks"] if b["role"] == "calibration"]
    run_study("calibration", blocks, ALL_CONDITIONS, str(ROOT / OUT / "calibration"), "calibration (no exports stored)", keep_exports=False)


def freeze_protocol() -> None:
    from genesis import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
    from genesis.experiments5c import ABLATION, BASE, BUDGET, PRIMARY
    from genesis.metrics_dictionary import METRICS_VERSION
    from genesis.sealed import SealedEvaluator, create_manifest
    from tools.summarize_m5b import RULE
    path = ROOT / OUT / "protocol" / "protocol.json"
    if path.exists():
        raise SystemExit("protocol already frozen; refusing to overwrite")
    pre = _json(ROOT / OUT / "manifest" / "preflight.json")
    if not pre["passed"]:
        raise SystemExit("preflight failed; the protocol cannot be frozen")
    sealed_path = ROOT / OUT / "protected" / "sealed-4-manifest.json"
    if not sealed_path.exists():
        earlier = [_json(ROOT / p) for p in ("evidence/v0.4.0/protected/sealed-manifest.json", "evidence/v0.5.0/protected/sealed-2-manifest.json",
                                              "evidence/v0.5.1/protected/sealed-3-manifest.json")]
        create_manifest(sealed_path, "workshop-sealed-4", earlier, exclude_panels=True, exclude_selection=True)
    sealed = SealedEvaluator(sealed_path)
    man = _manifest()
    protocol = {
        "milestone": "M5c", "release": "v0.5.2", "frozen_at": datetime.now(timezone.utc).isoformat(), "source": source_fingerprint(),
        "versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION, "sealed": sealed.manifest["version"], "metrics": METRICS_VERSION},
        "world_manifest": {"version": man["version"], "sha256_of_blocks": __import__("genesis.models", fromlist=["digest"]).digest(man["blocks"]),
                           "evaluation_blocks": [b["block"] for b in man["blocks"] if b["role"] == "evaluation"]},
        "preflight": {k: pre[k] for k in ("passed", "run_ablation")}, "base_settings": BASE, "budget": BUDGET,
        "studies": {
            "primary": {"conditions": {n: c for n, c in PRIMARY},
                        "question": "admission-policy effect (fixed validation-24 vs cohort-specific panels) under preserved knowledge, for two fixed search policies",
                        "primary_endpoint": "sealed-4 score of the final freeze's selection_panel_best, paired by block: panels vs fixed within each policy",
                        "secondary": ["selection-panel score of the final pick", "development / admission / selection / sealed gaps", "improvement and failed admissions",
                                      "panel query utilisation and cap hits", "production energy per alloy and alloy", "policy contrast within each admission policy"],
                        "not_claimed": "preservation versus reset (no reset conditions)"},
            "ablation": {"conditions": {n: c for n, c in ABLATION}, "run": pre["run_ablation"],
                         "control": "beam/fixed worlds are SHARED with the primary study (identical frozen configuration); not re-run",
                         "contrasts": "bundle vs plain beam; each leave-one-out vs the full bundle (effect of the removed guard conditional on the other guards)"}},
        "panel_rules": {"activation": "panel k is active while lifecycle cohort k is current (boundaries every 60 ticks)",
                        "feedback": "one admitted/not-admitted bit per submission plus the agent's own query count", "cap": f"{BASE['panel_queries']} submissions per agent per panel",
                        "comparison": "child and its admission reference re-scored on the identical active panel at submission",
                        "older_artifacts": "remain admitted and usable; their stored admission scores are never compared across panels",
                        "cost": "a submission costs one credit and the usual energy in both admission policies"},
        "final_selection": "at each freeze, the newest <=16 admitted or superseded workflows held by the cohort are scored on the shared selection-0 panel "
                           "(observer-side; never shown to agents); the lowest is frozen as selection_panel_best. Same rule in every condition; evaluations are counted.",
        "missing_data": RULE["text"] + " Missing picks are never scored as zero; failed worlds are reported with reasons and excluded from pairs.",
        "exclusions_and_stopping": "all frozen blocks run; no replacement of difficult worlds; no early stopping; the study ends at its endpoint whatever the result",
        "sealed_commitment": sealed.commitment, "sealed_disjoint_from": sealed.manifest["disjoint_from"],
        "limitations_declared": ["one controller realisation per parameter combination (controller-by-environment variation partly confounded)",
                                 "12 of 45 combinations of a finite task family; no open-world generalisation",
                                 "agents, artifacts and transitions within a world are not independent replicates"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")


def primary() -> None:
    from genesis.experiments5c import PRIMARY, run_study
    blocks = [b for b in _manifest()["blocks"] if b["role"] == "evaluation"]
    run_study("primary", blocks, PRIMARY, str(ROOT / OUT / "primary"), "evaluation")


def ablation() -> None:
    from genesis.experiments5c import ABLATION, run_study
    protocol = _json(ROOT / OUT / "protocol" / "protocol.json")
    out = ROOT / OUT / "ablation"
    if not protocol["studies"]["ablation"]["run"]:
        out.mkdir(parents=True, exist_ok=True)
        (out / "DEFERRED.json").write_text(json.dumps({"status": "planned, not executed", "reason": "declared runtime/storage budget (preflight)"}, indent=2), encoding="utf-8")
        return
    blocks = [b for b in _manifest()["blocks"] if b["role"] == "evaluation"]
    primary_path = ROOT / OUT / "primary" / "primary.json"
    run_study("ablation", blocks, ABLATION, str(out), "evaluation", shared={"beam/fixed": {"path": primary_path.relative_to(ROOT), "report": _json(primary_path)}})


def sealed_scoring() -> None:
    from genesis.sealed import SealedEvaluator
    evaluator = SealedEvaluator(ROOT / OUT / "protected" / "sealed-4-manifest.json")
    for name in ("primary", "ablation"):
        path = ROOT / OUT / name / f"{name}.json"
        if not path.exists():
            continue
        report = _json(path)
        results = {"version": evaluator.manifest["version"], "commitment": evaluator.commitment, "worlds": []}
        for w in report["worlds"]:
            if w["status"] != "completed":
                results["worlds"].append({"block": w["block"], "condition": w["condition"], "status": w["status"]})
                continue
            folder = ROOT / Path(w["shared_from"]).parent if w.get("shared_from") else ROOT / OUT / name
            export = json.loads(gzip.decompress((folder / w["export"]["file"]).read_bytes()))
            results["worlds"].append({"block": w["block"], "condition": w["condition"], "status": "scored", "shared_from": w.get("shared_from"),
                                      **evaluator.evaluate_closed_run(export)})
        (ROOT / OUT / name / "sealed-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


def sizes() -> None:
    out = {}
    for d in sorted((ROOT / OUT).iterdir()):
        if d.is_dir():
            files = [f for f in d.rglob("*") if f.is_file() and ".sqlite" not in f.name]
            out[d.name] = {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}
    out["total_bytes_committed_estimate"] = sum(v["bytes"] for v in out.values() if isinstance(v, dict))
    (ROOT / OUT / "evidence-sizes.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


STEPS = [
    ("world manifest", [PY, "tools/world_manifest_m5c.py", "manifest", str(OUT / "manifest" / "world-manifest.json")]),
    ("calibration (3 calibration blocks, no exports stored)", "calibration"),
    ("preflight", [PY, "tools/world_manifest_m5c.py", "preflight", str(OUT / "manifest" / "world-manifest.json"), str(OUT / "manifest" / "preflight.json"),
                   str(OUT / "calibration" / "calibration.json")]),
    ("freeze protocol and sealed-4 commitment", "freeze_protocol"),
    ("primary study: admission policy", "primary"),
    ("secondary study: allocation ablations (or deferral record)", "ablation"),
    ("sealed-4 scoring of closed runs", "sealed_scoring"),
    ("restart and replay with streams and panels", [PY, "tools/verify_restart_m5c.py", str(OUT / "verification" / "restart.json")]),
    ("server speed (target vs achieved)", [PY, "tools/measure_server_speed.py", str(OUT / "benchmark" / "server-speed.json"), "10"]),
    ("evidence sizes", "sizes"),
    ("summaries", [PY, "tools/summarize_m5c.py", str(OUT)]),
]


def main() -> None:
    os.chdir(ROOT)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    only = set(sys.argv[1:])
    log_path = ROOT / OUT / "runs.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = _json(log_path) if log_path.exists() else {"steps": []}
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
            code, err = proc.returncode, (proc.stderr[-1500:] or proc.stdout[-800:]) if proc.returncode else ""
            shown = " ".join("python" if c == PY else c for c in command)
        entry = {"step": name, "command": shown, "exit_code": code, "seconds": round(time.perf_counter() - start, 1), "stderr_tail": err,
                 "finished_at": datetime.now(timezone.utc).isoformat()}
        log["steps"] = [s for s in log["steps"] if s["step"] != name] + [entry]
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
        print(f"{name}: exit {code} in {entry['seconds']}s", flush=True)
        if code and name in ("world manifest", "preflight", "freeze protocol and sealed-4 commitment") or (code and name.startswith("calibration")):
            raise SystemExit("stopping: evaluation must not run without a valid manifest, calibration, preflight and frozen protocol")
    log["source_at_end"] = source_fingerprint()
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
