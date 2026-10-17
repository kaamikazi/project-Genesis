# Live-run checklist

Performed for Gemini on 2026-10-17 (two smoke runs; see [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)). Complete it again, and get the owner's explicit authorization, before every further live run.

- **Gemini (selected route, v0.6.1):** template [`config/gemini-smoke.disabled.json`](../config/gemini-smoke.disabled.json), setup and the exact commands in [GEMINI_SETUP](GEMINI_SETUP.md). Section 0 below applies in addition to sections 1–4.
- **Ollama:** template [`config/live-run.disabled.json`](../config/live-run.disabled.json).

Both templates refuse to run as shipped (verified in `evidence/v0.6.0/live-disabled.json` and `evidence/v0.6.1/guards.json`).

## 0. Gemini-specific confirmations (the owner, in AI Studio)

- [ ] The project behind the key is on the **free tier with billing disabled**. A local `paid: false` does not change how Google bills a project. If the tier is unknown or billed, stop here.
- [ ] `gemini-3.5-flash-lite` is **available** to that project (recheck the models page; do not substitute another model silently).
- [ ] The project's current **RPM / TPM / RPD** quota covers 10 requests; `min_dispatch_interval_s` is set from it.
- [ ] Only **simulation data** is sent, and free-tier content may be used to improve Google's products (pricing page).
- [ ] The key is entered for **one PowerShell session** only (GEMINI_SETUP), never into a file in the repository.
- [ ] All six `operator_confirmations` fields are filled in the local copy, which lives in `data/` and is not committed.

## 1. Decisions only the owner can make

- [ ] **Endpoint.** A local Ollama server (loopback, no credentials) or a hosted endpoint. For hosted endpoints a credential mechanism exists only for Gemini (`GEMINI_API_KEY`, read at dispatch, header only, never stored); any other hosted provider would need its own.
- [ ] **Exact model** name and tag, and whether its server supports structured outputs (set `structured_outputs` accordingly; Ollama's cloud models are documented without it).
- [ ] **Explicit authorization** for this run: who authorized it, when, and for which profile hash.
- [ ] **Limits.** Per-run and per-agent requests, input tokens, output tokens and controller time; concurrency (start with 1); `max_calls_per_tick`; deadline.
- [ ] **Money.** Local inference: `paid: false`, no prices. Paid endpoint: `paid: true`, a `pricing` block (currency, pricing version and source date, integer micro-units per million input and output tokens) and a `cost_micros` ceiling. Never invent a price.
- [ ] **Transcript publication.** Whether prompts and responses from live runs may be committed to the repository evidence, published only as hashes and summaries, or kept local. Default: local only (`data/`, git-ignored); the launcher's report contains no prompts, responses or keys.

## 2. Before the run

- [ ] `python -m pytest -q` passes on the commit that will run.
- [ ] Copy the template to a local, uncommitted file; fill in endpoint label, model, limits; set `live_authorized: true`.
- [ ] Confirm the endpoint is reachable by the operator by other means (GENESIS does not probe it).
- [ ] Record the commit, the profile's `config_hash` and the limits in the run notes.

## 3. Smoke scenario (smallest useful run)

- One model-backed agent (`a01`), seed 101, `workshop-1`, 40 ticks, `min_interval` 5, `max_calls_per_tick` 1, at most 20 requests (Ollama template) or 10 requests including repairs (Gemini template: 200,000 input and 10,240 generated tokens, 1,024 per request, 20 s per request, 900 s run deadline).
- Set `GENESIS_LIVE_MODEL_CALLS=1` only in the shell that runs it, and unset it afterwards.
- Expected evidence: ledger status counts, decisions by mode, parse failures and repairs, fallbacks with reasons, token totals against the reservation, latency, reducer model reconciliation, and decision re-execution (all matched).

## 4. After the run

- [ ] Any `outcome-unknown` rows are resolved by the operator (`POST /api/runs/{id}/model/resolve`) or left documented.
- [ ] Report live transport exercised and live agent behaviour demonstrated as separate claims, with the actual numbers; never pool model runs with offline results.
- [ ] Publish transcripts only as decided in section 1.
