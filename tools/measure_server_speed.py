"""Achieved simulation speed through the real server clock (v0.5.1 fixed-rate pacing), at base and peak population.

Usage: python tools/measure_server_speed.py OUT.json [seconds_per_case]
Each case creates a run through the API, sets the target to 10 ticks/s, runs for the given wall time and samples
/api/status. Durability settings are unchanged (SQLite WAL, synchronous=FULL). Timings depend on the machine.
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from genesis.api import create_app

FEATURES = {"task": "workshop-1", "ore_per_site": 900, "teaching": True, "teaching_policy": "package-scheduled", "search_policy": "beam-alloc",
            "budget_unit": "credits", "search_budget": 48, "lifecycle": "cohorts", "cohort_count": 3, "max_ticks": 240}


def case(client: TestClient, population: int, overlap: int, seconds: float) -> dict:
    cfg = {**FEATURES, "seed": 42, "population": population, "cohort_ticks": 80, "cohort_overlap": overlap}
    run = client.post("/api/runs", json=cfg).json()["run_id"]
    rid = lambda: str(uuid.uuid4())  # noqa: E731
    client.post("/api/control", json={"operation": "speed", "speed": 10, "request_id": rid()})
    if overlap:   # advance into the overlap window first so peak population is measured
        for _ in range(80 - overlap + 2):
            client.post("/api/control", json={"operation": "step", "request_id": rid()})
    client.post("/api/control", json={"operation": "run", "request_id": rid()})
    samples = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        time.sleep(0.5)
        st = client.get("/api/status").json()
        if st.get("achieved_ticks_per_second") is not None:
            samples.append(st)
    client.post("/api/control", json={"operation": "pause", "request_id": rid()})
    achieved = [s["achieved_ticks_per_second"] for s in samples]
    return {"base_population": population, "overlap": overlap, "run_id": run, "target_ticks_per_second": 10,
            "achieved_ticks_per_second_median": round(statistics.median(achieved), 2) if achieved else None,
            "last_step_ms_median": round(statistics.median(s["last_step_ms"] for s in samples), 1) if samples else None,
            "max_lag_seconds": max((s["lag_seconds"] for s in samples), default=None),
            "active_agents_seen": sorted({s["active_agents"] for s in samples}), "samples": len(samples)}


def main(out: Path, seconds: float) -> None:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        with TestClient(create_app(Path(tmp) / "speed.sqlite", Path(tmp) / "no-evidence")) as client:
            for population, overlap in ((8, 0), (8, 40), (20, 0), (20, 40)):
                rows.append(case(client, population, overlap, seconds))
                print(rows[-1])
    result = {"platform": platform.platform(), "python": platform.python_version(), "pacing": "fixed-rate (v0.5.1); catch-up capped at 1 s",
              "durability": "SQLite WAL, synchronous=FULL (unchanged)", "cases": rows,
              "note": "the selected speed is a target; achieved is measured over the last 20 committed ticks"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 8.0)
