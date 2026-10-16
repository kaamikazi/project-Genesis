"""Durable call ledger: sidecar tables in the run's SQLite database (never part of agent-visible world state).

Lifecycle of one request (one row per attempt; a repair is its own row linked by parent_id):
  reserved -> dispatching -> completed -> consumed
  reserved -> cancelled-before-dispatch     (process ended before sending; nothing left the machine)
  dispatching -> failed-not-delivered       (provably never reached a server)
  dispatching -> failed-delivered           (an error response was received; usage unknown, reservation kept)
  dispatching -> outcome-unknown            (timeout, reset, or the process ended mid-dispatch; never resent)
  completed -> expired-unconsumed           (the world moved on before the response could be applied)
  blocked                                   (not sent: budget, redaction, prompt size, concurrency)
Identity and reservation are written before dispatch; a completed response is written before any world transition
uses it; `consumed` is set in the same database transaction that commits the tick.
No credentials, headers or provider reasoning fields are stored.
"""
from __future__ import annotations

import json
import time

from ..models import JSON, digest

DDL = """
CREATE TABLE IF NOT EXISTS model_profiles(run_id TEXT PRIMARY KEY, profile TEXT NOT NULL, profile_hash TEXT NOT NULL, paused INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS model_calls(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT UNIQUE NOT NULL, run_id TEXT NOT NULL, agent TEXT NOT NULL, tick INTEGER NOT NULL,
  role TEXT NOT NULL, attempt INTEGER NOT NULL, parent_id TEXT, identity TEXT NOT NULL, status TEXT NOT NULL, worker TEXT, lease_until REAL,
  source TEXT NOT NULL, endpoint_label TEXT, requested_model TEXT, returned_model TEXT, prompt TEXT, prompt_hash TEXT, input_bytes INTEGER,
  truncations TEXT, response TEXT, response_hash TEXT, parsed TEXT, parse_error TEXT, usage TEXT, latency_ms REAL, termination TEXT,
  reservation TEXT, reconciled TEXT, fallback TEXT, receipt TEXT, consumed_tick INTEGER, reexecutable INTEGER NOT NULL DEFAULT 1,
  recorded_from TEXT, resolved INTEGER NOT NULL DEFAULT 0, created_at REAL, updated_at REAL);
CREATE INDEX IF NOT EXISTS model_calls_run ON model_calls(run_id, agent, tick);
"""
JSON_FIELDS = ("identity", "truncations", "parsed", "usage", "reservation", "reconciled")
TRANSITIONS = {
    None: {"reserved", "blocked", "completed"},                  # completed directly only for recorded re-use
    "reserved": {"dispatching", "cancelled-before-dispatch", "blocked"},
    "dispatching": {"completed", "failed-not-delivered", "failed-delivered", "outcome-unknown"},
    "completed": {"consumed", "expired-unconsumed"},
    "cancelled-before-dispatch": {"reserved"},
}


def decision_identity(run_id: str, agent: str, tick: int, role: str, attempt: int, observation_hash: str, prompt_version: str,
                      schema_version: str, config_hash: str) -> JSON:
    """Stable identity of one decision request. The observation hash alone is not unique (identical observations recur);
    the committed decision position (run, agent, tick) and the call role/attempt make it so. No secrets."""
    return {"run_id": run_id, "agent": agent, "tick": tick, "role": role, "attempt": attempt, "observation_hash": observation_hash,
            "prompt_version": prompt_version, "schema_version": schema_version, "config_hash": config_hash}


def decision_id(identity: JSON) -> str:
    return digest(identity)


def receipt(row: JSON) -> str:
    """Immutable receipt binding identity, the exact response used and its parse result."""
    return digest({"decision_id": row["decision_id"], "identity": row["identity"], "prompt_hash": row["prompt_hash"],
                   "response_hash": row["response_hash"], "parsed": row["parsed"], "parse_error": row["parse_error"]})


def decode(row) -> JSON:
    out = dict(row)
    for k in JSON_FIELDS:
        if out.get(k) is not None:
            out[k] = json.loads(out[k])
    return out


def rows(db, run_id: str, agent: str | None = None) -> list[JSON]:
    q = "SELECT * FROM model_calls WHERE run_id=?" + (" AND agent=?" if agent else "") + " ORDER BY seq"
    return [decode(r) for r in db.execute(q, (run_id, agent) if agent else (run_id,))]


def get(db, did: str) -> JSON | None:
    r = db.execute("SELECT * FROM model_calls WHERE decision_id=?", (did,)).fetchone()
    return decode(r) if r else None


def insert(db, row: JSON) -> None:
    status = row["status"]
    if status not in TRANSITIONS[None]:
        raise ValueError(f"invalid initial status {status}")
    now = time.time()
    data = {**row, "created_at": now, "updated_at": now}
    for k in JSON_FIELDS:
        if data.get(k) is not None:
            data[k] = json.dumps(data[k], sort_keys=True)
    cols = sorted(data)
    db.execute(f"INSERT INTO model_calls({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", [data[c] for c in cols])


def update(db, did: str, status: str | None = None, **fields) -> None:
    if status is not None:
        current = db.execute("SELECT status FROM model_calls WHERE decision_id=?", (did,)).fetchone()
        if current is None:
            raise KeyError(did)
        if status not in TRANSITIONS.get(current[0], set()):
            raise ValueError(f"illegal ledger transition {current[0]} -> {status}")
        fields["status"] = status
    fields["updated_at"] = time.time()
    for k in JSON_FIELDS:
        if k in fields and fields[k] is not None:
            fields[k] = json.dumps(fields[k], sort_keys=True)
    cols = sorted(fields)
    db.execute(f"UPDATE model_calls SET {','.join(c + '=?' for c in cols)} WHERE decision_id=?", [fields[c] for c in cols] + [did])


SANITIZED_EXPORT_FIELDS = ("seq", "decision_id", "agent", "tick", "role", "attempt", "parent_id", "identity", "status", "source", "endpoint_label",
                           "requested_model", "returned_model", "prompt", "prompt_hash", "input_bytes", "truncations", "response", "response_hash",
                           "parsed", "parse_error", "usage", "termination", "reservation", "reconciled", "fallback", "receipt", "consumed_tick",
                           "reexecutable", "recorded_from", "resolved")


def export_rows(db, run_id: str) -> list[JSON]:
    """For exports and the API: no worker ids, leases or wall-clock fields (latency is reported separately)."""
    return [{k: r.get(k) for k in SANITIZED_EXPORT_FIELDS} for r in rows(db, run_id)]
