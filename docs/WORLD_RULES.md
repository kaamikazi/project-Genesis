# World rules (`phase-world-3`)

Everything here is enforced by `genesis/engine.py` and `genesis/world.py`. A controller's words never change state. Only an accepted action or a scheduled environment process does.

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
