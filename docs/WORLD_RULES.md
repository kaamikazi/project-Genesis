# World rules (`phase-world-4`)

Everything here is enforced by `genesis/engine.py`, `genesis/world.py` and, for the `workshop-1` task, `genesis/workshop.py`. v0.4 additions (task `workshop-1`, teaching, cohorts) are scenario fields whose defaults (`task: phase-1`, `teaching: false`, `lifecycle: single`) reproduce v0.3 behaviour exactly; see `test_v030_scenarios_reproduce_under_v040_rules`. A controller's words never change state. Only an accepted action or a scheduled environment process does.

## Map and time

- The grid is `width × height`, 24 × 16 by default (allowed: 16–64 × 12–48). Terrain is `water`, `grass`, `forest` or `hill`, generated from the `world-terrain` stream keyed by `(seed, x, y)`. The outer ring is always water. The tiles around both settlements and the middle row are always grass, so the two settlements are connected.
- There are two settlements: **Hearth** at `(w/4, h/2)` and **Haven** at `(3w/4, h/2)`. Each has a communal **storage** and a **library**.
- Time is a whole-number tick. Every active agent submits at most one action per tick.

## Resources and accounting

Resources are `food`, `ore` and `alloy`. All quantities are integers.

| Source / sink | Rule |
|---|---|
| Food sites (2 per settlement) | Start at 120, capacity 120, replenish **+2 per tick** (ledger source). |
| Ore sites (2 per settlement) | Start at `ore_per_site` (default **240**). They **never replenish**. |
| Initial agent inventory | 8 food, 8 ore, 0 alloy. Successors start with nothing. |
| `consume` | 1 food → ledger sink. |
| `produce` / `use_artifact` | 2 ore → ledger sink, 1 alloy → ledger source. |

After every action and every tick, `check_invariants` verifies:

`total(r) == initial(r) + ledger[r].source − ledger[r].sink`

It also checks that no inventory is negative or non-integer, that site stock stays within capacity, that energy stays in 0..40, that no agent stands on water, and that retired agents hold nothing. A violation aborts the action, so its state is never committed.

**Alloy ceiling.** Initial ore is `4 × ore_per_site + 8 × population`. With the defaults (8 agents, 240 per site) that is 1,024 ore. Each alloy costs 2 ore, so the **theoretical maximum** is 512 alloy per world. Whether a world reaches it depends on whether it runs long enough and whether any ore ends up inaccessible. The independent reducer reports produced alloy per world against this maximum.

## Settlement storage

Storage has **unlimited capacity**. Access is limited to **members**: agents whose `home` is that settlement and who stand within 2 tiles of it. Storage access is independent of knowledge sharing, so a sharing-restricted agent can still use communal goods.

- `deposit {settlement, resource, amount}` moves goods from the agent to the store.
- `withdraw {settlement, resource, amount}` moves goods from the store to the agent.

Both cost 1 energy, require 1 ≤ amount ≤ 100, and update the store's `flows` ledger (`deposit`, `withdraw`, `retirement`). Withdrawals are checked against current stock when they resolve. If two members compete for the same stock in one tick, the second fails with `insufficient settlement stock`. A store with no active members is reported as inaccessible by the reducer.

## Energy

Agents start with 30 energy (maximum 40). Every active agent with energy left loses 1 per tick (fatigue). An agent with 0 energy and 0 food becomes `inactive` and keeps its inventory.

Every accepted action records `energy_charged`. Environment events record per-agent `fatigue`. Together these account for every change in energy: [tests/test_reducer.py](../tests/test_reducer.py) reconciles each agent's energy using events alone.

## Actions

Every action is a versioned `Action` (`id`, `agent`, `tick`, `kind`, `params`). The parameter set must match exactly. `tick` must equal the current tick, which acts as the observation version. Only `active` agents can act. Submissions for retired or inactive agents are rejected with a logged reason.

