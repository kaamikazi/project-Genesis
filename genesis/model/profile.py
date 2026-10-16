"""Model profile: the non-secret configuration of a run's model-backed inhabitants (stored with the run).

Credentials are never part of a profile; an endpoint URL carrying credentials or key-like query parameters is refused.
Default posture is offline: `live` mode additionally needs `live_authorized: true` in the profile AND the environment
switch GENESIS_LIVE_MODEL_CALLS=1 at dispatch time. Strict paid mode needs configured prices and a cost ceiling.
A live Gemini profile is further restricted (v0.6.1): only the official API origin, free-tier operator confirmations,
a finite wall-clock run deadline, and no paid mode (see runtime.live_guard). The API key is read from GEMINI_API_KEY
by the transport at dispatch time and never enters a profile, hash, ledger, prompt or export.
"""
from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import JSON, digest
from . import ACTION_SCHEMA_VERSION, ADAPTER_VERSION, GEMINI_ADAPTER_VERSION, GEMINI_WIRE_SCHEMA_VERSION, PARSER_VERSION, PROMPT_VERSION

GEMINI_ORIGIN = "https://generativelanguage.googleapis.com"
OLLAMA_ONLY = ("keep_alive", "think")
GEMINI_ONLY = ("provider", "thinking_level", "request_logging")
NOT_REQUEST_CONTENT = ("base_url", "min_dispatch_interval_s")


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
    provider: Literal["ollama", "gemini"] = "ollama"
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
    # Gemini generateContent only (None = field not sent; the provider default applies)
    thinking_level: Literal["minimal", "low", "medium", "high"] | None = None
    request_logging: bool | None = None                      # sent as the request-level `store` field
    # local pacing between dispatches (wall clock; set from the project's actual quota; ticks are not a rate limit)
    min_dispatch_interval_s: float = Field(default=0.0, ge=0, le=3600)

    @model_validator(mode="after")
    def _provider_fields(self) -> "AdapterConfig":
        wrong = [k for k in (OLLAMA_ONLY if self.provider == "gemini" else GEMINI_ONLY[1:]) if getattr(self, k) is not None]
        if wrong:
            raise ValueError(f"fields {wrong} do not apply to provider {self.provider}")
        return self

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


class OperatorConfirmations(BaseModel):
    """Statements only the operator can make (GENESIS cannot verify them). All must be true for a live Gemini run."""
    model_config = ConfigDict(extra="forbid", strict=True)
    free_tier_billing_disabled: bool = False   # the selected Google project is on the free tier with billing disabled
    model_available: bool = False              # the exact model is listed for that project
    quota_sufficient: bool = False             # current RPM/TPM/RPD quota covers the run's request ceiling
    simulation_data_only: bool = False         # only simulated-world data will be sent
    confirmed_by: str = Field(default="", max_length=80)
    confirmed_on: str = Field(default="", max_length=10)   # YYYY-MM-DD

    def missing(self) -> list[str]:
        out = [k for k in ("free_tier_billing_disabled", "model_available", "quota_sufficient", "simulation_data_only") if not getattr(self, k)]
        return out + [k for k in ("confirmed_by", "confirmed_on") if not getattr(self, k)]


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
    run_deadline_s: int | None = Field(default=None, ge=1, le=86400)   # wall clock, from the run's first dispatch
    operator_confirmations: OperatorConfirmations | None = None

    @model_validator(mode="after")
    def _rules(self) -> "ModelProfile":
        if self.paid and (self.pricing is None or self.run_budget.cost_micros is None or self.agent_budget.cost_micros is None):
            raise ValueError("strict paid mode needs configured prices and cost ceilings (fail closed)")
        if self.mode == "recorded" and not self.source_run:
            raise ValueError("recorded mode needs source_run")
        if self.mode == "live" and self.adapter.base_url.startswith("http://") and urlparse(self.adapter.base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("live mode over plain http is allowed only for a loopback endpoint")
        if self.adapter.provider == "gemini" and self.mode == "live":
            if self.adapter.base_url.rstrip("/") != GEMINI_ORIGIN:
                raise ValueError(f"a live Gemini profile must use the official origin {GEMINI_ORIGIN}")
            if self.paid:
                raise ValueError("paid Gemini service is not enabled in this milestone (free tier only)")
        return self


def config_hash(profile: ModelProfile) -> str:
    """Everything that determines request content (not budgets, mode, authorization or the endpoint address, so a
    recording made through one loopback port or host can be continued through another)."""
    a = profile.adapter
    if a.provider == "ollama":
        # exactly the v0.6.0 hash input, so existing Ollama recordings and identities still match
        content = a.model_dump(exclude={*NOT_REQUEST_CONTENT, *GEMINI_ONLY})
        versions = [PROMPT_VERSION, ACTION_SCHEMA_VERSION, PARSER_VERSION, ADAPTER_VERSION]
    else:
        content = a.model_dump(exclude={*NOT_REQUEST_CONTENT, *OLLAMA_ONLY})
        versions = [PROMPT_VERSION, ACTION_SCHEMA_VERSION, PARSER_VERSION, GEMINI_ADAPTER_VERSION, GEMINI_WIRE_SCHEMA_VERSION]
    return digest({"adapter": content, "versions": versions, "repair_limit": profile.repair_limit})


def public_view(profile: ModelProfile) -> JSON:
    """Safe for the API and exports (a profile never contains secrets, but keep the view explicit)."""
    return {**profile.model_dump(), "config_hash": config_hash(profile)}
