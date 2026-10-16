# Implementation status, v0.6.0 / M6 (2026-10-16)

Engine `0.6.0` · rules `phase-world-5.2` (unchanged) · evaluators unchanged · prompt `genesis-prompt-1` · action schema `genesis-action-schema-1` · parser `genesis-parser-1` · adapter `ollama-chat-1` · reducer `genesis.reducer/3` · metrics `genesis-metrics-1`.

- **Evidence:** [`evidence/v0.6.0/`](../../evidence/v0.6.0/README.md)
- **Decisions:** [ADR-008](../ADR-008-model-controller-boundary.md)
- **Before a live run:** [LIVE_RUN_CHECKLIST](../LIVE_RUN_CHECKLIST.md) and the disabled template [`config/live-run.disabled.json`](../../config/live-run.disabled.json)
- **Previous status:** [v0.5.2](IMPLEMENTATION_STATUS-v0.5.2.md), [v0.5.1](IMPLEMENTATION_STATUS-v0.5.1.md), [v0.5.0](IMPLEMENTATION_STATUS-v0.5.0.md), [v0.4.0](IMPLEMENTATION_STATUS-v0.4.0.md). All earlier releases and their evidence are unchanged.

## Four separate claims

| Claim | Status |
|---|---|
| **Integration implemented** | Yes: model-controller boundary, event-driven scheduler, durable request ledger, budgets, explicit fallback, three replay modes, observer views |
| **Fixture verified** | Yes: 39 new tests and 11 evidence scenarios, using an in-process fixture transport and a loopback mock server that speaks the Ollama `/api/chat` wire format |
| **Live transport exercised** | **No.** No provider endpoint was contacted, no credential was used, and no model weights were downloaded. |
| **Live agent behaviour demonstrated** | **No.** Every model-shaped response so far came from a scripted fixture policy, which says nothing about model competence. |

The search-tuning cycle stays closed: M6 changed no world rule, evaluator or offline policy.

## Verification

| Check | Result |
|---|---|
| Baseline before any change (tag v0.5.2) | 165 passed, build OK |
| `python -m pytest -q` | **204 passed** (39 new in `tests/test_v060.py`) |
| `npm run build` (with `tsc --noEmit`) | Succeeded |
| Runs without a model profile | **Unchanged.** A phase-1 world and a workshop-1 world with cohorts and teaching, 120 ticks each, give identical final-state and tick-record hashes under tag v0.5.2 and under v0.6.0 (`offline-parity.json`). Copy-on-write equivalence also holds with model inhabitants. |
| `python tools/generate_evidence_m6.py` | All 5 steps exited 0 from runtime commit `dccd1c3`, clean at start and end; 11 of 11 scenarios passed; tests and build re-run inside the pipeline (204 passed) |
| Observer | Model panel checked in the browser at desktop and 375 px widths (tables scroll inside their panels; no page overflow); sanitized transcript view works |

## What was built

| Capability | Where | Tests |
|---|---|---|
| Strict output contract: one JSON object, known kind, exact parameters, bounded strings, finite numbers, no extra fields, no identity | `genesis/model/schema.py` | `test_parser_*` |
| Prompts from versioned instructions + restricted observation (escaped data block) + schema + bounded memory; deterministic, recorded truncation | `genesis/model/prompt.py` | `test_prompts_*`, `test_untrusted_text_*` |
| Ollama `/api/chat` adapter (non-streamed); structured outputs as a declared capability; reasoning fields discarded; usage and done reason parsed | `genesis/model/adapter.py`, `transport.py` | `test_ollama_adapter_*`, `test_structured_outputs_*`, `test_http_errors_*`, `test_oversized_*` |
| Durable ledger with lifecycle validation, leases, stable decision identity and receipts | `genesis/model/ledger.py` | `test_repeated_observations_*`, crash tests |
| Budgets per run and per agent with reservation before dispatch; committed / pending / uncertain / historical; paid mode fails closed | `genesis/model/budget.py`, `profile.py` | `test_budget_exhaustion_*`, `test_live_mode_and_paid_mode_fail_closed` |
| Event-driven scheduler and standing intents | `genesis/model/scheduler.py` | `test_scheduler_does_not_call_on_every_tick` |
| Two-phase step: I/O outside the write transaction, pure controller inside it, consumption committed with the tick | `genesis/model/runtime.py`, `controller.py`, `genesis/storage.py` | `test_restart_*`, `test_crash_*`, `test_possible_dispatch_*`, `test_competing_workers_*` |
| State replay, decision re-execution, strict recorded continuation | `genesis/model/recorded.py`, `runtime.py` | `test_state_replay_*`, `test_reexecution_*`, `test_strict_recorded_fork_*` |
| Reducer reconciliation of decisions, calls, tokens and receipts | `genesis/reducer.py` | `test_reducer_reconciles_*` |
| Observer: modes, scheduler reasons, model identity, fixture/recorded/live indicator, budgets, request states, parse failures, repairs, fallbacks, transcripts, receipts, pause, latency separate from simulation speed | `genesis/model/observer.py`, `genesis/api.py`, `frontend/src/ModelPanel.tsx` | `test_api_exposes_*` |

## Fixture integration run (scripted; not model behaviour)

Seed 101, `workshop-1`, 120 ticks, inhabitants a01 and a05 model-backed through the loopback mock server; the other six use the offline controller. The fixture was scripted to return one invalid JSON reply, one illegal action and one HTTP 500.

| Measure | Value |
|---|---|
| Provider requests | 46 (one per 5.4 ticks per model agent; minimum gap 5 ticks, as configured) |
| Model agents' decisions | 44 model proposals · 38 standing-intent executions · 157 offline-policy decisions · 1 fallback (after the HTTP 500) |
| Ledger | 45 consumed · 1 failed-delivered; nothing pending or uncertain |
| Reducer | Decisions, calls (46) and tokens reconcile with the ledger and the world metrics; no missing, double-referenced or unconsumed receipts |
| Decision re-execution | 82 of 82 model decisions matched |

Most of a model agent's turns are offline-policy turns by design: the scheduler only calls between `min_interval` ticks when a trigger fires and otherwise lets the standing intent or the offline policy act. Each decision says which.

## Known limitations

- **No live evidence.** Latency, token counts, parse-failure rates and behaviour of a real model are unknown.
- **Token reservation** uses prompt bytes as an upper bound for input tokens; it over-reserves for typical tokenizers.
- **Uncertain outcomes need an operator.** Ollama has no idempotency key or status lookup, so an `outcome-unknown` request keeps its reservation and pauses that agent until resolved.
- **One protocol.** No streaming, no tool calls, no hosted-provider credential mechanism, no prices.
- **Controller time** is measured in whole milliseconds; fixture calls round to 0.
- **Evidence size:** 0.49 MB in total (the gzipped integration export is 0.42 MB).