| Action | Preconditions | Cost | Effect |
|---|---|---|---|
| `wait` | — | 0 | none |
| `move {x,y}` | adjacent tile, not water | 1 (grass) / 2 (forest, hill) | position changes |
| `gather {site}` | site within 1, stock > 0 | 1 | up to 4 units, site → inventory |
| `consume` | food ≥ 1 | 1 food | +min(20, 40 − energy) energy |
| `transfer {target,resource,amount}` | active recipient within 2, funded | 1 | inventory moves |
| `offer_trade {…}` | active agent within 2, funded, one pending offer per maker | 1 | offer recorded, expires after 6 ticks |
| `accept_trade {offer}` | targets you, not expired, maker active and within 2, **both sides funded now** | 1 | atomic swap |
| `send_message {target,message}` | active agent within 2; `greeting` or `request_food` | 1 | recipient stores an *unverified* belief |
| `deposit` / `withdraw` | member, within 2 of the store, funded | 1 | storage transfer |
| `produce` | converter capability, ore ≥ 2 | 2 or 6 (phase) | 2 ore → 1 alloy, fixed mode 0 |
| `propose_artifact {program,parent}` | `invention: open`, budget left, valid AST, parent held **and still current** | 1 | immutable proposed artifact |
| `test_artifact {artifact}` | creator only, status `proposed` | 3 | independent evaluation; agent gets aggregate feedback only |
| `inspect_artifact {artifact}` | **library capability**, home library, `verified`, not yet held, within 2 of home | 2 | logged transmission; the AST is now held |
| `use_artifact {artifact}` | artifact held, `verified` or `superseded` | production cost under the chosen mode | 2 ore → 1 alloy; usage and first-use evidence recorded |

Each action runs on a candidate copy of the state, so a rejection cannot partly change anything. Since v0.3.0, the candidate copies only the objects an action can mutate and shares everything else. Results are identical to the full-copy reference: [tests/test_optimization.py](../tests/test_optimization.py) checks this.

## The hidden phase mechanic

Each location and tick has a phase `keyed(seed, "environment-phase", tick, x, y) % 12`. An agent observes only the phase where it stands.

Conversion costs **2 energy** when the mode matches the phase (mode 0 for phase < 6, mode 1 for phase ≥ 6) and **6 energy** otherwise. Controllers never receive the conversion function, the world seed, or any value derived from it.

## Knowledge access

Knowledge access is the `library` capability. It is separate from physical storage access.

- `sharing: true` gives every initial agent `library`. `sharing: false` gives none.
- A successor gets `library` only when `successor_access: "library"`.
- An agent can execute only artifacts it **holds** (`known`), and it can obtain them only by:
  - verifying its own proposal,
  - inspecting the library (which requires the capability), or
  - receiving the labelled direct-transfer succession package.

There is no other route. Messages use a two-word vocabulary, observations exclude other agents' histories, retired agents' records are never shown to controllers, and there is no teaching action.

## Tick order (scheduled processes)

1. Build each active agent's observation from the committed state at the start of the tick.
2. Reject any submitted action for a non-active agent. Collect proposals from active agents. A controller exception becomes an audited `controller_failure` plus a labelled `wait`.
3. Rotate priority by `tick mod active_count`.
4. Apply proposals in order. Ownership, proximity, funding and stock are checked again at resolution.
5. `tick += 1`; apply fatigue and inactivity.
6. **Lifecycle transition** (if scheduled for this tick): retire the selected agents, then create successors.
7. Replenish food.
8. Expire offers that are too old, unfunded, or involve a party who is not active or not within reach. Offers made by or to retirees expire here, in the same step as the retirement.
9. Check invariants, then commit everything in one SQLite transaction.

## Lifecycle: retirement and succession

`removal: "creators" | "matched"` at `removal_tick`:

- **creators:** every active creator of a currently verified artifact retires.
- **matched:** one non-creator from each creator's settlement retires (lowest ID not already chosen). This is a *descriptive* control: these workers differ from the creators in role and labour.

**Retirement.** The agent becomes `retired` with `retired_tick` set. Its whole inventory moves to its settlement's storage, recorded in `flows.retirement` and the event's `inventory_moved`, where members can withdraw it. The agent's identity and history stay in state as an archive, and controllers never see them.

**Succession** (`succession: "fresh"`). Each retiree is replaced at the same boundary by a new agent with:

