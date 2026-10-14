"""Stored check: interrupt the process during active teaching, reopen the database, and continue identically.

Usage: python tools/verify_restart_m4.py OUT.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from genesis.models import Scenario, digest
from genesis.storage import Store


def main(out: Path) -> None:
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "r.sqlite")
        base = store.create(Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=60))
        for _ in range(60):
            store.step(base)
        fork = store.fork(base, 60, {"removal": "creators", "removal_tick": 61, "succession": "fresh", "successor_access": "none",
                                     "teaching": True, "invention": "frozen", "max_ticks": 140}, "restart-check")
        state = None
        for _ in range(80):
            state = store.step(fork)
            if any(s["stage"] in ("instruction", "practice") for s in state["sessions"].values()):
                break
        active = [s["id"] for s in state["sessions"].values() if s["stage"] in ("instruction", "practice")]
        checks.append({"check": "a teaching session is active at the interruption point", "passed": bool(active), "tick": state["tick"], "sessions": active})
        reference = Store(Path(tmp) / "ref.sqlite")
        ref_run = reference.import_run(store.export(fork))
        del store                                            # the process's in-memory objects are discarded
        reopened = Store(Path(tmp) / "r.sqlite")
        same = digest(reopened.load(fork)) == digest(state)
        checks.append({"check": "reopened database holds the same committed state, sessions included", "passed": same})
        a, b = None, None
        for _ in range(20):
            a = reopened.step(fork)
            b = reference.step(ref_run)
        checks.append({"check": "continuation after restart matches an uninterrupted reference for 20 ticks", "passed": digest(a) == digest(b), "tick": a["tick"]})
        replay = reopened.replay(fork, state["tick"])
        checks.append({"check": "replay to the interruption tick restores the session exactly",
                       "passed": replay["sessions"] == state["sessions"] and digest(replay) == digest(state)})
    result = {"checks": checks, "all_passed": all(c["passed"] for c in checks)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
