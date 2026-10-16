from __future__ import annotations

import os
import json
import threading
from collections import deque
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, ConfigDict, Field

from . import ENGINE_VERSION
from .experiments import metrics
from .models import Action, Scenario, digest
from .storage import Store


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: Literal["run", "pause", "step", "speed", "select"]
    speed: int = Field(default=2, ge=1, le=10)
    request_id: str = Field(default="", max_length=100)
    run_id: str | None = None


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=100)
    action: Action


class ModelRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    config: Scenario
    agents: list[str] | None = Field(default=None, max_length=4)


class ModelPause(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    paused: bool


class ModelResolve(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision_id: str = Field(min_length=8, max_length=80)
    note: str = Field(default="acknowledged", max_length=120)


class Fork(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tick: int = Field(ge=0)
    intervention: dict | None = None
    label: str | None = Field(default=None, max_length=80)


class SimulationService:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.RLock()
        # Resume the newest run this engine can continue; older-version runs stay browsable in the archive.
        current = [r for r in store.list_runs() if r["compatible"]]
        self.run_id = current[0]["id"] if current else store.create(Scenario())
        self.running = False
        self.speed = 2
        self.error: str | None = None
        self.stop = threading.Event()
        self.recent: deque = deque(maxlen=20)        # commit times of the last ticks while running
        self.last_step_ms: float | None = None
        self.lag_seconds = 0.0
        self.active_agents: int | None = None
        self.base_population: int | None = None
        self.peak_active = 0

    def clock(self):
        """Fixed-rate pacing (v0.5.1): ticks are due every 1/speed seconds from the previous due time, not from the end
        of the previous step, so a fast engine reaches the target. A slow engine falls behind; lag is reported and
        catch-up is capped at one second so the clock never bursts. Pacing never changes what a tick computes."""
        due = time.monotonic()
        while not self.stop.wait(.005):
            with self.lock:
                now = time.monotonic()
                if not self.running:
                    due = now
                    self.recent.clear()
                    continue
                if now < due:
                    continue
                try:
                    started = time.monotonic()
                    state = self.store.step(self.run_id)
                    finished = time.monotonic()
                    self.last_step_ms = round((finished - started) * 1000, 1)
                    self.recent.append(finished)
                    self.active_agents = sum(a["status"] == "active" for a in state["agents"].values())
                    self.base_population = state["config"]["population"]
                    self.peak_active = max(self.peak_active, self.active_agents)
                    if state["tick"] >= state["config"]["max_ticks"]:
                        self.running = False
                except Exception as exc:
                    self.error = str(exc)
                    self.running = False
                due += 1 / self.speed
                self.lag_seconds = max(0.0, time.monotonic() - due)
                if self.lag_seconds > 1.0:
                    due = time.monotonic()         # cap catch-up: report the lag instead of bursting

    def achieved(self) -> float | None:
        if not self.running or len(self.recent) < 3:
            return None
        span = self.recent[-1] - self.recent[0]
        return round((len(self.recent) - 1) / span, 2) if span > 0 else None

    def status(self):
        return {"run_id": self.run_id, "running": self.running, "speed": self.speed, "error": self.error,
                "controller": "offline by default; model inhabitants only from fixtures, mock transport or recordings; live calls disabled", "clock_owner": "server", "engine": ENGINE_VERSION,
                "target_ticks_per_second": self.speed, "achieved_ticks_per_second": self.achieved(),
                "last_step_ms": self.last_step_ms, "lag_seconds": round(self.lag_seconds, 3) if self.running else 0.0,
                "base_population": self.base_population, "active_agents": self.active_agents, "peak_active_agents_this_session": self.peak_active}


def create_app(db_path: str | Path | None = None, evidence_dir: str | Path | None = None) -> FastAPI:
    store = Store(db_path or os.getenv("GENESIS_DB", "data/genesis.sqlite"))
    evidence = Path(evidence_dir or os.getenv("GENESIS_EVIDENCE", Path(__file__).resolve().parent.parent / "evidence" / "v0.3.0"))
    milestone4 = Path(os.getenv("GENESIS_EVIDENCE_M4", evidence.parent / "v0.4.0"))
    milestone5 = Path(os.getenv("GENESIS_EVIDENCE_M5", evidence.parent / "v0.5.0"))
    milestone5b = Path(os.getenv("GENESIS_EVIDENCE_M5B", evidence.parent / "v0.5.1"))
    milestone5c = Path(os.getenv("GENESIS_EVIDENCE_M5C", evidence.parent / "v0.5.2"))
    service = SimulationService(store)

    @asynccontextmanager
    async def lifespan(app):
        worker = threading.Thread(target=service.clock, name="genesis-clock", daemon=True)
        worker.start()
        yield
        service.stop.set()
        worker.join(timeout=15)

    app = FastAPI(title="GENESIS local observatory", version=ENGINE_VERSION, lifespan=lifespan)
    app.state.service = service
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"ok": True, "engine": ENGINE_VERSION, "offline": True}

    @app.get("/api/status")
    def status():
        with service.lock:
            return service.status()

    @app.get("/api/runs")
    def runs():
        return store.list_runs()

    def load_from(folder: Path, name: str):
        path = folder / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    @app.get("/api/experiments")
    def experiments():
        def load(name: str):
            path = evidence / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        report, inheritance = load("comparison/comparison.json"), load("inheritance/inheritance.json")

        def load_m4(name: str):
            path = milestone4 / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return {"available": report is not None, "report": report, "inheritance": inheritance,
                "inheritance_twenty": load("twenty/inheritance/inheritance.json"), "evidence_dir": evidence.name,
                "teaching": load_m4("teaching/teaching.json"), "cumulative": load_m4("cumulative/cumulative.json"),
                "sealed": load_m4("cumulative/sealed-results.json"), "milestone4_dir": milestone4.name,
                "m5": {name: load_from(milestone5, path) for name, path in (
                    ("summary", "summary.json"), ("protocol", "protocol/protocol.json"), ("demonstration", "demonstration/component-chain.json"),
                    ("restart", "verification/restart.json"), ("search_cpu", "benchmark/search-cpu.json"),
                    ("diagnosis", "diagnosis/search-diagnosis.json"), ("inherited", "diagnosis/inherited-improvements.json"),
                    ("patch_audit", "verification/generation-patch-audit.json"))}, "milestone5_dir": milestone5.name,
                "m5b": {name: load_from(milestone5b, path) for name, path in (
                    ("summary", "summary.json"), ("protocol", "protocol/protocol.json"), ("bugfix", "bugfix/bugfix-evidence.json"),
                    ("calibration", "calibration/calibration-decision.json"), ("speed", "benchmark/server-speed.json"),
                    ("production_v05", "production/production-v0.5.0-policy.json"), ("restart", "verification/restart.json"))},
                "m5c": {name: load_from(milestone5c, path) for name, path in (
                    ("summary", "summary.json"), ("protocol", "protocol/protocol.json"), ("manifest", "manifest/world-manifest.json"),
                    ("preflight", "manifest/preflight.json"), ("sizes", "evidence-sizes.json"), ("speed", "benchmark/server-speed.json"),
                    ("deferred", "ablation/DEFERRED.json"))}}

    @app.post("/api/runs")
    def create(config: Scenario):
        with service.lock:
            service.running = False
            service.run_id = store.create(config)
            service.error = None
            return service.status()

    @app.post("/api/model-runs")
    def create_model_run(body: ModelRunRequest):
        """Fixture-backed model inhabitants only (no provider is contacted); live runs are never created through the API."""
        from .model.profile import AdapterConfig, Ceilings, ModelProfile
        agents = body.agents or ["a01"]
        profile = ModelProfile(mode="fixture", agents=agents, endpoint_label="fixture", adapter=AdapterConfig(model="fixture-policy-1"),
                               run_budget=Ceilings(requests=400, input_tokens=4_000_000, output_tokens=200_000, controller_time_ms=600_000),
                               agent_budget=Ceilings(requests=200, input_tokens=2_000_000, output_tokens=100_000, controller_time_ms=300_000))
        with service.lock:
            service.running = False
            service.run_id = store.create(body.config, model_profile=profile)
            service.error = None
            return service.status()

    @app.get("/api/runs/{run_id}/model")
    def model_summary(run_id: str):
        from .model.observer import summary
        result = summary(store, run_id)
        if result is None:
            raise HTTPException(404, "run has no model-backed inhabitants")
        return result

    @app.get("/api/runs/{run_id}/model/calls/{decision_id}")
    def model_call(run_id: str, decision_id: str):
        from .model.observer import call_detail
        return call_detail(store, run_id, decision_id)

    @app.post("/api/runs/{run_id}/model/pause")
    def model_pause(run_id: str, body: ModelPause):
        store.set_model_paused(run_id, body.paused)
        return {"run_id": run_id, "paused": body.paused, "note": "pausing stops new model scheduling; it does not cancel anything at a provider"}

    @app.post("/api/runs/{run_id}/model/resolve")
    def model_resolve(run_id: str, body: ModelResolve):
        store.resolve_unknown(run_id, body.decision_id, body.note)
        return {"resolved": body.decision_id, "note": "the reservation remains counted as uncertain usage"}

    @app.get("/api/runs/{run_id}")
    def state(run_id: str, tick: int | None = Query(default=None, ge=0)):
        with service.lock:
            w = store.load(run_id) if tick is None else store.replay(run_id, tick)
            return {"state": w, "hash": digest(w), "metrics": metrics(w), "status": service.status(),
                    "events": store.events(run_id, through=w["tick"]), "checkpoints": store.checkpoints(run_id),
                    "diagnostics": store.diagnostics(run_id, through=w["tick"]),
                    "telemetry": store.telemetry(run_id), "model_enabled": store.model_profile(run_id) is not None}

    @app.post("/api/control")
    def control(command: Control):
        with service.lock:
            if command.operation in ("run", "step"):
                store.require_writable(service.run_id)
            if command.operation == "run":
                current = store.load(service.run_id)
                if current["tick"] >= current["config"]["max_ticks"]:
                    raise HTTPException(409, "Run has reached its tick limit. Create a fresh world.")
                service.running = True
                service.error = None
            elif command.operation == "pause":
                service.running = False
            elif command.operation == "speed":
                service.speed = command.speed
            elif command.operation == "select":
                if command.run_id is None:
                    raise HTTPException(422, "run_id required")
                store.load(command.run_id)
                service.running = False
                service.run_id = command.run_id
                service.error = None
            else:
                if service.running:
                    raise HTTPException(409, "Pause before stepping.")
                if not command.request_id:
                    raise HTTPException(422, "request_id required for step")
                store.step(service.run_id, request_id=command.request_id)
            return service.status()

    @app.post("/api/runs/{run_id}/actions")
    def submit(run_id: str, submission: Submission):
        with service.lock:
            if service.running:
                raise HTTPException(409, "Pause before submitting an action.")
            w = store.step(run_id, {submission.action.agent: submission.action}, submission.request_id)
            return {"tick": w["tick"], "hash": digest(w), "result": w["agents"][submission.action.agent]["last_result"]}

    @app.post("/api/runs/{run_id}/checkpoint")
    def checkpoint(run_id: str):
        with service.lock:
            return store.checkpoint(run_id)

    @app.post("/api/runs/{run_id}/fork")
    def fork(run_id: str, command: Fork):
        with service.lock:
            service.running = False
            service.run_id = store.fork(run_id, command.tick, command.intervention, command.label)
            service.error = None
            return service.status()

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: str):
        return JSONResponse(store.export(run_id), headers={"Content-Disposition": f'attachment; filename="genesis-{run_id}.json"'})

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="observatory")
    return app