- a new ID and name, at the settlement, with 30 energy and nothing in inventory
- no memories, beliefs, relationships or held procedures
- role set by `successor_role`
- a recorded `predecessor` link (the retiree gets a `successor` link)
- an `inheritance` record: policy, package, provenance, and counts of inherited memories and skills

| `successor_access` | What the successor can obtain |
|---|---|
| `library` | The `library` capability. It must still discover, inspect and execute a procedure itself. |
| `none` | Nothing. No capability, no package. |
| `direct` | A labelled **debugging control**: the settlement's current verified procedures, handed over with a `succession package (direct-transfer control)` transmission record. |

`invention: "frozen"` rejects every new proposal. Diagnostic experiments use it so that relearning cannot mask inherited retention.

All of this is simulated lifecycle management. It is not death, reproduction or culture.


## Task `workshop-1` (v0.4)

A batch workflow replaces single conversions. `produce` runs the baseline workflow. `use_artifact` runs an admitted workflow the agent holds. A program decides four things from local measurements (`phase`, `humidity`) and the agent's own `ore` and `energy`:

- **batch** b (1–4)
- **heat** h (0–3)
- **mode** (0/1)
- **flux** (0/1, costs 1 food)

Hidden per-world parameters are drawn from the world seed and never observed:

- a phase split `s` ∈ 4–8
- a heat offset `o` ∈ 0–2
- a flux threshold `f` ∈ 4–6

| Quantity | Rule |
|---|---|
| Optimal heat | `h* = min(3, (humidity + o) // 3)` |
| Ore | `2b + ⌈b·|h − h*|/2⌉`, plus 1 if `humidity ≥ f` and no flux |
| Energy | `3 + b·(2 if mode matches the phase split else 5) + 2h` |
| Output | `b` alloy |
| Busy time | The agent is busy for `b − 1` more ticks. Only `wait` and `consume` are accepted while busy. |

An infeasible batch is rejected and nothing changes. All flows go through the ledger: ore sink, food sink for flux, and alloy source.

**Proposal and test actions:**

| Action | Cost | Result |
|---|---|---|
| `propose_artifact` | 1 energy | Workshop programs may name composition `sources` and call held components. |
| `test_artifact` | 3 energy | Development role: per-case results on the 24 development cases, for your own proposal or any workflow you hold. |
| `submit_artifact` | 2 energy | Validation role on 24 validation cases. The proposer learns only *admitted* or *not admitted*. An admitted revision supersedes its parent. |

## Teaching sessions (`teaching-1`, when `teaching: true`)

| Action | Requirements | Cost |
|---|---|---|
| `offer_teaching {learner, artifact}` | Teacher **holds** the artifact; same settlement; within 2 tiles; learner lacks it; neither is in another session | 1 |
| `accept_teaching {session}` | Learner, before expiry (6 ticks), co-located (≤ 1). If the program calls components the learner does not hold, the session **fails** with the reason recorded. | 0 |
| `teach_step` / `learn_step {session}` | Co-located; 3 work units per side | 2 / 1 |
| `practice_step {session}` | A real supervised execution with the learner's own inputs. After 2 runs, **acquired** only if every run cost no more per alloy than the baseline under the same conditions, otherwise **failed**. | as production |
| `abandon_session {session}` | Either participant | 0 |

**Reservation.** During instruction, both participants may only take their step, `consume`, `wait` or abandon.

**Interruption.** The environment step interrupts a session when a participant is no longer active, or when there has been no progress for more than 8 ticks. Unaccepted offers expire.

**Recording.** Acquisition adds the artifact to the learner's holdings, with a `teaching session` transmission. The learner's first later `use_artifact` is recorded as `first_independent_use`.

**Request channel.** `request_lesson` is added to the message vocabulary only when teaching is on. Messages still cannot carry programs.

## Cohort lifecycle (`lifecycle: cohorts`)

At each tick `k·cohort_ticks` (for `k = 1…cohort_count−1`), the environment step:

1. records a **freeze**,
2. retires every active agent, moving their inventory to storage,
3. creates one fresh agent per retiree, with the same home and role, cohort `k`, and no memories or holdings.

A final freeze is recorded at `max_ticks`.

With `cross_cohort_access: false`, the library hides artifacts created by earlier cohorts. Within a cohort, sharing is unchanged.
