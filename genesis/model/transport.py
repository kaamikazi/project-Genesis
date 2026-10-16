"""Wire transports with explicit outcome classes. No retries happen here: every attempt is one ledger record.

Outcome classes (what the caller may conclude):
- Delivered response:     an HTTP status and body were received.
- NotDelivered:           the request provably never reached a server (e.g. connection refused). Usage: none.
- OutcomeUnknown:         the request may have reached the server (timeout, reset after sending). Usage: unknown.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class NotDelivered(Exception):
    pass


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
