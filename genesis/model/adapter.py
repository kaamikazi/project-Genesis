"""Ollama /api/chat adapter (ollama-chat-1): the one documented wire protocol implemented in M6.

Contract checked against the official documentation (2026-10-16):
  https://docs.ollama.com/api/chat                       request: model, messages[{role, content}], stream, format
                                                          ("json" or a JSON Schema object), options{temperature,
                                                          num_predict, seed, ...}, think, keep_alive.
                                                          non-streamed response: model, created_at, message{role,
                                                          content, thinking?}, done, done_reason, total_duration,
                                                          prompt_eval_count, eval_count (and durations in ns).
  https://docs.ollama.com/capabilities/structured-outputs  format may be a JSON Schema; the docs recommend also giving
                                                          the schema in the prompt and temperature 0; Ollama's cloud
                                                          does not support structured outputs.
Declared capabilities are configuration, not assumptions: structured outputs may be switched off for endpoints that
do not support them (then format "json" is sent and the parser still enforces the schema). Ollama documents no
idempotency key and no request-status lookup, so an uncertain outcome cannot be reconciled with the provider.
The `thinking` field is never stored or used. Only the allow-listed request headers are sent; none are stored.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..models import JSON
from . import ADAPTER_VERSION
from .schema import output_schema

REQUEST_HEADER_ALLOWLIST = ("Content-Type", "Accept")


@dataclass
class AdapterResult:
    ok: bool
    content: str | None
    returned_model: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    done_reason: str | None
    error: str | None
    provider_ns: JSON


def capabilities(cfg: JSON) -> JSON:
    return {"adapter": ADAPTER_VERSION, "wire_protocol": "Ollama POST /api/chat, non-streamed (stream=false)",
            "structured_outputs": bool(cfg.get("structured_outputs", True)),
            "reports_usage": "prompt_eval_count / eval_count when present (otherwise usage is estimated, labelled)",
            "output_limit": "options.num_predict = max_output_tokens", "idempotency_key": False, "status_lookup": False,
            "streaming": False, "reasoning_fields": "discarded (message.thinking is never stored)"}


def build_request(messages: list[JSON], cfg: JSON) -> tuple[str, bytes, dict[str, str]]:
    body = {"model": cfg["model"], "messages": messages, "stream": False,
            "format": output_schema() if cfg.get("structured_outputs", True) else "json",
            "options": {"temperature": cfg.get("temperature", 0), "num_predict": cfg["max_output_tokens"]}}
    if cfg.get("seed") is not None:
        body["options"]["seed"] = cfg["seed"]
    if cfg.get("keep_alive") is not None:
        body["keep_alive"] = cfg["keep_alive"]
    if cfg.get("think") is not None:
        body["think"] = cfg["think"]
    url = cfg["base_url"].rstrip("/") + "/api/chat"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    return url, json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"), headers


def parse_response(status: int, body: bytes, max_response_bytes: int) -> AdapterResult:
    if len(body) > max_response_bytes:
        return AdapterResult(False, None, None, None, None, None, f"response body exceeds {max_response_bytes} bytes", {})
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return AdapterResult(False, None, None, None, None, None, f"HTTP {status}: body is not JSON", {})
    if status != 200 or not isinstance(data, dict):
        err = data.get("error") if isinstance(data, dict) else None
        return AdapterResult(False, None, None, None, None, None, f"HTTP {status}: {str(err)[:200] if err else 'error'}", {})
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    content = message.get("content")
    count = lambda k: data[k] if isinstance(data.get(k), int) and data[k] >= 0 else None  # noqa: E731
    ns = {k: data[k] for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration") if isinstance(data.get(k), int)}
    if not isinstance(content, str):
        return AdapterResult(False, None, data.get("model"), count("prompt_eval_count"), count("eval_count"), data.get("done_reason"),
                             "response has no message.content string", ns)
    return AdapterResult(True, content, data.get("model") if isinstance(data.get("model"), str) else None, count("prompt_eval_count"),
                         count("eval_count"), data.get("done_reason") if isinstance(data.get("done_reason"), str) else None, None, ns)
