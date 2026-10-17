"""Phase A of a model-backed tick: decide, reserve, dispatch, persist. Runs OUTSIDE any database write transaction.

Each ledger write is its own short transaction; network I/O happens between them, never inside one. Phase B (the
engine tick) only reads the prepared results, so a slow response can never be applied to a world that changed: the
store re-checks the state hash before committing.

Crash/restart rules (see ledger.py for states):
- a row still `reserved` from an ended process was never sent: it may be dispatched again under the same identity;
- a row `dispatching` from an ended process may have reached the provider: it becomes `outcome-unknown`, keeps its
  reservation, is never resent, and model use for that agent pauses until an operator resolves it;
- a `completed`, unconsumed row whose full identity matches the current decision is reused without a new call;
- a completed row whose tick has passed becomes `expired-unconsumed` (never applied to a later world).
Neither Ollama nor Gemini documents an idempotency key or status lookup, so no exactly-once claim is made.

Run-level halts (v0.6.1): after an HTTP 429 / RESOURCE_EXHAUSTED response, after a response whose reported usage
exceeded its reservation, or once the profile's wall-clock run deadline has passed, no further request is dispatched
for the run; later decisions are labelled fallbacks. Nothing is retried, rotated or switched.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field

from ..models import JSON, digest
from ..world import LocalObservations
from . import ACTION_SCHEMA_VERSION, PROMPT_VERSION
from . import adapter, budget, gemini, ledger, scheduler
from .profile import ModelProfile, config_hash
from .prompt import build_messages
from .schema import ParseError, parse_proposal
from .transport import CredentialMissing, NotDelivered, OutcomeUnknown, Transport  # noqa: F401 (CredentialMissing re-exported)

SECRET_PATTERNS = [re.compile(p) for p in (r"(?i)bearer\s+[a-z0-9._\-]{8,}", r"\bsk-[A-Za-z0-9_\-]{16,}", r"\bAIza[0-9A-Za-z_\-]{30,}",
                                           r"(?i)\b(api[_-]?key|authorization|x-api-key|x-goog-api-key)\s*[:=]\s*\S{8,}")]


class DecisionInFlight(RuntimeError):
    """Another live worker holds this decision; this worker must not dispatch or commit it."""


class RecordingMismatch(RuntimeError):
    """Strict recorded mode found no matching recording for a decision."""


class LiveCallsDisabled(RuntimeError):
    pass


class SimulatedCrash(RuntimeError):
    """Raised by test hooks to emulate the process ending at a chosen point."""


def live_guard(profile: ModelProfile, transport) -> None:
    """Every condition a dispatch needs, checked before anything is reserved. Raises; never prints secrets."""
    if profile.mode == "live" and not (profile.live_authorized and os.environ.get("GENESIS_LIVE_MODEL_CALLS") == "1"):
        raise LiveCallsDisabled("live model calls need live_authorized in the profile and GENESIS_LIVE_MODEL_CALLS=1")
    if profile.mode == "live" and profile.adapter.provider == "gemini":
        missing = profile.operator_confirmations.missing() if profile.operator_confirmations else ["operator_confirmations"]
        if missing:
            raise LiveCallsDisabled(f"live Gemini calls need the operator's free-tier confirmations: missing {missing}")
        if profile.run_deadline_s is None:
            raise LiveCallsDisabled("live Gemini calls need a finite run_deadline_s")
        if (profile.adapter.wire_schema or "genesis-gemini-wire-1") != "genesis-gemini-wire-2":
            raise LiveCallsDisabled("genesis-gemini-wire-1 cannot express action parameters (found in the 2026-10-17 smoke run); "
                                    "set adapter.wire_schema to genesis-gemini-wire-2")
    if hasattr(transport, "preflight"):
        transport.preflight()                     # CredentialMissing: concise, contains no environment values


def run_halt(profile: ModelProfile, run_rows: list[JSON], now: float) -> str | None:
    for r in run_rows:
        use = r.get("usage") or {}
        if use.get("halt") == "quota":
            return "provider quota or rate limit reached (HTTP 429); model dispatch stopped for this run; no retry"
        if use.get("reservation_exceeded"):
            return "reported usage exceeded its reservation; model dispatch stopped for this run"
    if profile.run_deadline_s is not None:
        started = [r["created_at"] for r in run_rows if r["status"] not in budget.NO_USAGE and r.get("source") != "recorded" and r.get("created_at")]
        if started and now - min(started) > profile.run_deadline_s:
            return f"run wall-clock deadline of {profile.run_deadline_s} s reached; model dispatch stopped"
    return None


def env_secrets() -> list[str]:
    return [v for k, v in os.environ.items() if any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASSWORD")) and len(v) >= 8]


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS) or any(s in text for s in env_secrets())


def scrub(text: str) -> str:
    for s in env_secrets():
        text = text.replace(s, "[REDACTED]")
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


@dataclass
class Prepared:
    mode: str                          # "model-proposal" | "model-intent-execution" | "offline-policy" | "fallback"
    reason: str
    observation_hash: str
    proposal: JSON | None = None
    decision_ids: list[str] = field(default_factory=list)
    receipt: str | None = None
    source: str | None = None
    new_calls: int = 0
    new_tokens: int = 0
    origin: str | None = None          # intent: the decision id whose standing choice is executed


class ModelRuntime:
    def __init__(self, store, run_id: str, profile: ModelProfile, transport: Transport | None, worker: str | None = None, hooks: dict | None = None):
        self.store, self.run_id, self.profile, self.transport = store, run_id, profile, transport
        self.worker = worker or uuid.uuid4().hex[:12]
        self.hooks = hooks or {}
        self.cfg_hash = config_hash(profile)
        self.source = "recorded" if profile.mode == "recorded" else (transport.kind if transport else profile.mode)
        self.wire = gemini if profile.adapter.provider == "gemini" else adapter

    def _hook(self, point: str) -> None:
        if point in self.hooks:
            self.hooks[point]()

    # --- recovery ---------------------------------------------------------------------------------------------
    def recover(self, tick: int) -> None:
        now = time.time()
        with self.store.connection() as db, db:
            for r in ledger.rows(db, self.run_id):
                stale = r["worker"] != self.worker and (r["lease_until"] or 0) < now
                if r["status"] == "dispatching" and stale:
                    ledger.update(db, r["decision_id"], "outcome-unknown", termination="process ended during dispatch; provider outcome unknown; not resent")
                elif r["status"] == "reserved" and stale:
                    ledger.update(db, r["decision_id"], "cancelled-before-dispatch", termination="process ended before dispatch; nothing was sent")
                elif r["status"] == "completed" and r["tick"] < tick:
                    ledger.update(db, r["decision_id"], "expired-unconsumed", termination="world advanced before this response was applied")

    # --- phase A -------------------------------------------------------------------------------------------------
    def prepare(self, state: JSON) -> dict[str, Prepared]:
        if self.profile.mode != "recorded":
            live_guard(self.profile, self.transport)
        self.recover(state["tick"])
        paused = self.store.model_paused(self.run_id)
        prepared: dict[str, Prepared] = {}
        calls_this_tick = 0
        obs_builder = LocalObservations()
        for aid in sorted(self.profile.agents):
            agent = state["agents"].get(aid)
            if agent is None or agent["status"] != "active":
                continue
            obs = obs_builder.build(state, aid)
            obs_hash = digest(obs)
            with self.store.connection() as db:
                agent_rows = ledger.rows(db, self.run_id, aid)
            plan = scheduler.decide(obs, agent_rows, self.profile.scheduler, paused)
            if plan.kind == "offline":
                prepared[aid] = Prepared("offline-policy", plan.reason, obs_hash)
                continue
            if plan.kind == "intent":
                prepared[aid] = Prepared("model-intent-execution", plan.reason, obs_hash, proposal=plan.intent["parsed"],
                                         receipt=plan.intent["receipt"], source=plan.intent["source"], origin=plan.intent["decision_id"])
                continue
            if calls_this_tick >= self.profile.scheduler.max_calls_per_tick:
                prepared[aid] = Prepared("offline-policy", f"deferred: run call cap {self.profile.scheduler.max_calls_per_tick} per tick reached", obs_hash)
                continue
            result = self._deliberate(state, obs, obs_hash, aid, plan.reason)
            calls_this_tick += result.new_calls
            prepared[aid] = result
        return prepared

    def _deliberate(self, state: JSON, obs: JSON, obs_hash: str, aid: str, reason: str) -> Prepared:
        tick = state["tick"]
        ids: list[str] = []
        new_calls = new_tokens = 0
        error: str | None = None
        for attempt, role in ((0, "primary"), (1, "repair")):
            if role == "repair" and (self.profile.repair_limit < 1 or error is None):
                break
            try:
                messages, meta = build_messages(obs, self.profile.adapter.max_input_bytes, repair_error=error if role == "repair" else None)
            except ValueError as exc:
                return Prepared("fallback", f"{reason}; prompt not built: {exc}", obs_hash, decision_ids=ids, new_calls=new_calls, new_tokens=new_tokens)
            prompt_text = "\n\n".join(m["content"] for m in messages)
            identity = ledger.decision_identity(self.run_id, aid, tick, role, attempt, obs_hash, PROMPT_VERSION, ACTION_SCHEMA_VERSION, self.cfg_hash)
            did = ledger.decision_id(identity)
            ids.append(did)
            row = self._obtain(did, identity, aid, tick, role, attempt, ids[-2] if role == "repair" else None, messages, prompt_text, meta)
            if row["source"] != "recorded" and row["status"] not in ("blocked", "cancelled-before-dispatch"):
                # attributed to the committed decision that uses (or falls back on) it, whichever process sent it
                new_calls += 1
                rec = row.get("reconciled") or {}
                new_tokens += int(rec.get("input_tokens") or 0) + int(rec.get("output_tokens") or 0) if rec.get("basis") == "reported" else 0
            status = row["status"]
            if status != "completed":
                why = row.get("fallback") or row.get("termination") or status
                return Prepared("fallback", f"{reason}; {role} request {status}: {why}", obs_hash, decision_ids=ids, new_calls=new_calls, new_tokens=new_tokens)
            if row.get("parse_error"):
                error = row["parse_error"]
                if (row.get("usage") or {}).get("repairable") is False:
                    return Prepared("fallback", f"{reason}; {role} response unusable (no repair attempted): {error}", obs_hash, decision_ids=ids,
                                    new_calls=new_calls, new_tokens=new_tokens)
                continue
            return Prepared("model-proposal", reason + (" (after one repair)" if role == "repair" else ""), obs_hash, proposal=row["parsed"],
                            decision_ids=ids, receipt=row["receipt"], source=row["source"], new_calls=new_calls, new_tokens=new_tokens)
        return Prepared("fallback", f"{reason}; unusable model output after repair limit: {error}", obs_hash, decision_ids=ids,
                        new_calls=new_calls, new_tokens=new_tokens)

    # --- one request -------------------------------------------------------------------------------------------
    def _obtain(self, did: str, identity: JSON, aid: str, tick: int, role: str, attempt: int, parent: str | None,
                messages: list[JSON], prompt_text: str, meta: JSON) -> JSON:
        base = {"decision_id": did, "run_id": self.run_id, "agent": aid, "tick": tick, "role": role, "attempt": attempt, "parent_id": parent,
                "identity": identity, "source": self.source, "endpoint_label": self.profile.endpoint_label, "requested_model": self.profile.adapter.model,
                "prompt": prompt_text, "prompt_hash": digest(messages), "input_bytes": meta["input_bytes"], "truncations": meta["truncations"]}
        with self.store.connection() as db:
            existing = ledger.get(db, did)
        if existing is not None:
            if existing["status"] == "completed":
                return existing                                   # restart: reuse the persisted response, no new call
            if existing["status"] == "reserved" and existing["worker"] != self.worker and (existing["lease_until"] or 0) >= time.time():
                raise DecisionInFlight(f"decision {did[:12]} is reserved by worker {existing['worker']}")
            if existing["status"] == "dispatching":
                if existing["worker"] != self.worker and (existing["lease_until"] or 0) >= time.time():
                    raise DecisionInFlight(f"decision {did[:12]} is being dispatched by worker {existing['worker']}")
                return existing
            if existing["status"] != "cancelled-before-dispatch":
                return existing                                   # failed / unknown / blocked / expired: never resent
        if self.profile.mode == "recorded":
            return self._from_recording(base, existing)
        if contains_secret(prompt_text):
            return self._block(base, existing, "prompt matched a credential pattern; not sent", reexecutable=0)
        with self.store.connection() as db:
            run_rows = ledger.rows(db, self.run_id)
        halt = run_halt(self.profile, run_rows, time.time())
        if halt:
            return self._block(base, existing, halt)
        reserve = budget.reservation(self.profile, meta["input_bytes"])
        over = budget.check(self.profile.run_budget, run_rows, reserve) or budget.check(self.profile.agent_budget, [r for r in run_rows if r["agent"] == aid], reserve)
        if over:
            return self._block(base, existing, f"budget exhausted ({over})")
        inflight = sum(1 for r in run_rows if r["status"] == "dispatching" and (r["lease_until"] or 0) >= time.time())
        if inflight >= self.profile.concurrency:
            return self._block(base, existing, f"concurrency limit {self.profile.concurrency} reached")
        interval = self.profile.adapter.min_dispatch_interval_s
        if interval > 0:
            sent = [r["created_at"] for r in run_rows if r["status"] not in budget.NO_USAGE and r.get("source") != "recorded" and r.get("created_at")]
            wait = min(interval, interval - (time.time() - max(sent))) if sent else 0
            if wait > 0:
                time.sleep(wait)                               # local pacing (wall clock); never inside a transaction
        lease = time.time() + (self.profile.adapter.deadline_ms + self.profile.lease_grace_ms) / 1000
        with self.store.connection() as db, db:
            if existing is None:
                ledger.insert(db, {**base, "status": "reserved", "worker": self.worker, "lease_until": lease, "reservation": reserve})
            else:
                ledger.update(db, did, "reserved", worker=self.worker, lease_until=lease, reservation=reserve)
        self._hook("before-dispatch")
        url, body, headers = self.wire.build_request(messages, self.profile.adapter.model_dump())
        with self.store.connection() as db, db:
            ledger.update(db, did, "dispatching")
        started = time.perf_counter()
        try:
            self._hook("during-dispatch")
            wire = self.transport.send(url, body, headers, self.profile.adapter.deadline_ms / 1000, self.profile.adapter.max_response_bytes)
        except NotDelivered as exc:
            return self._finish(did, "failed-not-delivered", started, termination=scrub(str(exc)),
                                reconciled={"requests": 1, "input_tokens": 0, "output_tokens": 0, "cost_micros": 0, "basis": "not delivered (counts as an attempt)"})
        except OutcomeUnknown as exc:
            return self._finish(did, "outcome-unknown", started, termination=scrub(str(exc)))
        except SimulatedCrash:
            raise
        except Exception as exc:  # noqa: BLE001 -- any other transport failure may have reached the provider
            return self._finish(did, "outcome-unknown", started, termination=scrub(f"{type(exc).__name__}: {exc}")[:300])
        result = self.wire.parse_response(wire.status, wire.body, self.profile.adapter.max_response_bytes)
        if self.wire is gemini:
            return self._complete_gemini(did, started, reserve, result)
        if not result.ok:
            reconciled = {**reserve, "basis": "error response; usage unknown, reservation kept"}
            return self._finish(did, "failed-delivered", started, termination=scrub(result.error or "error")[:300], reconciled=reconciled,
                                returned_model=result.returned_model)
        content = result.content
        reexecutable = 1
        if contains_secret(content):
            content, reexecutable = scrub(content), 0
        parse_error, parsed = None, None
        if reexecutable == 0:
            parse_error = "response contained credential-like content; scrubbed and not used"
        else:
            try:
                parsed = parse_proposal(content, self.profile.adapter.max_output_bytes)
            except ParseError as exc:
                parse_error = str(exc)[:300]
        if result.prompt_tokens is not None and result.output_tokens is not None:
            reconciled = {"requests": 1, "input_tokens": result.prompt_tokens, "output_tokens": result.output_tokens,
                          "cost_micros": budget.cost_micros(self.profile, result.prompt_tokens, result.output_tokens), "basis": "reported"}
        else:
            reconciled = {**reserve, "basis": "estimated (provider did not report usage)"}
        usage = {"prompt_eval_count": result.prompt_tokens, "eval_count": result.output_tokens, "done_reason": result.done_reason}
        row = self._finish(did, "completed", started, response=content, response_hash=digest(content), parsed=parsed, parse_error=parse_error,
                           usage=usage, reconciled=reconciled, returned_model=result.returned_model, termination=result.done_reason,
                           reexecutable=reexecutable)
        self._hook("after-persist")
        return row

    def _complete_gemini(self, did: str, started: float, reserve: JSON, result) -> JSON:
        """Gemini outcome -> ledger row. Usage: generated = candidates + thoughts; cached is part of the prompt count."""
        use = {"provider": "gemini", **{k: v for k, v in result.provider_meta.items() if v is not None}}
        if not result.ok:                                       # an error response was delivered: a definite rejection
            if result.halt:
                use["halt"] = result.halt
            reconciled = {**reserve, "basis": "error response (definite rejection); provider usage not reported, reservation kept conservatively"}
            return self._finish(did, "failed-delivered", started, termination=scrub(result.error or "error")[:300], reconciled=reconciled,
                                usage=use, returned_model=result.returned_model)
        norm = result.usage or {"basis": "missing", "problems": []}
        use["normalized_usage"] = norm
        if norm["basis"] == "reported":
            reconciled = {"requests": 1, "input_tokens": norm["input_tokens"], "output_tokens": norm["output_tokens"],
                          "thinking_tokens": norm["thinking_tokens"], "candidate_tokens": norm["candidate_tokens"],
                          "cached_input_tokens": norm["cached_input_tokens"], "provider_total": norm["provider_total"],
                          "cost_micros": budget.cost_micros(self.profile, norm["input_tokens"], norm["output_tokens"]), "basis": "reported"}
        else:
            def take(k):
                return max(int(norm.get(k) or 0), int(reserve[k]))
            reconciled = {"requests": 1, "input_tokens": take("input_tokens"), "output_tokens": take("output_tokens"),
                          "thinking_tokens": norm.get("thinking_tokens"), "cost_micros": reserve.get("cost_micros"),
                          "basis": f"estimated: provider usage {norm['basis']} ({'; '.join(norm.get('problems') or [])[:160]}); "
                                   "the larger of report and reservation is charged"}
        if any(isinstance(norm.get(k), int) and norm[k] > reserve[k] for k in ("input_tokens", "output_tokens")):
            use["reservation_exceeded"] = True                  # halts further dispatch for this run (run_halt)
        content, parsed, parse_error, reexecutable = result.content, None, None, 1
        if content is None:
            parse_error = (result.error or "no usable text")[:300]
            use["content_error"] = True
            use["repairable"] = bool(result.repairable)
        elif contains_secret(content):
            content, reexecutable = scrub(content), 0
            parse_error = "response contained credential-like content; scrubbed and not used"
            use["repairable"] = False
        else:
            try:
                parsed = parse_proposal(content, self.profile.adapter.max_output_bytes)
            except ParseError as exc:
                parse_error = str(exc)[:300]
                use["repairable"] = True
        row = self._finish(did, "completed", started, response=content, response_hash=digest(content), parsed=parsed, parse_error=parse_error,
                           usage=use, reconciled=reconciled, returned_model=result.returned_model, termination=result.done_reason,
                           reexecutable=reexecutable)
        self._hook("after-persist")
        return row

    def _finish(self, did: str, status: str, started: float, **fields) -> JSON:
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        with self.store.connection() as db, db:
            current = ledger.get(db, did)
            reconciled = fields.pop("reconciled", None)
            if status == "completed":
                tmp = {**current, **fields}
                fields["receipt"] = ledger.receipt({**tmp, "parsed": fields.get("parsed"), "parse_error": fields.get("parse_error")})
            if reconciled is not None:
                reconciled = {**reconciled, "controller_time_ms": int(elapsed)}     # time is known even when tokens are not
            ledger.update(db, did, status, latency_ms=elapsed, reconciled=reconciled, **fields)
            row = ledger.get(db, did)
        row["_dispatched_now"] = True
        return row

    def _block(self, base: JSON, existing: JSON | None, why: str, reexecutable: int = 1) -> JSON:
        with self.store.connection() as db, db:
            if existing is None:
                ledger.insert(db, {**base, "status": "blocked", "fallback": why, "reexecutable": reexecutable, "worker": self.worker})
            else:
                ledger.update(db, base["decision_id"], "blocked", fallback=why)
            return ledger.get(db, base["decision_id"])

    def _from_recording(self, base: JSON, existing: JSON | None) -> JSON:
        source = self.profile.source_run
        with self.store.connection() as db:
            candidates = [r for r in ledger.rows(db, source, base["agent"]) if r["tick"] == base["tick"] and r["role"] == base["role"]
                          and r["attempt"] == base["attempt"] and r["identity"]["observation_hash"] == base["identity"]["observation_hash"]
                          and r["prompt_hash"] == base["prompt_hash"] and r["identity"]["config_hash"] == self.cfg_hash
                          and r["status"] in ("consumed", "completed") and r["reexecutable"]]
        if len(candidates) != 1:
            why = "no matching recording" if not candidates else "ambiguous recordings"
            if self.profile.recorded_miss == "stop":
                raise RecordingMismatch(f"{why} for agent {base['agent']} tick {base['tick']} {base['role']}")
            return self._block(base, existing, f"strict recorded mode: {why} (declared fallback)")
        src = candidates[0]
        row = {**base, "status": "completed", "recorded_from": src["decision_id"], "response": src["response"], "response_hash": src["response_hash"],
               "parsed": src["parsed"], "parse_error": src["parse_error"], "usage": src["usage"], "returned_model": src["returned_model"],
               "reconciled": {**(src.get("reconciled") or {}), "basis": f"historical (recorded in run {source}); not new usage"},
               "termination": "re-used recording", "worker": self.worker}
        row["receipt"] = ledger.receipt(row)
        with self.store.connection() as db, db:
            ledger.insert(db, row)
            return ledger.get(db, base["decision_id"])
