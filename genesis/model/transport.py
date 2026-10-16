"""Wire transports with explicit outcome classes. No retries happen here: every attempt is one ledger record.

Outcome classes (what the caller may conclude):
- Delivered response:     an HTTP status and body were received.
- NotDelivered:           the request provably never reached a server (e.g. connection refused). Usage: none.
- OutcomeUnknown:         the request may have reached the server (timeout, reset after sending). Usage: unknown.
"""
from __future__ import annotations

import os
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
GEMINI_ORIGIN = "https://generativelanguage.googleapis.com"
GEMINI_KEY_ENV = "GEMINI_API_KEY"


class NotDelivered(Exception):
    pass


class CredentialMissing(RuntimeError):
    """Setup error raised before anything is reserved or sent. Never includes environment values."""


class OutcomeUnknown(Exception):
    pass


@dataclass
class WireResponse:
    status: int
    body: bytes


class Transport(Protocol):
    kind: str          # "fixture" | "mock-http" | "recorded" | "live"

    def send(self, url: str, body: bytes, headers: dict[str, str], timeout_s: float, max_response_bytes: int) -> WireResponse: ...


class HttpTransport:
    """Plain HTTP POST via the standard library. `loopback_only` refuses any non-loopback host (used for mock servers);
    live use requires an explicit authorization recorded in the model profile and an environment switch."""

    def __init__(self, kind: str, loopback_only: bool = True):
        self.kind, self.loopback_only = kind, loopback_only

    def send(self, url: str, body: bytes, headers: dict[str, str], timeout_s: float, max_response_bytes: int) -> WireResponse:
        host = urlparse(url).hostname or ""
        if self.loopback_only and host not in LOOPBACK:
            raise NotDelivered(f"refusing non-loopback host for transport kind {self.kind}")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        sent = False
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as resp:     # noqa: S310 (scheme checked by caller)
                sent = True
                data = resp.read(max_response_bytes + 1)
                return WireResponse(resp.status, data)
        except urllib.error.HTTPError as exc:
            return WireResponse(exc.code, exc.read(max_response_bytes + 1))
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ConnectionRefusedError):
                raise NotDelivered("connection refused") from None
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise OutcomeUnknown("timed out") from None
            raise OutcomeUnknown(f"transport error after possible delivery: {type(exc.reason).__name__}") from None
        except (socket.timeout, TimeoutError):
            raise OutcomeUnknown("timed out" + (" while reading" if sent else "")) from None
        except (ConnectionResetError, ConnectionAbortedError):
            raise OutcomeUnknown("connection reset after possible delivery") from None


class InProcessTransport:
    """Calls a Python handler with the serialized request (no sockets). Used for fixtures and unit tests."""

    def __init__(self, handler: Callable[[str, bytes, dict], WireResponse], kind: str = "fixture"):
        self.handler, self.kind = handler, kind

    def send(self, url: str, body: bytes, headers: dict[str, str], timeout_s: float, max_response_bytes: int) -> WireResponse:
        response = self.handler(url, body, headers)
        return WireResponse(response.status, response.body[:max_response_bytes + 1])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: urllib then surfaces the 3xx as an HTTPError, i.e. an ordinary non-200 response.
    (The default handler would re-send non-content headers, including an API key header, to the new location.)"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class GeminiTransport:
    """HTTPS POST to the Gemini Developer API only.

    - The x-goog-api-key header is read from the process environment (GEMINI_API_KEY) at send time and attached only
      when the URL's scheme, host and port equal the allowed origin and the path is /v1beta/models/{model}:generateContent
      with no query string. The key is never logged, stored, put in a URL or returned in an error.
    - Redirects are never followed; there are no retries (every attempt is one ledger row).
    - `for_loopback_test` builds an isolated instance whose allowed origin is a loopback mock server; it cannot target
      any non-loopback host, so tests never justify a production origin bypass.
    """

    def __init__(self, kind: str = "live", origin: str = GEMINI_ORIGIN, key_env: str = GEMINI_KEY_ENV):
        if origin != GEMINI_ORIGIN:
            raise ValueError("GeminiTransport only targets the official Gemini API origin (use for_loopback_test in tests)")
        self.kind, self.origin, self.key_env = kind, origin, key_env
        self._opener = urllib.request.build_opener(_NoRedirect)

    @classmethod
    def for_loopback_test(cls, base_url: str, kind: str = "mock-http", key_env: str = GEMINI_KEY_ENV) -> "GeminiTransport":
        u = urlparse(base_url)
        if u.scheme != "http" or u.hostname not in LOOPBACK:
            raise ValueError("test transports may only target a loopback http origin")
        inst = cls.__new__(cls)
        inst.kind, inst.origin, inst.key_env = kind, f"{u.scheme}://{u.netloc}", key_env
        inst._opener = urllib.request.build_opener(_NoRedirect)
        return inst

    def preflight(self) -> None:
        if not os.environ.get(self.key_env, "").strip():
            raise CredentialMissing(f"{self.key_env} is not set in this process environment; set it for this session only "
                                    "(see docs/GEMINI_SETUP.md). Nothing was reserved or sent.")

    def _allowed(self, url: str) -> bool:
        u, o = urlparse(url), urlparse(self.origin)
        return (u.scheme, u.hostname, u.port) == (o.scheme, o.hostname, o.port) and not u.query and not u.username and not u.password             and u.path.startswith("/v1beta/models/") and u.path.endswith(":generateContent") and ".." not in u.path

    def send(self, url: str, body: bytes, headers: dict[str, str], timeout_s: float, max_response_bytes: int) -> WireResponse:
        if not self._allowed(url):
            raise NotDelivered("refusing to send credentials outside the allowed Gemini origin and path")
        key = os.environ.get(self.key_env, "").strip()
        if not key:
            raise NotDelivered(f"{self.key_env} is not set; nothing was sent")
        wire_headers = {k: v for k, v in headers.items() if k in ("Content-Type", "Accept")}
        wire_headers["x-goog-api-key"] = key
        request = urllib.request.Request(url, data=body, headers=wire_headers, method="POST")
        del key, wire_headers
        sent = False
        try:
            with self._opener.open(request, timeout=timeout_s) as resp:          # noqa: S310 (origin checked above)
                sent = True
                return WireResponse(resp.status, resp.read(max_response_bytes + 1))
        except urllib.error.HTTPError as exc:
            return WireResponse(exc.code, exc.read(max_response_bytes + 1))
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ConnectionRefusedError):
                raise NotDelivered("connection refused") from None
            if isinstance(exc.reason, socket.gaierror):
                raise NotDelivered("name resolution failed") from None
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise NotDelivered("TLS certificate verification failed before sending") from None
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise OutcomeUnknown("timed out") from None
            raise OutcomeUnknown(f"transport error after possible delivery: {type(exc.reason).__name__}") from None
        except (socket.timeout, TimeoutError):
            raise OutcomeUnknown("timed out" + (" while reading" if sent else "")) from None
        except (ConnectionResetError, ConnectionAbortedError):
            raise OutcomeUnknown("connection reset after possible delivery") from None
        finally:
            request.headers.pop("X-goog-api-key", None)                          # urllib capitalizes header names
