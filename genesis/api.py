from __future__ import annotations

import os
import json
import threading
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

    def clock(self):
        due = time.monotonic()
        while not self.stop.wait(.03):
            with self.lock:
                if not self.running:
                    due = time.monotonic()
                    continue
                if time.monotonic() < due:
                    continue
                try:
                    state = self.store.step(self.run_id)
                    if state["tick"] >= state["config"]["max_ticks"]:
                        self.running = False
                except Exception as exc:
                    self.error = str(exc)
                    self.running = False
                due = time.monotonic() + 1/self.speed

    def status(self):
        return {"run_id": self.run_id, "running": self.running, "speed": self.speed, "error": self.error,
                "controller": "offline / no model calls", "clock_owner": "server", "engine": ENGINE_VERSION}


def create_app(db_path: str | Path | None = None, evidence_dir: str | Path | None = None) -> FastAPI:
    store = Store(db_path or os.getenv("GENESIS_DB", "data/genesis.sqlite"))
    evidence = Path(evidence_dir or os.getenv("GENESIS_EVIDENCE", Path(__file__).resolve().parent.parent / "evidence" / "v0.3.0"))
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

    @app.get("/api/experiments")
    def experiments():
        def load(name: str):
            path = evidence / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        report, inheritance = load("comparison/comparison.json"), load("inheritance/inheritance.json")
        return {"available": report is not None, "report": report, "inheritance": inheritance,
                "inheritance_twenty": load("twenty/inheritance/inheritance.json"), "evidence_dir": evidence.name}

    @app.post("/api/runs")
    def create(config: Scenario):
        with service.lock:
            service.running = False
            service.run_id = store.create(config)
            service.error = None
            return service.status()

    @app.get("/api/runs/{run_id}")
    def state(run_id: str, tick: int | None = Query(default=None, ge=0)):
        with service.lock:
            w = store.load(run_id) if tick is None else store.replay(run_id, tick)
            return {"state": w, "hash": digest(w), "metrics": metrics(w), "status": service.status(),
                    "events": store.events(run_id, through=w["tick"]), "checkpoints": store.checkpoints(run_id),
                    "telemetry": store.telemetry(run_id)}

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
