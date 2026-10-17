# Implementation status, v0.6.1 / M6a (2026-10-17)

Engine `0.6.1` · rules `phase-world-5.2` (unchanged) · prompt `genesis-prompt-1` · action schema `genesis-action-schema-1` · parser `genesis-parser-1` · adapters `ollama-chat-1`, `gemini-generatecontent-1` · Gemini wire schema `genesis-gemini-wire-1`.

- **Evidence:** [`evidence/v0.6.1/`](../../evidence/v0.6.1/README.md)
- **Decisions:** [ADR-009](../ADR-009-gemini-adapter.md) (Gemini), [ADR-008](../ADR-008-model-controller-boundary.md) (M6 boundary)
- **Setup and activation:** [GEMINI_SETUP](../GEMINI_SETUP.md), [LIVE_RUN_CHECKLIST](../LIVE_RUN_CHECKLIST.md), template [`config/gemini-smoke.disabled.json`](../../config/gemini-smoke.disabled.json)
- **Previous status:** [v0.6.0](IMPLEMENTATION_STATUS-v0.6.0.md), [v0.5.2](IMPLEMENTATION_STATUS-v0.5.2.md), [v0.5.1](IMPLEMENTATION_STATUS-v0.5.1.md), [v0.5.0](IMPLEMENTATION_STATUS-v0.5.0.md), [v0.4.0](IMPLEMENTATION_STATUS-v0.4.0.md)

## Four separate claims

| Claim | Status |
|---|---|
| **Gemini integration implemented** | Yes: native stateless `generateContent` adapter, backend-only `GEMINI_API_KEY`, origin pinning without redirects, thinking-aware usage, quota, overshoot and deadline halts, local pacing, operator free-tier confirmations, observer fields, a disabled smoke template and launcher |
| **Mock verified** | Yes: 38 new tests (242 total), a 22-case fault matrix over loopback HTTP, guard, recovery and replay checks, and a rehearsal of the exact smoke template against a mock server. Only synthetic keys were used. |
| **Live transport exercised** | **No.** Zero requests were sent to Google, and no key was read or used. |
| **Live agent behaviour demonstrated** | **No.** All Gemini-shaped responses so far are scripted fixtures. |

## Verification

| Check | Result |
|---|---|
| Baseline before any change (tag v0.6.0, HEAD `be44382`) | 204 passed (reported), build OK |
| `python -m pytest -q` | **242 passed** (204 earlier + 38 new in `tests/test_v061.py`) |
| `npm run build` | Succeeded |
| Offline worlds | Identical state and tick-record hashes under v0.6.0 and v0.6.1 (`offline-parity.json`) |
| Ollama path | All 39 v0.6.0 tests unchanged and passing. v0.6.0 Ollama config hashes recompute exactly, so existing recordings and identities still match. |
| Observer | Checked in the browser with a Gemini-format fixture run: provider and model in the header, halt banner after a 429, thinking tokens per request and in total, "not sent" for blocked rows; no console errors; no page overflow at 375 px |
| `python tools/generate_evidence_m6a.py` | All 7 steps exited 0 from runtime commit `ed3f5a7`, clean at start and end; pytest and build re-run inside the pipeline; the synthetic key appears nowhere in the evidence (53 KB) |

## What was built

| Capability | Where | Tests (`tests/test_v061.py`) |
|---|---|---|
| Native request envelope: `systemInstruction`, one user turn, `candidateCount: 1`, `maxOutputTokens`, `responseFormat.text` JSON with the wire schema, `thinkingConfig` MINIMAL without thoughts, `store: false`; no Ollama fields, tools or caches | `genesis/model/gemini.py` | `test_request_envelope_*` |
| Wire schema inside the documented subset; the full internal contract still enforced locally | `gemini.wire_schema`, `schema.parse_proposal` | `test_wire_schema_*` |
| Response classification: blocked prompt, no candidates or several, safety and other stops, `MAX_TOKENS`, non-text parts, empty text, thought parts dropped | `gemini.parse_response` | `test_unusable_candidates_*`, `test_thought_parts_*` |
| Usage: input = prompt (+ tool use), output = candidates + thoughts, cached reported but not added, total checked; bad reports charged at the reservation or more | `gemini.normalize_usage`, `runtime._complete_gemini` | `test_usage_*`, `test_missing_or_inconsistent_usage_*`, `test_reported_usage_*` |
| Halts: 429 / `RESOURCE_EXHAUSTED`, usage above its reservation, wall-clock run deadline | `runtime.run_halt` | `test_http_429_*`, `test_usage_above_*`, `test_run_wall_clock_deadline_*` |
| Budgets across repairs, per run and per agent; output reservation before dispatch; local pacing | `runtime._obtain`, `budget` | `test_request_ceiling_*`, `test_output_token_ceiling_*`, `test_local_pacing_*` |
| Credentials: key read at send time, header only, official origin and path only, no redirects, concise missing-key error, scrubbed errors, never in records, observations or API output | `transport.GeminiTransport`, `runtime.scrub` | `test_missing_key_*`, `test_key_travels_only_*`, `test_error_text_*`, `test_transport_pins_*`, `test_redirects_*` |
| Live guard: authorization, env switch, four operator confirmations plus name and date, finite deadline, no paid mode, official origin | `runtime.live_guard`, `profile` | `test_live_gemini_needs_*`, `test_smoke_template_*` |
| Crash after possible dispatch, saved-response reuse, repeated observations, state replay without network, re-execution, tamper detection, strict recorded fork | unchanged M6 machinery with Gemini recordings | `test_crash_*`, `test_saved_*`, `test_repeated_*`, `test_state_replay_*`, `test_reexecution_*`, `test_recorded_fork_*` |
| Observer: provider, model, halt, thinking and cached tokens, finish reasons | `observer.summary`, `frontend/src/ModelPanel.tsx` | `test_observer_reports_*` |
| Bounded smoke launcher: `show`, `rehearse` and `live` (hash-checked, fresh database only, never resumed) | `tools/gemini_smoke.py` | rehearsal evidence |

## Known limitations

- **Thinking vs `maxOutputTokens`.** The `generateContent` reference does not state that `maxOutputTokens` bounds thinking tokens. GENESIS halts after the first response that exceeds its reservation, so one response can overshoot before the stop.
- **Schema acceptance** by the live endpoint is unverified. A rejection would show as HTTP 400 `failed-delivered`; changing `structured_outputs` is then an operator decision.
- **Quota and tier** are not observable before a request. The project's real limits must be read in AI Studio; the 15 s pacing in the template is a placeholder.
- **`store: false`** is a logging preference sent with each request. It is not a guarantee about Google's retention, and free-tier content may be used to improve Google's products.
- **Definite rejections** (HTTP 4xx/5xx) keep their token reservation as committed usage, because the provider reports none. This is conservative.
- Not built: paid Gemini service, the Interactions API, streaming, tools, Vertex AI.
