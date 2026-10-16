# Gemini Developer API: adapter, setup and the bounded smoke run

Status (v0.6.1): **implemented and verified with mocks only. No request has been sent to Google from this project.**

## The adapter (`genesis/model/gemini.py`, `gemini-generatecontent-1`)

Official documentation consulted on **2026-10-17**:
[models](https://ai.google.dev/gemini-api/docs/models),
[gemini-3.5-flash-lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
[API keys](https://ai.google.dev/gemini-api/docs/api-key),
[generateContent reference](https://ai.google.dev/api/generate-content),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output),
[thinking](https://ai.google.dev/gemini-api/docs/thinking),
[pricing](https://ai.google.dev/gemini-api/docs/pricing),
[rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

| Item | Choice |
|---|---|
| Contract | `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, non-streamed, one self-contained request per decision. The Interactions API is not used and its field names are never mixed in. |
| Dependency | Python standard library (`urllib`); no SDK, so no hidden retries. |
| Request | `systemInstruction` = versioned instructions; `contents[0]` = the restricted observation data block; `generationConfig`: `candidateCount: 1`, `maxOutputTokens`, `temperature`, `responseFormat.text {mimeType: APPLICATION_JSON, schema}`, `thinkingConfig {thinkingLevel: MINIMAL, includeThoughts: false}`; `store: false` (a request-level logging preference, not a promise about Google's retention). No tools, grounding, code execution, retrieval, uploads, cached content or safety overrides. |
| Credential | `x-goog-api-key` header, read from `GEMINI_API_KEY` by `GeminiTransport` at dispatch time, attached only for the exact origin and `/v1beta/models/…:generateContent` path with no query string. Redirects are never followed. The key never enters profiles, hashes, ledgers, prompts, observations, exports, API responses, logs or Git. GENESIS reads only `GEMINI_API_KEY` (not `GOOGLE_API_KEY`). |
| Wire schema | `genesis-gemini-wire-1`: kind enum, `params` object, optional `explanation` and `standing`, no extra top-level fields. The documented subset has no `maxLength` and per-kind parameter sets are not expressed, so the strict local parser still enforces the full `genesis-action-schema-1` contract. Structured output constrains format, not legality: the engine judges every action. There is no restricted action subset for the smoke run. |
| Response handling | Only non-thought text parts of the single candidate reach the parser; thought parts and signatures are dropped and never stored. Blocked prompts, missing or multiple candidates, safety/recitation stops, `MAX_TOKENS` truncation, non-text parts and unknown finish reasons are recorded and become labelled fallbacks without a repair. Malformed JSON or empty text gets at most one repair. |
| Usage | `promptTokenCount` (+ tool-use prompt) = input; `candidatesTokenCount + thoughtsTokenCount` = generated output (both billed as output); `cachedContentTokenCount` is reported but already inside the prompt count; `totalTokenCount` is checked against the documented sum. Missing, non-integer, non-finite or inconsistent counts are charged at the larger of report and reservation. |
| Errors | HTTP 429 / `RESOURCE_EXHAUSTED` stops all model dispatch for the run (no retry, no key or project switch). Other error responses are definite rejections (`failed-delivered`, reservation kept). Timeouts and resets after possible delivery are `outcome-unknown`: never resent, reservation kept, operator resolution required. |
| Pacing | `min_dispatch_interval_s` spaces dispatches in wall-clock time; set it from your project's actual quota. Simulation ticks are not a rate limit. |

### Known limits (not hidden)

- **Thinking and `maxOutputTokens`.** The Interactions guide says its output limit includes thought tokens; the `generateContent` reference does not say so. GENESIS reserves `maxOutputTokens` for all generated tokens and, if a response reports more, records `reservation_exceeded` and stops dispatch for the run. One response could therefore exceed its reservation before the stop.
- **Wire schema acceptance.** Whether the live endpoint accepts this schema for this model has not been exercised. A rejection appears as an HTTP 400 `failed-delivered` row and a fallback; the remedy (for example `structured_outputs: false`, which sends JSON mode without a schema) is an operator decision.
- **Input tokens** are reserved as prompt bytes, an upper bound for typical tokenizers but not a provider guarantee.
- **Quota and tier** are properties of your Google project. The public model list establishes neither.

## What only you can confirm (free tier)

A local `paid: false` cannot make Google treat a billed project as free. Before a live run, confirm in AI Studio:

1. The project behind your key is on the **free tier with billing disabled**.
2. `gemini-3.5-flash-lite` is **available** to that project.
3. The current **RPM / TPM / RPD** quota covers 10 requests within the run (and set `min_dispatch_interval_s` accordingly; the template's 15 s is a cautious placeholder).
4. You accept that **only simulated-world data** is sent. Google's pricing page states that free-tier content is used to improve Google's products.

If the project is billed or its tier is unknown, leave live execution disabled.

## Windows setup (PowerShell, this session only)

Never put the key in a file inside the repository. Enter it for one PowerShell session without echoing it:

```powershell
$s = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $s).Password
Remove-Variable s
```

`Read-Host` input is not written to PowerShell history. When the run has finished, close the window or remove the variables:

```powershell
Remove-Item Env:GEMINI_API_KEY, Env:GENESIS_LIVE_MODEL_CALLS -ErrorAction SilentlyContinue
```

A persistent user environment variable (System Properties → Environment Variables) also works, but GENESIS never needs it outside the run; the session-only form keeps it from every other process.

## Activation (after the checklist)

1. Copy the template to the git-ignored `data/` folder and edit only the copy:
   ```powershell
   Copy-Item config\gemini-smoke.disabled.json data\gemini-smoke.local.json
   ```
   In the copy set `live_authorized: true`, fill all six `operator_confirmations` fields, and set `min_dispatch_interval_s` from your quota.
2. Review what will run (contacts nothing):
   ```powershell
   .venv\Scripts\python tools\gemini_smoke.py show --config data\gemini-smoke.local.json
   ```
   Check the model, limits and `profile_hash`; `missing_confirmations` must be empty.
3. Optional rehearsal of the same profile against a loopback mock (synthetic key, no network):
   ```powershell
   .venv\Scripts\python tools\gemini_smoke.py rehearse --config data\gemini-smoke.local.json --db data\gemini-rehearsal.sqlite
   ```
4. The live run (one command, in the session where the key was entered):
   ```powershell
   $env:GENESIS_LIVE_MODEL_CALLS = "1"; .venv\Scripts\python tools\gemini_smoke.py live --config data\gemini-smoke.local.json --db data\gemini-smoke-1.sqlite --profile-hash <profile_hash from step 2>
   ```
   It refuses to start if any guard fails, if the hash differs, or if the database path already exists (an ended run is never resumed or repeated automatically). It stops on the first 429, on a reservation overshoot, at the request ceiling, or at the wall-clock deadline.
5. The sanitized report (no prompts, responses or key) is written next to the database as `data\gemini-smoke-1.report.json`. Transcripts stay in the local SQLite file; `data/` is excluded from Git.
