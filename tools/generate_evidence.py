"""Regenerate every v0.3.0 evidence artifact with fixed, predeclared settings. Each step's command, exit status,
and duration is recorded in evidence/v0.3.0/runs.json; a failed step is recorded, not hidden.

Usage (repo root): python tools/generate_evidence.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = "evidence/v0.3.0"
PY = sys.executable
STEPS = [
    ("search-space enumeration", [PY, "tools/enumerate_space.py", f"{OUT}/invention/search-space.json"]),
    ("restart and idempotency verification", [PY, "tools/verify_restart.py", f"{OUT}/verification/restart.json"]),
    ("inheritance experiment, 8 agents", [PY, "-m", "genesis.cli", "inherit", "--seeds", "11", "42", "77", "--checkpoint", "60",
                                          "--window", "40", "--live-window", "100", "--out", f"{OUT}/inheritance"]),
    ("inheritance experiment, 20 agents", [PY, "-m", "genesis.cli", "inherit", "--seeds", "11", "42", "77", "--checkpoint", "60",
                                           "--window", "40", "--live-window", "100", "--population", "20", "--ore-per-site", "960",
                                           "--out", f"{OUT}/twenty/inheritance"]),
    ("descriptive paired comparison", [PY, "-m", "genesis.cli", "compare", "--seeds", "11", "42", "77", "--ticks", "160", "--out", f"{OUT}/comparison"]),
    ("demo world with succession, 8 agents", [PY, "-m", "genesis.cli", "--db", f"{OUT}/demo/demo.sqlite", "demo", "--seed", "42", "--ticks", "120",
                                              "--removal", "creators", "--removal-tick", "60", "--succession", "fresh", "--out", f"{OUT}/demo/offline-demo.json"]),
    ("profile before optimisation (full-copy reference)", [PY, "-m", "genesis.profiling", f"{OUT}/benchmark/profile-before-optimization.json", "100", "3", "full"]),
    ("profile after optimisation (scoped copy)", [PY, "-m", "genesis.profiling", f"{OUT}/benchmark/profile-after-optimization.json", "100", "3", "scoped"]),
    ("benchmark, 8 agents", [PY, "-m", "genesis.cli", "--db", f"{OUT}/benchmark/bench8.sqlite", "benchmark", "--ticks", "200", "--population", "8",
                             "--out", f"{OUT}/benchmark/benchmark-8.json"]),
    ("benchmark, 20 agents", [PY, "-m", "genesis.cli", "--db", f"{OUT}/benchmark/bench20.sqlite", "benchmark", "--ticks", "200", "--population", "20",
                              "--out", f"{OUT}/benchmark/benchmark-20.json"]),
]


def main() -> None:
    os.chdir(ROOT)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    only = set(sys.argv[1:])
    log_path = ROOT / OUT / "runs.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {"steps": []}
    for name, command in STEPS:
        if only and name not in only:
            continue
        start = time.perf_counter()
        proc = subprocess.run(command, env=env, capture_output=True, text=True)
        entry = {"step": name, "command": " ".join(c if c != PY else "python" for c in command), "exit_code": proc.returncode,
                 "seconds": round(time.perf_counter() - start, 1), "stderr_tail": proc.stderr[-1500:] if proc.returncode else ""}
        log["steps"] = [s for s in log["steps"] if s["step"] != name] + [entry]
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
        print(f'{name}: exit {proc.returncode} in {entry["seconds"]}s', flush=True)


if __name__ == "__main__":
    main()
