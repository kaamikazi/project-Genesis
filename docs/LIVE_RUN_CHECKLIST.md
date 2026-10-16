# Live-run checklist (not yet performed)

No live model call has been made in GENESIS. This checklist must be completed, and the owner must authorize the run explicitly, before the first one. The template is [`config/live-run.disabled.json`](../config/live-run.disabled.json); it refuses to run as shipped (verified in `evidence/v0.6.0/live-disabled.json`).

## 1. Decisions only the owner can make

- [ ] **Endpoint.** A local Ollama server (loopback, no credentials) or a hosted endpoint. A hosted endpoint needs a credential mechanism that is not implemented yet: credentials must come from the environment at call time and are never stored in profiles, ledgers or exports.
- [ ] **Exact model** name and tag, and whether its server supports structured outputs (set `structured_outputs` accordingly; Ollama's cloud models are documented without it).
- [ ] **Explicit authorization** for this run: who authorized it, when, and for which profile hash.
- [ ] **Limits.** Per-run and per-agent requests, input tokens, output tokens and controller time; concurrency (start with 1); `max_calls_per_tick`; deadline.
- [ ] **Money.** Local inference: `paid: false`, no prices. Paid endpoint: `paid: true`, a `pricing` block (currency, pricing version and source date, integer micro-units per million input and output tokens) and a `cost_micros` ceiling. Never invent a price.
- [ ] **Transcript publication.** Whether prompts and responses from live runs may be committed to the repository evidence, published only as hashes and summaries, or kept local.

## 2. Before the run

- [ ] `python -m pytest -q` passes on the commit that will run.
- [ ] Copy the template to a local, uncommitted file; fill in endpoint label, model, limits; set `live_authorized: true`.
- [ ] Confirm the endpoint is reachable by the operator by other means (GENESIS does not probe it).
- [ ] Record the commit, the profile's `config_hash` and the limits in the run notes.

## 3. Smoke scenario (smallest useful run)

- One model-backed agent (`a01`), seed 101, `workshop-1`, 40 ticks, `min_interval` 5, `max_calls_per_tick` 1, at most 20 requests.
- Set `GENESIS_LIVE_MODEL_CALLS=1` only in the shell that runs it, and unset it afterwards.
- Expected evidence: ledger status counts, decisions by mode, parse failures and repairs, fallbacks with reasons, token totals against the reservation, latency, reducer model reconciliation, and decision re-execution (all matched).

## 4. After the run

- [ ] Any `outcome-unknown` rows are resolved by the operator (`POST /api/runs/{id}/model/resolve`) or left documented.
- [ ] Report live transport exercised and live agent behaviour demonstrated as separate claims, with the actual numbers; never pool model runs with offline results.
- [ ] Publish transcripts only as decided in section 1.
