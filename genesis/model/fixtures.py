"""Verification-only responders: a deterministic fixture policy behind the Ollama and Gemini wire formats, plus loopback
mock servers. Fixture output is scripted; it is NOT evidence of model competence or intelligence.

The fixture policy reads the observation back out of the prompt and answers with a simple rule (eat when hungry,
fetch ore when short, otherwise produce or use a held workflow). A `script` maps the n-th call (1-based, counted
per responder) to an injected behaviour: invalid JSON, a well-formed illegal action, a timeout, an HTTP error,
missing usage counts, or a credential echo.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..models import JSON
from .prompt import extract_observation
from .transport import InProcessTransport, OutcomeUnknown, WireResponse

FIXED_CREATED_AT = "2026-10-16T00:00:00Z"


def fixture_policy(obs: JSON) -> JSON:
    a = obs["self"]
    inv = a["inventory"]
    sites = sorted(obs.get("sites") or [], key=lambda s: (abs(s["x"] - a["x"]) + abs(s["y"] - a["y"]), s["id"]))
    if a["energy"] <= 18 and inv.get("food", 0) > 0:
        return {"kind": "consume", "params": {}, "explanation": "fixture rule: eat when energy is low"}
    if inv.get("food", 0) < 2:
        food = [s for s in sites if s["resource"] == "food" and s["stock"] > 0]
        if food and abs(food[0]["x"] - a["x"]) + abs(food[0]["y"] - a["y"]) <= 1:
            return {"kind": "gather", "params": {"site": food[0]["id"]}, "explanation": "fixture rule: gather food"}
    if inv.get("ore", 0) < 2:
        ore = [s for s in sites if s["resource"] == "ore" and s["stock"] > 0]
        if ore and abs(ore[0]["x"] - a["x"]) + abs(ore[0]["y"] - a["y"]) <= 1:
            return {"kind": "gather", "params": {"site": ore[0]["id"]}, "standing": True, "explanation": "fixture rule: gather ore"}
        if ore:
            dx = (ore[0]["x"] > a["x"]) - (ore[0]["x"] < a["x"])
            dy = 0 if dx else (ore[0]["y"] > a["y"]) - (ore[0]["y"] < a["y"])
            return {"kind": "move", "params": {"x": a["x"] + dx, "y": a["y"] + dy}, "explanation": "fixture rule: walk to ore"}
    held = [k for k in a.get("known", []) if (obs.get("artifacts") or {}).get(k, {}).get("status") in ("admitted", "superseded")
            and (obs.get("artifacts") or {}).get(k, {}).get("kind") == "workflow"]
    if held:
        return {"kind": "use_artifact", "params": {"artifact": held[-1]}, "standing": True, "explanation": "fixture rule: run the newest held workflow"}
    return {"kind": "produce", "params": {}, "standing": True, "explanation": "fixture rule: produce with the baseline workflow"}


class FixtureResponder:
    """Turns an Ollama /api/chat request body into a response, deterministically. Thread-safe call counter."""

    def __init__(self, script: dict[int, str] | None = None, model: str = "fixture-policy-1", policy=fixture_policy):
        self.script, self.model, self.policy = dict(script or {}), model, policy
        self.calls = 0
        self.requests: list[JSON] = []
        self.lock = threading.Lock()

    def respond(self, body: bytes) -> tuple[int, bytes, str | None]:
        """Returns (status, body, special) where special may be 'timeout'."""
        request = json.loads(body.decode("utf-8"))
        with self.lock:
            self.calls += 1
            n = self.calls
            self.requests.append(request)
        fault = self.script.get(n)
        if fault == "timeout":
            return 0, b"", "timeout"
        if fault == "http-500":
            return 500, json.dumps({"error": "fixture internal error"}).encode(), None
        user = next(m["content"] for m in request["messages"] if m["role"] == "user")
        obs = extract_observation(user)
        action = self.policy(obs)
        if fault == "invalid-json":
            content = '{"kind": "consume", "params": {'                       # truncated JSON
        elif fault == "illegal-action":
            content = json.dumps({"kind": "transfer", "params": {"target": "nobody", "resource": "ore", "amount": 999}})
        elif fault == "secret-echo":
            content = json.dumps({"kind": "wait", "params": {}, "explanation": "api_key=sk-FAKEFAKEFAKEFAKEFAKE1234"})
        elif fault == "extra-field":
            content = json.dumps({**action, "agent": "a01"})
        else:
            content = json.dumps(action, sort_keys=True)
        prompt_bytes = sum(len(m["content"].encode("utf-8")) for m in request["messages"])
        payload = {"model": self.model, "created_at": FIXED_CREATED_AT, "message": {"role": "assistant", "content": content, "thinking": "fixture reasoning (must not be stored)"},
                   "done": True, "done_reason": "stop", "total_duration": 1000, "load_duration": 0, "prompt_eval_duration": 500, "eval_duration": 500}
        if fault != "no-usage":
            payload.update(prompt_eval_count=prompt_bytes // 4, eval_count=max(1, len(content) // 4))
        return 200, json.dumps(payload).encode("utf-8"), None


def in_process_transport(responder: FixtureResponder, kind: str = "fixture") -> InProcessTransport:
    def handler(url: str, body: bytes, headers: dict) -> WireResponse:
        status, data, special = responder.respond(body)
        if special == "timeout":
            raise OutcomeUnknown("fixture timeout (request may have reached the provider)")
        return WireResponse(status, data)
    return InProcessTransport(handler, kind)


def default_fixture_transport() -> InProcessTransport:
    return in_process_transport(FixtureResponder())


class MockOllamaServer:
    """A loopback HTTP server speaking the Ollama /api/chat wire format (verification only)."""

    def __init__(self, responder: FixtureResponder, timeout_sleep_s: float = 2.0):
        self.responder, self.timeout_sleep_s = responder, timeout_sleep_s
        self.headers_seen: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):     # keep test output quiet
                return

            def do_POST(self):                # noqa: N802
                outer.headers_seen.append(dict(self.headers))
                if self.path != "/api/chat":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                status, data, special = outer.responder.respond(body)
                if special == "timeout":
                    time.sleep(outer.timeout_sleep_s)
                    status, data = 200, json.dumps({"model": outer.responder.model, "message": {"role": "assistant", "content": "{}"}, "done": True}).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> "MockOllamaServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


# --- Gemini generateContent fixtures (v0.6.1; verification only, scripted, no network beyond loopback) -----------------

GEMINI_FAULTS = ("invalid-json", "illegal-action", "timeout", "http-500", "http-429", "http-400-schema", "blocked-prompt", "safety",
                 "max-tokens", "two-candidates", "no-candidates", "empty-text", "non-text-part", "thought-parts", "no-usage",
                 "inconsistent-usage", "nonfinite-usage", "overshoot", "secret-echo", "extra-field", "redirect")


class GeminiFixtureResponder:
    """Turns a generateContent request body into a generateContent response, deterministically.
    Usage is synthetic (characters / 4) with a fixed thinking count, so thinking accounting is exercised."""

    def __init__(self, script: dict[int, str] | None = None, model_version: str = "gemini-3.5-flash-lite", policy=fixture_policy,
                 thinking_tokens: int = 24):
        self.script, self.model_version, self.policy, self.thinking_tokens = dict(script or {}), model_version, policy, thinking_tokens
        self.calls = 0
        self.requests: list[JSON] = []
        self.lock = threading.Lock()

    def respond(self, body: bytes) -> tuple[int, bytes, str | None]:
        request = json.loads(body.decode("utf-8"))
        with self.lock:
            self.calls += 1
            n = self.calls
            self.requests.append(request)
        fault = self.script.get(n)
        if fault == "timeout":
            return 0, b"", "timeout"
        if fault == "redirect":
            return 302, b"", "redirect"
        if fault == "http-500":
            return 500, json.dumps({"error": {"code": 500, "message": "fixture internal error", "status": "INTERNAL"}}).encode(), None
        if fault == "http-429":
            return 429, json.dumps({"error": {"code": 429, "message": "fixture quota exceeded", "status": "RESOURCE_EXHAUSTED"}}).encode(), None
        if fault == "http-400-schema":
            return 400, json.dumps({"error": {"code": 400, "message": "fixture: schema not supported", "status": "INVALID_ARGUMENT"}}).encode(), None
        user = request["contents"][0]["parts"][0]["text"]
        action = self.policy(extract_observation(user))
        text = json.dumps(action, sort_keys=True)
        if fault == "invalid-json":
            text = '{"kind": "consume", "params": {'
        elif fault == "illegal-action":
            text = json.dumps({"kind": "transfer", "params": {"target": "nobody", "resource": "ore", "amount": 999}})
        elif fault == "secret-echo":
            text = json.dumps({"kind": "wait", "params": {}, "explanation": "key AIzaFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE00"})
        elif fault == "extra-field":
            text = json.dumps({**action, "agent": "a01"})
        elif fault == "empty-text":
            text = "  "
        prompt_tokens = (len(user) + len(request["systemInstruction"]["parts"][0]["text"])) // 4
        cand_tokens = max(1, len(text) // 4)
        thoughts = self.thinking_tokens
        if fault == "overshoot":
            thoughts = request["generationConfig"]["maxOutputTokens"] + 50
        usage = {"promptTokenCount": prompt_tokens, "candidatesTokenCount": cand_tokens, "thoughtsTokenCount": thoughts,
                 "totalTokenCount": prompt_tokens + cand_tokens + thoughts}
        if fault == "inconsistent-usage":
            usage["totalTokenCount"] += 7
        parts = [{"text": text}]
        if fault == "thought-parts":
            parts = [{"text": "FIXTURE THOUGHT CONTENT (must never be stored)", "thought": True}, {"text": text, "thoughtSignature": "c2ln"}]
        if fault == "non-text-part":
            parts = [{"functionCall": {"name": "shell", "args": {"cmd": "ls"}}}]
        candidate = {"content": {"role": "model", "parts": parts}, "finishReason": "STOP", "index": 0}
        if fault == "safety":
            candidate = {"finishReason": "SAFETY", "index": 0}
        if fault == "max-tokens":
            candidate = {"content": {"role": "model", "parts": [{"text": text[: len(text) // 2]}]}, "finishReason": "MAX_TOKENS", "index": 0}
        payload: JSON = {"candidates": [candidate], "modelVersion": self.model_version, "responseId": f"fixture-{n}"}
        if fault == "two-candidates":
            payload["candidates"] = [candidate, {**candidate, "index": 1}]
        if fault in ("no-candidates", "blocked-prompt"):
            payload["candidates"] = []
        if fault == "blocked-prompt":
            payload["promptFeedback"] = {"blockReason": "SAFETY"}
        if fault != "no-usage":
            payload["usageMetadata"] = usage
        raw = json.dumps(payload)
        if fault == "nonfinite-usage":
            raw = raw.replace(f'"thoughtsTokenCount": {thoughts}', '"thoughtsTokenCount": NaN')
        return 200, raw.encode("utf-8"), None


def gemini_in_process_transport(responder: GeminiFixtureResponder, kind: str = "fixture") -> InProcessTransport:
    def handler(url: str, body: bytes, headers: dict) -> WireResponse:
        status, data, special = responder.respond(body)
        if special == "timeout":
            raise OutcomeUnknown("fixture timeout (request may have reached the provider)")
        return WireResponse(status, data)
    return InProcessTransport(handler, kind)


def default_gemini_fixture_transport() -> InProcessTransport:
    return gemini_in_process_transport(GeminiFixtureResponder())


class MockGeminiServer:
    """A loopback HTTP server speaking the generateContent wire format (verification only). It records request paths,
    header names and the key header value (synthetic test keys only); a `redirect` fault answers 302 to `redirect_target`."""

    def __init__(self, responder: GeminiFixtureResponder, timeout_sleep_s: float = 2.0, redirect_target: str = "http://127.0.0.1:9/elsewhere"):
        self.responder, self.timeout_sleep_s, self.redirect_target = responder, timeout_sleep_s, redirect_target
        self.seen: list[JSON] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_POST(self):                # noqa: N802
                outer.seen.append({"path": self.path, "header_names": sorted(k.lower() for k in self.headers.keys()),
                                   "key_header": self.headers.get("x-goog-api-key")})
                if not (self.path.startswith("/v1beta/models/") and self.path.endswith(":generateContent")):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                status, data, special = outer.responder.respond(body)
                if special == "timeout":
                    time.sleep(outer.timeout_sleep_s)
                    status, data = 200, b"{}"
                try:
                    self.send_response(status)
                    if special == "redirect":
                        self.send_header("Location", outer.redirect_target)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> "MockGeminiServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
