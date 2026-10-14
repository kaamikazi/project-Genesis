"""Stored verification of resume-after-restart, duplicate-step idempotency and replay through the real API app.

Usage: python tools/verify_restart.py evidence/v0.3.0/verification/restart.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from genesis.api import create_app


def main(out: Path) -> None:
    result: dict = {"checks": []}
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "restart.sqlite"
        with TestClient(create_app(db, tmp)) as client:
            run = client.post("/api/runs", json={"seed": 42, "removal": "creators", "removal_tick": 30, "succession": "fresh"}).json()["run_id"]
            for i in range(40):
                client.post("/api/control", json={"operation": "step", "request_id": f"step-{i}"})
            client.post(f"/api/runs/{run}/checkpoint")
            before = client.get(f"/api/runs/{run}").json()
        # Server process state discarded; a new app instance opens the same database.
        with TestClient(create_app(db, tmp)) as client:
            status = client.get("/api/status").json()
            after = client.get(f"/api/runs/{run}").json()
            result["checks"].append({"check": "resume selects the same run", "passed": status["run_id"] == run})
            result["checks"].append({"check": "same committed tick and state hash after restart",
                                     "passed": (after["state"]["tick"], after["hash"]) == (before["state"]["tick"], before["hash"]),
                                     "tick": after["state"]["tick"], "hash": after["hash"]})
            first = client.post("/api/control", json={"operation": "step", "request_id": "dup-1"})
            second = client.post("/api/control", json={"operation": "step", "request_id": "dup-1"})
            tick = client.get(f"/api/runs/{run}").json()["state"]["tick"]
            result["checks"].append({"check": "duplicate step request advances once", "passed": first.status_code == second.status_code == 200 and tick == 41, "tick": tick})
            replay = client.get(f"/api/runs/{run}?tick=40").json()
            result["checks"].append({"check": "replay of tick 40 reproduces the pre-restart hash", "passed": replay["hash"] == before["hash"]})
            state = replay["state"]
            result["checks"].append({"check": "replayed state contains lifecycle, storage and successor records",
                                     "passed": bool(state["lifecycle"]["successions"]) and any(a["status"] == "retired" for a in state["agents"].values())
                                     and any(any(s["flows"]["retirement"].values()) for s in state["settlements"].values())})
            submitted = {"request_id": "manual-1", "action": {"id": "manual-wait", "agent": "a01", "tick": 41, "kind": "wait", "params": {}}}
            a = client.post(f"/api/runs/{run}/actions", json=submitted).json()
            b = client.post(f"/api/runs/{run}/actions", json=submitted).json()
            result["checks"].append({"check": "idempotent action submission", "passed": a == b})
    result["all_passed"] = all(c["passed"] for c in result["checks"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
