"""Model profile: the non-secret configuration of a run's model-backed inhabitants (stored with the run).

Credentials are never part of a profile; an endpoint URL carrying credentials or key-like query parameters is refused.
Default posture is offline: `live` mode additionally needs `live_authorized: true` in the profile AND the environment
switch GENESIS_LIVE_MODEL_CALLS=1 at dispatch time. Strict paid mode needs configured prices and a cost ceiling.
"""
from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import JSON, digest
from . import ACTION_SCHEMA_VERSION, ADAPTER_VERSION, PARSER_VERSION, PROMPT_VERSION


class Ceilings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requests: int = Field(ge=0, le=100000)
    input_tokens: int = Field(ge=0, le=10**9)
    output_tokens: int = Field(ge=0, le=10**9)
    controller_time_ms: int = Field(ge=0, le=10**9)
    cost_micros: int | None = Field(default=None, ge=0)     # integer micro-units of `pricing.currency`


class Pricing(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    currency: str = Field(min_length=3, max_length=3)
    version: str = Field(min_length=1, max_length=80)
    input_micros_per_mtok: int = Field(ge=0)                 # integer micro-units per million input tokens
    output_micros_per_mtok: int = Field(ge=0)


class AdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    base_url: str = "http://127.0.0.1:11434"
    model: str = Field(min_length=1, max_length=120)
    structured_outputs: bool = True
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=200, ge=16, le=4096)
    max_input_bytes: int = Field(default=16000, ge=2000, le=200000)
    max_response_bytes: int = Field(default=8192, ge=256, le=262144)
    max_output_bytes: int = Field(default=2048, ge=128, le=65536)
    deadline_ms: int = Field(default=20000, ge=50, le=600000)
    seed: int | None = None
    keep_alive: str | None = None
    think: bool | None = None

    @model_validator(mode="after")
    def _no_credentials(self) -> "AdapterConfig":
        u = urlparse(self.base_url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("base_url must be an http(s) URL")
        if u.username or u.password or any(k.lower() in ("key", "api_key", "apikey", "token", "access_token") for k in parse_qs(u.query)):
            raise ValueError("base_url must not carry credentials")
        return self


class SchedulerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    min_interval: int = Field(default=5, ge=1, le=1000)      # at most one deliberation per agent per min_interval ticks
    max_interval: int = Field(default=20, ge=1, le=10000)    # a standing intent is refreshed at least this often
    max_calls_per_tick: int = Field(default=2, ge=1, le=64)


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["fixture", "mock-http", "recorded", "live"]
    agents: list[str] = Field(min_length=1, max_length=20)
    endpoint_label: str = Field(default="fixture", max_length=80)
    adapter: AdapterConfig
    scheduler: SchedulerConfig = SchedulerConfig()
    run_budget: Ceilings
    agent_budget: Ceilings
    concurrency: int = Field(default=1, ge=1, le=8)
    repair_limit: int = Field(default=1, ge=0, le=1)
    pricing: Pricing | None = None
    paid: bool = False
    live_authorized: bool = False
    source_run: str | None = None                            # recorded mode: the run whose ledger supplies responses
    recorded_miss: Literal["stop", "fallback"] = "stop"
    lease_grace_ms: int = Field(default=5000, ge=0, le=600000)

    @model_validator(mode="after")
    def _rules(self) -> "ModelProfile":
        if self.paid and (self.pricing is None or self.run_budget.cost_micros is None or self.agent_budget.cost_micros is None):
            raise ValueError("strict paid mode needs configured prices and cost ceilings (fail closed)")
        if self.mode == "recorded" and not self.source_run:
            raise ValueError("recorded mode needs source_run")
        if self.mode == "live" and self.adapter.base_url.startswith("http://") and urlparse(self.adapter.base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("live mode over plain http is allowed only for a loopback endpoint")
        return self


def config_hash(profile: ModelProfile) -> str:
    """Everything that determines request content (not budgets, mode, authorization or the endpoint address, so a
    recording made through one loopback port or host can be continued through another)."""
    return digest({"adapter": profile.adapter.model_dump(exclude={"base_url"}), "versions": [PROMPT_VERSION, ACTION_SCHEMA_VERSION, PARSER_VERSION, ADAPTER_VERSION],
                   "repair_limit": profile.repair_limit})


def public_view(profile: ModelProfile) -> JSON:
    """Safe for the API and exports (a profile never contains secrets, but keep the view explicit)."""
    return {**profile.model_dump(), "config_hash": config_hash(profile)}
