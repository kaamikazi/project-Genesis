# M6 handoff: one model-backed controller under budgets

> **Status at v0.6.0:** steps 1–7 below are implemented and verified with fixtures and mocked transport (see [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md) and [ADR-008](ADR-008-model-controller-boundary.md)). Step 8 and the three decisions at the end are still open; the disabled template and [LIVE_RUN_CHECKLIST](LIVE_RUN_CHECKLIST.md) describe what a first live run needs. The text below is the handoff as written at v0.5.2.

M5c closes the offline search-tuning cycle. M6 integrates a model-backed controller behind the interfaces that already exist. Most of the work, including the adapter, recording, budgets, replay and tests, can be built and tested with **recorded fixtures and a fake provider, without any paid call**. A live provider is needed only for the final exploratory runs, and only after you choose a provider and set a budget.

## What already exists

| Piece | Where | What M6 can rely on |
|---|---|---|
| Controller interface | `genesis/models.py` `AgentController.propose(observation) -> Action` | One call per active agent per tick. The engine validates every action; a rejected action changes nothing. |
| Restricted observation | `genesis/world.py` `LocalObservations.build` | An explicit allow-list: own state, local tiles, sites, neighbours, own and accessible artifacts (programs only when held), own sessions, declared rules, and, under cohorts, the public schedule. It never includes configs, seeds, hidden parameters, validation scores, selection or sealed data (tested). |
| Action contract | `genesis/models.py` `Action`, `genesis/engine.py` `PARAMS` / `OPTIONAL_PARAMS` | Strict Pydantic. Every kind is listed with its parameters, including `withdraw_artifact` and the compare-and-swap `reference` on `submit_artifact`. |
| Explicit failure path | `genesis/engine.py` `advance` | A controller exception becomes a `controller_failure` event and an `explicit-failure-fallback` wait, never a silent success. Counted in `metrics.controller_failures`. |
| Decision records | tick records (`decisions[]`) | The action, the observation hash, the controller mode, and an optional `diagnostic` (no wall time; non-finite numbers removed). |
| Metric slots | `state.metrics.model_calls`, `tokens`, `cost_usd` | Present and zero today; the reducer and observer can report them. |
| Budgets | `SearchBudget` (credits), `Scenario.search_budget` | A per-lifetime action budget. There is no token or price budget yet. |
| Replay | `genesis/storage.py` | Replay applies recorded deltas and never re-invokes controllers, so model output is not needed to replay a run. |
| Continuation and forks | `Store.step`, `Store.fork`, `import_run` | Deterministic continuation, as long as the controller is deterministic given its recorded inputs. |
| Restart | WAL SQLite, hash-chained records | Verified at every milestone: a reopened run continues identically. |
| Reference controller | `genesis/controllers.py` `OfflineController` | Keeps working as the comparison baseline and as the fallback. |

## Integration work remaining

1. **Provider adapter** behind `AgentController`.
   - It turns an observation into a prompt and parses the response into one `Action`.
   - Schema-invalid or unparseable output goes to a bounded repair attempt, then the explicit fallback.
   - It holds no hidden state that bypasses the observation boundary.
2. **Call recording and redaction.**
   - Store the prompt, response, model id, parameters, latency and token counts per call, keyed by the decision's observation hash.
   - Keep these in a sidecar store, not in world state.
   - Redact credentials, and check that prompts contain nothing outside the observation allow-list.
3. **Budget manager for model use.**
   - Per-run and per-agent limits on calls, tokens, wall time and price.
   - Failures and repair calls are charged too.
   - When a limit is reached, the agent falls back to `OfflineController`, explicitly and recorded.
   - Fill `metrics.model_calls`, `tokens` and `cost_usd`.
4. **Deterministic re-execution from recordings.**
   - A `RecordedController` replays stored responses by observation hash, for continuation, forks and tests without calls.
   - A mismatched observation hash is an explicit error.
5. **Fixture-based tests, no paid calls.** Using a fake provider and recorded fixtures:
   - schema validation and parse failures;
   - repair limits and budget exhaustion;
   - fallback labelling and redaction;
   - the observation boundary: no config, seed or score leaks into prompts;
   - replay from recordings, copy-on-write equivalence, and reducer reconciliation with model metrics.
6. **Separate simulation skill from pretrained knowledge.**
   - Keep the restricted observation as the only world input.
   - Report model runs as a separate controller condition, never pooled with offline results.
7. **Observer.**
   - Controller mode per agent; calls, tokens and cost against budget; and failure or fallback events.
8. **Exploratory evaluation, only after a provider and budget are chosen.**
   - Reuse the M5c paired manifests and the selection-panel / sealed-final protocol.
   - Run the model controller as one fixed condition beside first-improvement and repaired beam, with a fresh final-case commitment.

## Needs your decision

- **Provider and model.**
- **Total spend limit, plus per-run and per-agent caps.**
- **Whether exploratory model runs may be published in the repository evidence.** Prompts and responses could be large; storage needs to be planned.

None of this blocks steps 1–7.
