# ADR-009: Gemini Developer API adapter (v0.6.1)

Status: accepted, 2026-10-17. Implemented and verified with fixtures and a loopback mock only; no live request has been made.

## Context

The owner selected Google AI Studio (the Gemini Developer API) as the available inference route. The M6 boundary (ADR-008) must stay intact: an authoritative engine, restricted observations, event-driven deliberation, reservations before dispatch, no blind resends, explicit fallback labels and three separate replay modes. Ollama and fixture support remain.

## Decisions

1. **One native contract: stateless `generateContent` (v1beta).** Each decision is one self-contained request with no previous-interaction id, cached content or server-side conversation. The Interactions API, which the current guides feature, is not used, and its field names and usage formats are never mixed in.
2. **JSON output via `generationConfig.responseFormat.text`** (`mimeType: APPLICATION_JSON`, `schema`). The reference marks `responseSchema` and `_responseJsonSchema` deprecated in favour of `responseFormat`.
3. **A versioned wire schema** (`genesis-gemini-wire-1`) inside the documented subset. It has no `maxLength` and no per-kind parameter sets. The local strict parser keeps the full `genesis-action-schema-1` contract, so nothing is weakened; the schema constrains format, never legality.
4. **Thinking at `MINIMAL` with `includeThoughts: false`.** For `gemini-3.5-flash-lite` thinking cannot be switched off (default "on (minimal)"). Thought parts that arrive anyway are dropped before storage. Thinking tokens are reported separately and counted once, inside generated output.
5. **The credential lives only in the transport.** `GeminiTransport` reads `GEMINI_API_KEY` at send time and attaches `x-goog-api-key` only for the exact official origin and generateContent path with no query string. It never follows redirects (urllib's default handler would forward the header) and never retries. Tests use `GeminiTransport.for_loopback_test`, which can only target loopback.
6. **Conservative usage.** Generated tokens are reserved at `maxOutputTokens`. Missing or inconsistent usage is charged at the larger of report and reservation. A response that reports more than its reservation halts dispatch for the run, because the `generateContent` reference does not state that `maxOutputTokens` bounds thinking.
7. **Quota is a stop condition.** HTTP 429 / `RESOURCE_EXHAUSTED` halts dispatch for the run, with no retry, key rotation, project switch or paid fallback. Local wall-clock pacing (`min_dispatch_interval_s`) is set from the project's real quota.
8. **Free tier is an operator-confirmed condition.** A live Gemini profile must use the official origin, cannot be paid, needs four operator confirmations plus a name and date, and needs a finite wall-clock run deadline. This is in addition to `live_authorized` and `GENESIS_LIVE_MODEL_CALLS=1`. No zero prices are inserted.
9. **Config hashes stay backward compatible.** Ollama profiles hash exactly as in v0.6.0, so existing recordings and identities still match. Gemini hashes include the adapter and wire-schema versions and exclude the endpoint address and pacing.

## Consequences

- An unconfirmed property of the live API (schema acceptance, whether thinking counts against the output limit, real latency, real quota) shows up in the smoke run as a labelled failure or halt, not as a silent success.
- The engine version becomes 0.6.1, so v0.6.0 runs are read-only and still replay. Offline worlds are unchanged.
- Not built: paid Gemini service, streaming, the Interactions API, tools or grounding, Vertex AI, and multi-key handling.
