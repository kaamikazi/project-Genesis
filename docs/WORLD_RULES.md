# World rules (`phase-world-2`)

Everything here is enforced by `genesis/engine.py` and `genesis/world.py`. A controller's words never change state. Only an accepted action or a scheduled environment process does.

## Map and time

- The grid is `width × height`, 24 × 16 by default (allowed: 16–64 × 12–48). Terrain is `water`, `grass`, `forest` or `hill`, generated from the `world-terrain` stream keyed by `(seed, x, y)`. The outer ring is always water. The tiles around both settlements and the middle row are always grass, so the two settlements are connected.
- There are two settlements: **Hearth** at `(w/4, h/2)` and **Haven** at `(3w/4, h/2)`. Each has a storage inventory and a library.
- Time is a whole-number tick. Every active agent submits at most one action per tick.

## Resources and accounting

Resources are `food`, `ore` and `alloy`. All quantities are integers.

| Source / sink | Rule |
|---|---|
| Food sites (2 per settlement) | Start at 120, capacity 120, replenish **+2 per tick** (ledger source). |
| Ore sites (2 per settlement) | Start at 240 and **never replenish**. |
| Initial agent inventory | 8 food, 8 ore, 0 alloy. |
| `consume` | 1 food → ledger sink. |
| `produce` / `use_artifact` | 2 ore → ledger sink, 1 alloy → ledger source. |

After every action and every tick, `check_invariants` verifies:

`total(r) == initial(r) + ledger[r].source − ledger[r].sink`

It also checks that no inventory is negative or non-integer, that site stock stays within capacity, that energy stays in 0..40, and that no agent stands on water. A violation aborts the action, so its state is never committed.

The total ore is 1,024: 960 on sites plus 64 carried. That caps alloy at **512 per world**, a design choice that the experiment results reflect.

## Energy

Agents start with 30 energy (maximum 40). Every active agent loses 1 energy per tick (fatigue). An agent with 0 energy and 0 food becomes `inactive` and keeps its inventory. The default scenario is designed so no one starves within 300 ticks; there is no hidden rescue.

## Actions

Every action is a versioned `Action` (`id`, `agent`, `tick`, `kind`, `params`). The parameter set must match exactly. `tick` must equal the current tick, which acts as the observation version.

| Action | Preconditions | Cost | Effect |
|---|---|---|---|
| `wait` | — | 0 | none |
| `move {x,y}` | adjacent tile (Manhattan 1), not water | 1 energy (grass), 2 (forest/hill) | position changes |
| `gather {site}` | site within distance 1, stock > 0 | 1 energy | up to 4 units, site → inventory |
| `consume` | food ≥ 1 | 1 food | +min(20, 40 − energy) energy |
| `transfer {target,resource,amount}` | active recipient within 2, amount 1..100, funded | 1 energy | inventory moves |
| `offer_trade {target,give,give_amount,want,want_amount}` | active agent within 2, funded, one pending offer per maker | 1 energy | offer recorded, expires after 6 ticks |
| `accept_trade {offer}` | offer targets you, not expired, maker active and within 2, **both sides funded now** | 1 energy | atomic two-sided swap |
| `send_message {target,message}` | active agent within 2; message ∈ {`greeting`, `request_food`} | 1 energy | recipient stores an *unverified* belief; no competence transfers |
| `produce` | converter capability, ore ≥ 2 | 2 or 6 energy (see phase) | 2 ore → 1 alloy, fixed mode 0 |
| `propose_artifact {program,parent}` | search budget left, valid AST, parent learned **and still current** | 1 energy | immutable proposed artifact |
| `test_artifact {artifact}` | creator only, status `proposed` | 3 energy | independent evaluation (see [INVENTION_PROTOCOL](INVENTION_PROTOCOL.md)) |
| `inspect_artifact {artifact}` | access allowed, `verified`, not yet known, within 2 of home settlement | 2 energy | logged transmission; recipient learns the AST |
| `use_artifact {artifact}` | `verified` or `superseded`, learned | production cost under the program's chosen mode | 2 ore → 1 alloy; usage evidence recorded |

Rejected actions record a reason, such as `insufficient energy` or `artifact access denied`. Every action runs on a disposable copy of the state, so a rejection cannot partly change anything.

## The hidden phase mechanic

Each location and tick has a phase `keyed(seed, "environment-phase", tick, x, y) % 12`. An agent observes only the phase where it stands.

Conversion costs **2 energy** when the mode matches the phase: mode 0 for phase < 6, mode 1 for phase ≥ 6. Otherwise it costs **6 energy**.

This rule is a deliberately unfamiliar, fictional mechanic. Controllers never receive the conversion function or the world seed.

## Knowledge access

- **Sharing on:** an agent may inspect any `verified` artifact in its home settlement's library.
- **Sharing off:** an agent can access only artifacts it created. No other route carries procedures: messages use a two-word vocabulary, observations exclude other agents' action histories, and there is no teaching action yet.

## Tick order (scheduled processes)

1. Build each active agent's observation from the committed state at the start of the tick.
2. Collect proposals. A controller exception becomes an audited `controller_failure` plus a labelled `wait` fallback.
3. Rotate priority by `tick mod active_count`, so the lowest ID is not always first.
4. Apply each proposal in order to a disposable copy of the evolving state. Ownership, proximity, funding and stock are checked again at this point, so a later agent can lose contention for a depleted site.
5. `tick += 1`; apply fatigue and inactivity.
6. Apply the **scheduled lifecycle removal**, if the scenario defines one for this tick.
7. Replenish food sites.
8. Expire offers that are too old, now unfunded, or involve an inactive or distant party.
9. Check invariants, then commit everything in one SQLite transaction.

## Lifecycle removal (scenario option)

`removal: "creators" | "matched"` at `removal_tick`.

- **creators:** retires every active agent who created a currently verified artifact.
- **matched:** retires one non-creator from each of those creators' settlements, the lowest ID not already chosen. This is the control condition.

Retired agents stop acting, stop tiring, and disappear from neighbours' observations. Their inventory moves to their settlement's storage, so resources are conserved and the comparison isolates lost workers and lost knowledge. If no verified creators exist, the event records that nobody was removed.

This is scheduled lifecycle management. It is not death, reproduction, or evolution.
