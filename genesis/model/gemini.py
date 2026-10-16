"""Gemini Developer API adapter (gemini-generatecontent-1): one native, stateless contract.

Contract (official documentation, accessed 2026-10-17):
  https://ai.google.dev/api/generate-content
    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    request:  systemInstruction{parts[{text}]}, contents[{role:"user", parts[{text}]}], generationConfig{candidateCount,
              maxOutputTokens, temperature, seed, responseFormat{text{mimeType, schema}}, thinkingConfig{thinkingLevel,
              includeThoughts}}, store (request-level logging override)
    response: candidates[{content{parts[{text, thought?, thoughtSignature?}]}, finishReason, finishMessage, index}],
              promptFeedback{blockReason}, usageMetadata{promptTokenCount, cachedContentTokenCount, candidatesTokenCount,
              toolUsePromptTokenCount, thoughtsTokenCount, totalTokenCount}, modelVersion, responseId
    totalTokenCount is documented as prompt + tool-use prompt + thoughts + response candidates.
  https://ai.google.dev/gemini-api/docs/structured-output   supported JSON Schema subset (no maxLength)
  https://ai.google.dev/gemini-api/docs/thinking            gemini-3.5-flash-lite: thinking on by default (minimal);
                                                            levels minimal/low/medium/high; cannot be switched off
  https://ai.google.dev/gemini-api/docs/api-key             header x-goog-api-key; env GEMINI_API_KEY
  https://ai.google.dev/gemini-api/docs/rate-limits         per-project RPM/TPM/RPD; 429 RESOURCE_EXHAUSTED
  https://ai.google.dev/gemini-api/docs/pricing             free tier: free of charge, content used to improve products

Choices
- generateContent (not the Interactions API): each decision is one self-contained request; no previous-interaction id,
  no cached content, no conversation state. Field names and usage formats of the two APIs are never mixed.
- `responseFormat.text` is used for JSON output (the reference marks responseSchema/_responseJsonSchema deprecated).
- No tools, grounding, code execution, retrieval, uploads, caches or safety-setting overrides are sent.
- The API key is not handled here: the transport adds the x-goog-api-key header at dispatch time (never stored).
- Thought parts are dropped before anything is stored; only non-thought text parts are joined into the final text.
- Gemini documents no idempotency key or request-status lookup: an uncertain outcome cannot be reconciled.

The wire schema (genesis-gemini-wire-1) is a deliberately smaller description than the internal contract: the
documented subset has no `maxLength`, and per-kind parameter sets are not expressed. The strict local parser still
enforces the full genesis-action-schema-1 contract; structured output constrains format, never legality.
"""
from __future__ import annotations

import json
import math
from urllib.parse import quote

from ..models import JSON
from . import GEMINI_ADAPTER_VERSION, GEMINI_WIRE_SCHEMA_VERSION
from .adapter import AdapterResult
from .schema import KINDS, MAX_EXPLANATION

API_VERSION = "v1beta"
REQUEST_HEADER_ALLOWLIST = ("Content-Type", "Accept")      # x-goog-api-key is added by the transport, never here
USAGE_FIELDS = ("promptTokenCount", "cachedContentTokenCount", "candidatesTokenCount", "toolUsePromptTokenCount", "thoughtsTokenCount", "totalTokenCount")
TRUNCATED = {"MAX_TOKENS", "CONTINUATION"}
REFUSED = {"SAFETY", "RECITATION", "LANGUAGE", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT",
           "IMAGE_RECITATION", "PUP_LIMITED_DISABLED"}


def wire_schema() -> JSON:
    """The JSON Schema sent as responseFormat.text.schema (documented subset only)."""
    return {"type": "object", "additionalProperties": False, "required": ["kind", "params"],
            "properties": {"kind": {"type": "string", "enum": KINDS},
                           "params": {"type": "object", "description": "exactly the parameters listed for the chosen kind"},
                           "explanation": {"type": "string", "description": f"optional, at most {MAX_EXPLANATION} characters"},
                           "standing": {"type": "boolean"}}}


