# Agent model

An agent is a persistent identity plus state. A controller is attached to it, proposes actions, and never mutates anything itself.

## Persistent state (per agent)

`id`, `name`, `home`, `created_tick`, `status` (`active` / `inactive` / `retired`), position, `energy`, `inventory`, `capabilities`, `role` (`researcher` / `producer`), `goals`, `plan`, `search_count`.

Knowledge fields:

- `known`: artifacts whose AST this agent holds.
- `seen`: artifacts it inspected.
- `used`: artifacts it executed.

Social fields:

- `relationships`: counts of interactions received.
- `messages`: the last 8.
- `beliefs`: the last 8 message claims, each with its source event, `confidence: "unverified"` and a revision number.

History fields:

- `memories`: the last 16 action results, each the agent's own accepted or rejected event.
- `last_result`

All of this lives in the committed state, so it survives restart, replay and export. Identity is unaffected by which controller is attached.

## Observations: what a controller can see

`LocalObservations.build(state, agent_id)` returns only:

- the tick, the agent's own state, and the phase at its own tile
- a per-agent `controller_seed` derived from the world seed. It is never the world seed itself, which would let a controller recompute terrain and every hidden phase. A test enforces this.
- resource sites and terrain within Manhattan distance 4
- active neighbours within distance 2 (ID, name, position only)
- trade offers addressed to the agent that have not expired
- accessible artifacts: own, already learned, or (with sharing on) verified artifacts in the home library. Programs are included only for own or learned artifacts. **Evaluations are never included.**
- the last 8 memories

Controllers never receive the ledger, global metrics, other agents' inventories or histories, the conversion function, or the scenario configuration.

## Controllers in this release

| Mode | Label in decisions and manifests | What it is |
|---|---|---|
| Deterministic baseline | `deterministic-baseline` | A rule list: eat when energy ≤ 10, gather food when food < 3, accept fundable offers, learn a current verified procedure if none is known, scripted occasional trades and gifts, gather ore, then produce with the best known procedure or fall back to fixed mode 0. |
| Bounded search | `bounded-search` | The same rules, plus the researcher's search over the 16-program grammar and the revision neighbourhood ([INVENTION_PROTOCOL](INVENTION_PROTOCOL.md)). |
| Submitted | `submitted` | An action posted through `POST /api/runs/{id}/actions`. It passes the same validation. |
| Failure fallback | `explicit-failure-fallback` | Used when a controller raised an exception. The action is a `wait` and a `controller_failure` event is logged. It is never presented as a decision. |

The scenario field `controller: "baseline"` turns researchers into producers, so no search happens.

Everything that looks social in a run is scripted: trade offers on `tick % 31 == 9` and food gifts on `tick % 43 == 17`. The engine still validates every one, and they are labelled as scripted here and in the UI notes. **Nothing in this release is model-controlled, and nothing is emergent.**

## Memory

Memory is a bounded window of the agent's own action results (16 stored, 8 retrieved). There is no summarisation yet. The authoritative history is the event log, and memory is only a convenience view of it.

## Deferred: LLM controller

Section 9 of the spec describes an optional provider-independent LLM controller with budgets. **It is not implemented in this release.** This is deliberate: the spec asks for one fully working provider rather than several unfinished ones, and nothing could be run against a paid API without your authorisation.

The integration point is already fixed. An LLM controller implements `AgentController.propose(observation) -> Action`, receives exactly the restricted observation above, and its output goes through the same `Action` schema validation and rule checks. Budget counters (`model_calls`, `tokens`, `cost_usd`) already exist in the metrics and currently read 0. See [ROADMAP](ROADMAP.md), milestone 2.
