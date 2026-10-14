from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

JSON = dict[str, Any]
RESOURCES = ("food", "ore", "alloy")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def keyed(seed: int, stream: str, *keys: Any) -> int:
    return int(digest([seed, stream, *keys])[:16], 16)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    width: int = Field(default=24, ge=16, le=64)
    height: int = Field(default=16, ge=12, le=48)
    population: int = Field(default=8, ge=4, le=20)
    sharing: bool = True
    controller: Literal["search", "baseline"] = "search"
    max_ticks: int = Field(default=300, ge=1, le=10000)
    snapshot_every: int = Field(default=20, ge=1, le=1000)
    search_budget: int = Field(default=16, ge=0, le=16)
    # Scenario-scheduled lifecycle removal (not death): "creators" retires verified-artifact creators;
    # "matched" retires the same number of non-creators from the same settlements as a control.
    removal: Literal["none", "creators", "matched"] = "none"
    removal_tick: int = Field(default=80, ge=1, le=10000)
    # Succession: each retiree is replaced at the same boundary by a fresh agent with a new identity.
    succession: Literal["none", "fresh"] = "none"
    successor_role: Literal["producer", "researcher"] = "producer"
    # Inheritance policy for successors: settlement library access, none, or a labelled direct-transfer control.
    successor_access: Literal["library", "none", "direct"] = "library"
    # "frozen" rejects every new proposal; used to keep fresh invention identical in diagnostic windows.
    invention: Literal["open", "frozen"] = "open"
    # Controller randomness is independent of the world seed and never placed in observations.
    controller_seed: int = Field(default=7, ge=0, le=2**31 - 1)
    # Declared resource scale: ore placed on each of the four ore sites at world creation (never replenished).
    ore_per_site: int = Field(default=240, ge=0, le=5000)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=100)
    agent: str = Field(min_length=1, max_length=40)
    tick: int = Field(ge=0)
    version: Literal[1] = 1
    kind: Literal["wait", "move", "gather", "consume", "transfer", "offer_trade", "accept_trade", "send_message", "inspect_artifact", "propose_artifact", "test_artifact", "use_artifact", "produce", "deposit", "withdraw"]
    params: JSON = Field(default_factory=dict)


class AgentController(Protocol):
    def propose(self, observation: JSON) -> Action: ...


class ObservationBuilder(Protocol):
    def build(self, state: JSON, agent_id: str) -> JSON: ...


class MemoryStore(Protocol):
    def retrieve(self, state: JSON, agent_id: str, limit: int = 8) -> list[JSON]: ...


class WorldRules(Protocol):
    def apply(self, state: JSON, action: Action) -> JSON: ...


class ArtifactEvaluator(Protocol):
    def evaluate(self, program: JSON) -> JSON: ...


class EventStore(Protocol):
    def load(self, run_id: str) -> JSON: ...
    def step(self, run_id: str, overrides: dict[str, Action] | None = None) -> JSON: ...


class BudgetManager(Protocol):
    def available(self, agent: JSON, limit: int) -> bool: ...


class ExperimentRunner(Protocol):
    def run(self, seeds: list[int], ticks: int, output: str) -> JSON: ...