def capabilities(cfg: JSON) -> JSON:
    return {"adapter": GEMINI_ADAPTER_VERSION, "wire_schema": GEMINI_WIRE_SCHEMA_VERSION,
            "wire_protocol": f"Gemini Developer API POST /{API_VERSION}/models/{{model}}:generateContent (stateless, non-streamed)",
            "structured_outputs": bool(cfg.get("structured_outputs", True)),
            "schema_enforcement": "wire schema constrains format only (no maxLength, no per-kind params); the strict local parser enforces the full contract",
            "thinking": f"thinkingLevel={cfg.get('thinking_level') or 'provider default'}; thoughts never requested, returned parts flagged thought are dropped",
            "reports_usage": "usageMetadata: prompt, cached (part of prompt), candidates, thoughts, tool-use prompt, total",
            "output_limit": "generationConfig.maxOutputTokens (whether it bounds thinking tokens on generateContent is not stated in the reference; checked after each response)",
            "idempotency_key": False, "status_lookup": False, "streaming": False, "tools": False,
            "credential": "x-goog-api-key header from GEMINI_API_KEY at dispatch (transport); never stored",
            "logging_preference": "store=false sent when request_logging is false; a logging preference, not a guarantee about provider-side retention"}


def endpoint(cfg: JSON) -> str:
    return f"{cfg['base_url'].rstrip('/')}/{API_VERSION}/models/{quote(cfg['model'], safe='.-_')}:generateContent"


def build_request(messages: list[JSON], cfg: JSON) -> tuple[str, bytes, dict[str, str]]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    user = "\n\n".join(m["content"] for m in messages if m["role"] == "user")
    fmt: JSON = {"mimeType": "APPLICATION_JSON"}
    if cfg.get("structured_outputs", True):
        fmt["schema"] = wire_schema()
    gen: JSON = {"candidateCount": 1, "maxOutputTokens": cfg["max_output_tokens"], "temperature": cfg.get("temperature", 0),
                 "responseFormat": {"text": fmt}}
    if cfg.get("seed") is not None:
        gen["seed"] = cfg["seed"]
    if cfg.get("thinking_level"):
        gen["thinkingConfig"] = {"thinkingLevel": cfg["thinking_level"].upper(), "includeThoughts": False}
    body: JSON = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                  "generationConfig": gen}
    if cfg.get("request_logging") is not None:
        body["store"] = bool(cfg["request_logging"])
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    return endpoint(cfg), json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"), headers


def _count(meta: JSON, key: str) -> tuple[int | None, bool]:
    """(value, valid). Absent -> (None, True); present but not a finite non-negative integer -> (None, False)."""
    if key not in meta:
        return None, True
    v = meta[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and (not math.isfinite(v) or v != int(v))) or v < 0:
        return None, False
    return int(v), True


def normalize_usage(meta: JSON | None) -> JSON:
    """Normalized receipt. Generated tokens = candidates + thoughts (both billed as output); cached tokens are part of
    the prompt count and are reported, never added again. Basis: reported | incomplete | inconsistent | missing."""
    if not isinstance(meta, dict):
        return {"basis": "missing", "problems": ["no usageMetadata"]}
    values, problems = {}, []
    for k in USAGE_FIELDS:
        v, ok = _count(meta, k)
        values[k] = v
        if not ok:
            problems.append(f"{k} is not a finite non-negative integer")
    prompt, tool, cand, thoughts, total = (values[k] for k in ("promptTokenCount", "toolUsePromptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount"))
    out = {"input_tokens": None if prompt is None else prompt + (tool or 0), "cached_input_tokens": values["cachedContentTokenCount"],
           "candidate_tokens": cand, "thinking_tokens": thoughts, "output_tokens": None if cand is None else cand + (thoughts or 0),
           "provider_total": total}
    if prompt is None or cand is None:
        problems.append("prompt or candidate count missing")
    if values["cachedContentTokenCount"] is not None and prompt is not None and values["cachedContentTokenCount"] > prompt:
        problems.append("cached count exceeds prompt count")
    if total is not None and prompt is not None and cand is not None and total != prompt + (tool or 0) + cand + (thoughts or 0):
        problems.append("totalTokenCount differs from prompt + tool-use + thoughts + candidates")
    basis = "reported"
    if problems:
        basis = "inconsistent" if any("differs" in p or "exceeds" in p or "finite" in p for p in problems) else "incomplete"
    return {**out, "basis": basis, "problems": problems}


