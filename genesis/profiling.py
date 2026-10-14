"""Profile representative runs before optimising. Timing, cProfile breakdown and memory are separate passes."""
from __future__ import annotations

import cProfile
import gzip
import json
import platform
import pstats
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

from . import ENGINE_VERSION, EVALUATOR_VERSION, RULE_VERSION
from .models import JSON, Scenario
from .storage import Store

# Labels -> substrings matched against pstats function keys (file:line(function)).
BREAKDOWN = {
    "state_copy (copy.deepcopy)": ("copy.py", "deepcopy"),
    "observation_build": ("world.py", "build"),
    "controller_propose": ("controllers.py", "propose"),
    "rules_apply": ("engine.py", "apply"),
    "invariant_checks": ("world.py", "check_invariants"),
    "engine_advance_total": ("engine.py", "advance"),
    "decode_and_validate_state": ("storage.py", "_decode"),
    "delta_diff": ("storage.py", "changes"),
    "canonical_json": ("models.py", "canonical"),
    "sha256_digest": ("models.py", "digest"),
    "sqlite_commit_fsync": ("~", "<method '__exit__' of 'sqlite3.Connection' objects>"),
    "sqlite_execute": ("~", "<method 'execute' of 'sqlite3.Connection' objects>"),
    "json_loads": ("json", "loads"),
    "artifact_store_checks": ("storage.py", "_artifacts"),
}


def _cumulative(stats: pstats.Stats) -> dict[str, float]:
    result = {label: 0.0 for label in BREAKDOWN}
    for (filename, _, name), (_, _, _, cumtime, _) in stats.stats.items():  # type: ignore[attr-defined]
        for label, (file_part, func) in BREAKDOWN.items():
            if func == name and (file_part == "~" or filename.endswith(file_part) or (file_part == "json" and "json" in filename)):
                result[label] = max(result[label], cumtime)
    return result


OVERRIDES: JSON = {}   # extra Scenario fields for the profiled runs (e.g. workshop-1 with teaching active)


def _run(population: int, ticks: int, folder: Path, profiler: cProfile.Profile | None = None) -> tuple[Store, str, list[float]]:
    store = Store(folder / f"p{population}-{time.perf_counter_ns()}.sqlite")
    rid = store.create(Scenario(**{"seed": 42, **OVERRIDES, "population": population, "max_ticks": ticks}))
    samples = []
    for _ in range(ticks):
        start = time.perf_counter()
        if profiler:
            profiler.enable()
        store.step(rid)
        if profiler:
            profiler.disable()
        samples.append((time.perf_counter() - start) * 1000)
    return store, rid, samples


def profile(populations: list[int], ticks: int, repetitions: int) -> JSON:
    report: JSON = {"versions": {"engine": ENGINE_VERSION, "rules": RULE_VERSION, "evaluator": EVALUATOR_VERSION},
                    "environment": {"platform": platform.platform(), "processor": platform.processor(), "python": platform.python_version()},
                    "settings": {"ticks_per_run": ticks, "repetitions": repetitions, "seed": 42, "snapshot_every": 20,
                                 "sqlite": "WAL, synchronous=FULL"}, "populations": {}}
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for population in populations:
            runs = []
            for _ in range(repetitions):
                start = time.perf_counter()
                store, rid, samples = _run(population, ticks, folder)
                runs.append({"wall_seconds": time.perf_counter() - start, "median_tick_ms": statistics.median(samples),
                             "p95_tick_ms": sorted(samples)[int(len(samples) * .95) - 1], "mean_tick_ms": statistics.mean(samples)})
            profiler = cProfile.Profile()
            store, rid, samples = _run(population, ticks, folder, profiler)
            stats = pstats.Stats(profiler)
            profiled_total = sum(samples) / 1000
            breakdown = {k: {"seconds": round(v, 4), "share_of_profiled_step_time": round(v / profiled_total, 4)}
                         for k, v in _cumulative(stats).items()}
            start = time.perf_counter()
            export = store.export(rid)
            export_build = time.perf_counter() - start
            start = time.perf_counter()
            raw = json.dumps(export, separators=(",", ":")).encode()
            serialize = time.perf_counter() - start
            start = time.perf_counter()
            packed = gzip.compress(raw, 9)
            compress = time.perf_counter() - start
            start = time.perf_counter()
            for _ in range(5):
                snapshot = json.dumps(store.load(rid), separators=(",", ":"))
            snapshot_ms = (time.perf_counter() - start) / 5 * 1000
            ui = _ui_payload(store, rid)
            tracemalloc.start()
            _run(population, min(ticks, 30), folder)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            report["populations"][str(population)] = {
                "timing_runs": [{k: round(v, 3) for k, v in r.items()} for r in runs],
                "median_tick_ms_across_runs": round(statistics.median(r["median_tick_ms"] for r in runs), 2),
                "run_to_run_stdev_of_median_ms": round(statistics.stdev(r["median_tick_ms"] for r in runs), 2) if len(runs) > 1 else None,
                "ticks_per_second": round(ticks / statistics.median(r["wall_seconds"] for r in runs), 2),
                "profiled_breakdown": breakdown,
                "profiled_note": "cProfile cumulative seconds over one instrumented run; shares overlap (nested calls) and cProfile adds overhead",
                "export": {"build_seconds": round(export_build, 3), "json_serialize_seconds": round(serialize, 3), "gzip_seconds": round(compress, 3),
                           "uncompressed_bytes": len(raw), "compressed_bytes": len(packed)},
                "snapshot_serialize_ms": round(snapshot_ms, 2), "snapshot_bytes": len(snapshot),
                "ui_payload": ui,
                "memory": {"peak_traced_python_bytes": peak, "ticks": min(ticks, 30), "note": "separate tracemalloc pass, not timed"},
            }
    return report


def _ui_payload(store: Store, rid: str) -> JSON:
    from fastapi.testclient import TestClient
    from .api import create_app
    app = create_app(store.path)
    with TestClient(app) as client:
        client.get(f"/api/runs/{rid}")
        times, size = [], 0
        for _ in range(5):
            start = time.perf_counter()
            response = client.get(f"/api/runs/{rid}")
            times.append((time.perf_counter() - start) * 1000)
            size = len(response.content)
    return {"median_ms": round(statistics.median(times), 2), "bytes_uncompressed": size,
            "note": "GET /api/runs/{id} through the ASGI test client (no network); the browser polls this about once per second"}


if __name__ == "__main__":
    import sys
    from . import engine
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("evidence/v0.3.0/benchmark/profile.json")
    engine.COPY_STRATEGY = sys.argv[4] if len(sys.argv) > 4 else "scoped"
    if len(sys.argv) > 5:
        OVERRIDES.update(json.loads(sys.argv[5]))
    result = profile([8, 20], int(sys.argv[2]) if len(sys.argv) > 2 else 100, int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    result["settings"]["copy_strategy"] = engine.COPY_STRATEGY
    result["settings"]["scenario_overrides"] = OVERRIDES
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({p: {k: v for k, v in r.items() if k in ("median_tick_ms_across_runs", "ticks_per_second", "profiled_breakdown", "ui_payload")}
                      for p, r in result["populations"].items()}, indent=1))
