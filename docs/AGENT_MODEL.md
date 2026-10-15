# Agent model

An agent is a persistent identity plus state. A controller is attached to it, proposes actions, and never mutates anything itself.

## Persistent state (per agent)

- **Identity and status:** `id`, `name`, `home`, `created_tick`, `status` (`active` / `inactive` / `retired`), position, `energy`, `inventory`, `capabilities` (`converter`, and `library` when knowledge access is granted), `role` (`researcher` / `producer`), `goals`, `plan`, `search_count`.
- **Knowledge:** `known` (artifacts whose AST the agent holds), `seen` (inspected), `used` (executed).
- **Social:** `relationships` (received-interaction counts), `messages` (last 8), `beliefs` (last 8 claims, each with a source event, `confidence: "unverified"` and a revision number).
- **History:** `memories` (the last 16 of the agent's own action results) and `last_result`.
- **Lineage (v0.3):** `predecessor`, `successor`, `retired_tick`, and `inheritance`. The `inheritance` record holds the policy, the package, the role, provenance, and the counts of memories and skills inherited.

Everything lives in the committed state, so it survives restart, replay and export. A retired agent's record stays as an archive, and no controller ever receives it.

## Observations: what a controller can see

`LocalObservations.build(state, agent_id)` builds controller input from an explicit allow-list:

| Field | Content |
|---|---|
| `tick`, `self`, `phase` | The current tick, the agent's own full record, and the phase at its own tile |
| `rules` | `invention_open` and the `search_budget`: the permissions in force for the agent |
| `home_storage` | Its home store's inventory, only when within reach |
| `sites`, `tiles` | Resource sites and terrain within Manhattan distance 4 |
| `neighbors` | Active agents within 2 tiles (ID, name, position) |
| `offers` | Unexpired offers addressed to it |
| `artifacts` | Artifacts it created or holds, plus verified library artifacts if it has `library`. Programs only for those it created or holds. **No evaluation records.** |
| `memory` | Its last 8 memories |

Controllers never receive:

- the world seed or any value derived from it
- the scenario configuration, ledger or global metrics
- other agents' inventories, memories or histories
- retired agents' records
- the conversion function
- evaluation cases

The human observatory reads the full state through the API. The observation builder never reuses that payload.

**Independence test.** [`test_observations_are_independent_of_hidden_parameters`](../tests/test_engine.py) holds the visible inputs fixed and changes hidden parameters: the world seed (chosen to give the same local phase), the controller seed, the ledger, metrics, a distant agent's inventory and memories, and an inaccessible verified artifact. The controller input must be byte-identical.

**What agents may legitimately infer.** An agent sees its own phase, and it receives feedback on its own tests: training totals and pass/fail per partition. So over many tests and moves it could learn something about the phase rule and about the held-out partition as a whole. Blocking direct leaks does not stop learning from permitted feedback, and the experiment documents say so.

## Controllers in this release

| Mode | Label in decisions | What it is |
|---|---|---|
| Deterministic baseline | `deterministic-baseline` | A rule list. Eat when energy ≤ 10. When food < 3, withdraw food from home storage or gather it. Accept fundable offers. Learn an accessible verified procedure if none is held. Scripted trades and gifts. When ore < 2, withdraw ore from storage or gather it. Produce with the best held procedure, otherwise in fixed mode 0. |
| Bounded search | `bounded-search` | The same rules, plus: learn an accessible library procedure first if one exists, then search the 16-program grammar (if nothing is held) or revise the best held procedure. |
| Submitted | `submitted` | An action posted through the API. It passes the same validation. |
| Failure fallback | `explicit-failure-fallback` | A `wait` after a controller exception, logged as `controller_failure` and never presented as a decision. |

**Controller randomness.** `OfflineController(seed)` is constructed for each step from the scenario's independent `controller_seed` (default 7) and holds it privately. Its candidate and revision ordering uses `keyed(seed, …)`. Because the seed is independent of the world seed and never enters an observation, it reveals nothing about the environment.

One consequence: with the same `controller_seed`, every world tries candidates in the same order, and the seeds vary only the environment.

**Scripted, not emergent.** Trades (`tick % 31 == 9`) and gifts (`tick % 43 == 17`) are scripted. **Nothing is model-controlled, and nothing is emergent.**

## v0.4 observation additions

These fields appear only when the task is `workshop-1` or teaching is on, so v0.3 observations are unchanged:

- `humidity` at the agent's own tile
- `sessions`: the agent's own active session, showing stage, work counts, practice count and expiry. It shows **no program** and none of the counterpart's state.
- `rules.task` and `rules.teaching`
- `dev_score` on the agent's **own** proposals (development role)

Observations never include:

- validation scores or records
- freeze records
- sealed anything
- hidden workshop parameters

The agent's own `dev_notes` hold the results of its own development tests.

## v0.4 offline policies (developer-supplied)

| Role | Policy |
|---|---|
| **Researcher** (`workshop-1`) | Learn the current library head if it holds no admitted workflow. Development-test any held workflow it has no note for. Propose the first untried neighbour of its best held workflow (or of the baseline), in an order keyed by the controller's private seed. Submit only when the development score beats the current best. |
| **Producer** | Top up to 8 ore, then run the best held admitted workflow, otherwise the baseline. Upgrade when the library head was superseded. |
| **Learner** (teaching on, nothing held, nothing in the library) | Send `request_lesson` to a neighbour. Accept offers, moving next to the teacher first. Practise when it has at least 4 ore, otherwise obtain ore first. |
| **Teacher** | Answer a request from the last 6 ticks from a neighbour with an offer of its newest held workflow, if its energy is at least 14. |

A fixed schedule defines only cohort transitions. Acquisition and improvement are decided by the engine and evaluators, never by the schedule.

## v0.5 offline policies (developer-supplied)

| Role | Change |
|---|---|
| **Researcher, `first-improvement`** | Unchanged from v0.4. It now records a diagnostic for each decision and labels each proposal's operator. Under credits it stops when fewer than 2 credits remain. |
| **Researcher, `beam`** | See [INVENTION_PROTOCOL](INVENTION_PROTOCOL.md#the-beam-policy). It first tries to refactor its champion to call a held component, tests components inside its champion, and inspects library components it does not hold. |
| **Learner** (`teaching_policy: package`) | Rotates lesson requests over its neighbours by tick, rather than always asking the first. |
| **Teacher** | Unchanged. It offers its newest held workflow. Under `package` the engine computes the closure and teaches missing dependencies inside the session. |

Observations gain, for the agent's *own* artifacts only: the development host, the host's development score, behaviour equality with the host, and the operator. Validation scores, sealed cases, hidden parameters and seeds remain absent (tested).

## Memory

Memory is a bounded window of the agent's own action results (16 stored, 8 retrieved). Test results carry only aggregate feedback; full evaluations stay on the artifact record. The authoritative history is the event log.

## Succession and inheritance

A successor starts empty. Its `inheritance` record states exactly what it received:

- `library`: a capability only
- `none`: nothing
- `direct`: a package of artifact IDs, as a labelled control

Pretrained-model knowledge does not exist here, because the controllers are not language models. When LLM controllers are added, simulation-specific skills (held artifacts) must be kept separate from what a model already knows.

## Deferred: LLM controller

Not implemented. The integration point is `AgentController.propose(observation) -> Action`, using exactly the restricted observation above. Its output would pass the same schema and rule checks. Budget counters (`model_calls`, `tokens`, `cost_usd`) exist and read 0. See [ROADMAP](ROADMAP.md).
