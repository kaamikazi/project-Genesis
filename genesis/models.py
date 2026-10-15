from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    search_budget: int = Field(default=16, ge=0, le=64)
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
    # v0.4: task family, teaching sessions and cohort lifecycle. Defaults reproduce v0.3 behaviour.
    task: Literal["phase-1", "workshop-1"] = "phase-1"
    teaching: bool = False
    lifecycle: Literal["single", "cohorts"] = "single"
    cohort_ticks: int = Field(default=60, ge=5, le=10000)
    cohort_count: int = Field(default=3, ge=1, le=20)
    cross_cohort_access: bool = True
    # v0.5: search policy, shared search credits, dependency-aware lessons, mentorship overlap. Defaults reproduce v0.4.
    search_policy: Literal["first-improvement", "beam", "beam-nocomponents", "beam-alloc"] = "first-improvement"
    budget_unit: Literal["proposals", "credits"] = "proposals"
    teaching_policy: Literal["strict-prerequisites", "package", "package-scheduled"] = "strict-prerequisites"
    cohort_overlap: int = Field(default=0, ge=0, le=1000)
    # v0.5.1: admission cases. "fixed" = the shared validation-24 partition (v0.4/v0.5 behaviour); "cohort-panels" =
    # a precommitted 24-case panel per cohort, each agent limited to `panel_queries` submissions per panel.
    validation_policy: Literal["fixed", "cohort-panels"] = "fixed"
    panel_queries: int = Field(default=12, ge=1, le=1000)
    # v0.5.2 (M5c): versioned random streams. "legacy" derives hidden invention parameters, terrain and the per-tick
    # environment from `seed` (v0.1-v0.5.1 behaviour). "streams-1" takes them from separate declared sources, as a
    # world-manifest block: `hidden_combo` (one member of the finite workshop-1 family), `terrain_seed` (terrain and
    # per-tick phase/humidity), and `controller_seed` (controller randomness). Evaluation partitions stay precommitted.
    seed_scheme: Literal["legacy", "streams-1"] = "legacy"
    terrain_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    hidden_combo: list[int] | None = None
    # v0.5.2: final champion selection. "admission-score" = lowest stored admission score (earlier behaviour);
    # "selection-panel" = a bounded eligible set re-scored on one shared selection panel at each freeze.
    final_selection: Literal["admission-score", "selection-panel"] = "admission-score"
    selection_candidates: int = Field(default=16, ge=1, le=100)
    # v0.5.2 leave-one-out flag for the beam-alloc bundle (submission safety is never disabled).
    alloc_disable: Literal["none", "stale-frontier", "reserve", "novelty"] = "none"

    @model_validator(mode="after")
    def _streams(self) -> "Scenario":
        if self.seed_scheme == "streams-1":
            if self.terrain_seed is None or self.hidden_combo is None:
                raise ValueError("streams-1 needs terrain_seed and hidden_combo")
            split, offset, flux = (self.hidden_combo + [None, None, None])[:3]
            if len(self.hidden_combo) != 3 or not (4 <= split <= 8 and 0 <= offset <= 2 and 4 <= flux <= 6):
                raise ValueError("hidden_combo must be [split 4-8, offset 0-2, flux_threshold 4-6] (the workshop-1 family)")
        elif self.terrain_seed is not None or self.hidden_combo is not None:
            raise ValueError("terrain_seed and hidden_combo apply only to seed_scheme streams-1")
        return self


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=100)
    agent: str = Field(min_length=1, max_length=40)
    tick: int = Field(ge=0)
    version: Literal[1] = 1
    kind: Literal["wait", "move", "gather", "consume", "transfer", "offer_trade", "accept_trade", "send_message", "inspect_artifact", "propose_artifact", "test_artifact", "use_artifact", "produce", "deposit", "withdraw",
                  "submit_artifact", "offer_teaching", "accept_teaching", "teach_step", "learn_step", "practice_step", "abandon_session",
                  "withdraw_artifact"]
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