def parse_response(status: int, body: bytes, max_response_bytes: int) -> AdapterResult:
    """Classify one delivered HTTP response. `content` is the final action text (thoughts excluded) or None."""
    def fail(error, *, usage=None, model=None, finish=None, repairable=False, halt=None, extra=None):
        return AdapterResult(False, None, model, None, None, finish, error, {}, usage=usage or {"basis": "missing", "problems": []},
                             provider_meta=extra or {}, repairable=repairable, halt=halt)

    if len(body) > max_response_bytes:
        return fail(f"response body exceeds {max_response_bytes} bytes")
    if 300 <= status < 400:
        return fail(f"HTTP {status} redirect refused (not followed; credentials not forwarded)", extra={"http_status": status})
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return fail(f"HTTP {status}: body is not JSON")
    if status != 200 or not isinstance(data, dict):
        err = data.get("error") if isinstance(data, dict) and isinstance(data.get("error"), dict) else {}
        state = str(err.get("status") or "")[:40]
        msg = str(err.get("message") or "error")[:200]
        if status == 429 or state == "RESOURCE_EXHAUSTED":
            return fail(f"HTTP {status} {state or 'RESOURCE_EXHAUSTED'}: quota or rate limit reached; model dispatch stopped for this run (no retry)",
                        halt="quota", extra={"http_status": status, "error_status": state})
        return fail(f"HTTP {status} {state}: {msg}".strip(), extra={"http_status": status, "error_status": state})
    usage = normalize_usage(data.get("usageMetadata"))
    model = data.get("modelVersion") if isinstance(data.get("modelVersion"), str) else None
    meta = {"response_id": data.get("responseId") if isinstance(data.get("responseId"), str) else None, "http_status": status}
    feedback = data.get("promptFeedback") if isinstance(data.get("promptFeedback"), dict) else {}
    candidates = data.get("candidates")
    if feedback.get("blockReason"):
        return AdapterResult(True, None, model, None, None, None, f"prompt blocked by the provider ({str(feedback['blockReason'])[:40]})", {},
                             usage=usage, provider_meta={**meta, "block_reason": str(feedback["blockReason"])[:40]}, repairable=False)
    if not isinstance(candidates, list) or not candidates:
        return AdapterResult(True, None, model, None, None, None, "response has no candidates", {}, usage=usage, provider_meta=meta, repairable=False)
    if len(candidates) != 1:
        return AdapterResult(True, None, model, None, None, None, f"expected exactly one candidate, got {len(candidates)}", {}, usage=usage,
                             provider_meta=meta, repairable=False)
    cand = candidates[0] if isinstance(candidates[0], dict) else {}
    finish = cand.get("finishReason") if isinstance(cand.get("finishReason"), str) else None
    meta["finish_reason"] = finish
    parts = (cand.get("content") or {}).get("parts") if isinstance(cand.get("content"), dict) else None
    parts = parts if isinstance(parts, list) else []
    texts, other = [], []
    for part in parts:
        if not isinstance(part, dict):
            other.append("malformed")
        elif part.get("thought") is True:
            continue                                         # thought content is never used or stored
        elif isinstance(part.get("text"), str):
            texts.append(part["text"])
        else:
            other.append(next((k for k in part if k not in ("thoughtSignature",)), "empty"))
    meta["dropped_thought_parts"] = sum(1 for p in parts if isinstance(p, dict) and p.get("thought") is True)
    if finish in REFUSED:
        return AdapterResult(True, None, model, None, None, finish, f"provider stopped the candidate ({finish})", {}, usage=usage, provider_meta=meta, repairable=False)
    if finish in TRUNCATED:
        return AdapterResult(True, None, model, None, None, finish, f"output truncated ({finish}); not parsed", {}, usage=usage, provider_meta=meta, repairable=False)
    if finish not in ("STOP", None):
        return AdapterResult(True, None, model, None, None, finish, f"unexpected finish reason {finish[:40]}", {}, usage=usage, provider_meta=meta, repairable=False)
    if finish is None:
        return AdapterResult(True, None, model, None, None, None, "candidate has no finish reason (incomplete)", {}, usage=usage, provider_meta=meta, repairable=False)
    if other:
        return AdapterResult(True, None, model, None, None, finish, f"non-text part(s) in the candidate: {sorted(set(map(str, other)))[:3]}", {}, usage=usage,
                             provider_meta=meta, repairable=False)
    text = "".join(texts)
    if not text.strip():
        return AdapterResult(True, None, model, None, None, finish, "candidate text is empty", {}, usage=usage, provider_meta=meta, repairable=True)
    return AdapterResult(True, text, model, usage.get("input_tokens"), usage.get("output_tokens"), finish, None, {}, usage=usage, provider_meta=meta)
