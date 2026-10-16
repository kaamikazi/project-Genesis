"""Public output schema and strict parser for model proposals (genesis-action-schema-1 / genesis-parser-1).

A model may return exactly one JSON object:
  {"kind": <action kind>, "params": {...}, "explanation": <optional short text>, "standing": <optional bool>}
The controller fills in the agent identity, tick and action id; a model cannot choose who acts or when.
Validation here is syntactic and structural (JSON, size, fields, kinds, parameter names, finite values). Whether the
action is legal is decided only by the engine; a well-formed illegal action becomes an ordinary rejected world action.
"""
from __future__ import annotations

import json
import math
from typing import Any

from ..engine import OPTIONAL_PARAMS, PARAMS
from ..models import JSON, Action, canonical

KINDS = sorted(PARAMS)
TOP_LEVEL = {"kind", "params", "explanation", "standing"}
STANDING_KINDS = {"use_artifact", "produce", "gather", "consume", "wait"}   # may be repeated by the executor while they keep succeeding
STRUCTURED_PARAMS = {"program", "sources"}                                   # the only parameters that may hold objects or lists
MAX_STRING, MAX_EXPLANATION, MAX_STRUCTURED_BYTES, MAX_INT = 128, 200, 4096, 10**6


def output_schema() -> JSON:
    """JSON Schema sent to adapters that declare structured-output support (and shown in every prompt)."""
    return {"type": "object", "additionalProperties": False, "required": ["kind", "params"],
            "properties": {"kind": {"type": "string", "enum": KINDS},
                           "params": {"type": "object"},
                           "explanation": {"type": "string", "maxLength": MAX_EXPLANATION},
                           "standing": {"type": "boolean"}}}


def action_catalogue() -> list[JSON]:
    """The public action contract: kinds with required and optional parameter names."""
    return [{"kind": k, "required": sorted(PARAMS[k]), "optional": sorted(OPTIONAL_PARAMS.get(k, set()))} for k in KINDS]


class ParseError(ValueError):
    pass


def _reject_constant(name: str) -> Any:
    raise ParseError(f"non-finite number {name} is not allowed")


def _check_value(key: str, value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise ParseError(f"parameter {key} is nested too deeply")
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if abs(value) > MAX_INT:
            raise ParseError(f"parameter {key} is out of range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ParseError(f"parameter {key} is not finite")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise ParseError(f"parameter {key} is too long")
        return
    if isinstance(value, (dict, list)):
        if key not in STRUCTURED_PARAMS:
            raise ParseError(f"parameter {key} may not be an object or list")
        if len(canonical(value).encode("utf-8")) > MAX_STRUCTURED_BYTES:
            raise ParseError(f"parameter {key} exceeds {MAX_STRUCTURED_BYTES} bytes")
        for k, v in (value.items() if isinstance(value, dict) else enumerate(value)):
            if isinstance(value, dict) and not isinstance(k, str):
                raise ParseError("object keys must be strings")
            _check_value(key, v, depth + 1)
        return
    raise ParseError(f"parameter {key} has an unsupported type")


def parse_proposal(text: str, max_bytes: int) -> JSON:
    """Strict parse of one model output into a proposal dict {kind, params, explanation?, standing?}."""
    if text is None:
        raise ParseError("empty response")
    if len(text.encode("utf-8")) > max_bytes:
        raise ParseError(f"response exceeds {max_bytes} bytes")
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except ParseError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParseError(f"invalid JSON: {exc.msg if hasattr(exc, 'msg') else exc}") from None
    if not isinstance(data, dict):
        raise ParseError("the response must be one JSON object")
    extra = set(data) - TOP_LEVEL
    if extra:
        raise ParseError(f"unexpected top-level fields: {sorted(extra)}")
    kind, params = data.get("kind"), data.get("params")
    if kind not in PARAMS:
        raise ParseError(f"unknown action kind {str(kind)[:40]!r}")
    if not isinstance(params, dict):
        raise ParseError("params must be an object")
    required, optional = PARAMS[kind], OPTIONAL_PARAMS.get(kind, set())
    if not required <= set(params) <= required | optional:
        raise ParseError(f"{kind} needs parameters {sorted(required)} (optional {sorted(optional)}), got {sorted(params)}")
    for k, v in params.items():
        _check_value(k, v)
    explanation = data.get("explanation")
    if explanation is not None and (not isinstance(explanation, str) or len(explanation) > MAX_EXPLANATION):
        raise ParseError("explanation must be a short string")
    standing = data.get("standing", False)
    if not isinstance(standing, bool) or (standing and kind not in STANDING_KINDS):
        raise ParseError(f"standing is allowed only for {sorted(STANDING_KINDS)}")
    out = {"kind": kind, "params": params, "standing": standing}
    if explanation:
        out["explanation"] = explanation          # a generated explanation; never authoritative state
    return out


def to_action(proposal: JSON, agent_id: str, tick: int) -> Action:
    """The controller, not the model, sets identity and timing."""
    return Action(id=f"{tick}:{agent_id}", agent=agent_id, tick=tick, kind=proposal["kind"], params=proposal["params"])
