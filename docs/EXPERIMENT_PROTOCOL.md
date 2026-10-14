# Experiment protocols (v0.3.0)

There are two kinds of experiment. They answer different questions and must not be confused.

| Protocol | Question | Status of its retirement results |
|---|---|---|
| `paired-phase-3` (descriptive) | How do whole runs differ by condition? | **Descriptive only.** Not a knowledge-retention test. |
| `inheritance-diagnostic-1` (controlled) | Does a successor obtain and use a procedure through a permitted path after its creator retires? | Controlled test |

Both are exploratory checks of designed mechanisms. They are not tests of general hypotheses about artificial societies.

## Common rules

- **Seeds are fixed in advance:** 11, 42 and 77. Run lengths and windows are fixed before running, and a step's stopping rule is written into its report.
- **Durable intent:** every planned attempt is written to the report **before** it runs, then marked `completed`, `failed` (with the error) or `ineligible` (with the reason). Nothing is dropped.
- **Replay check:** every completed world is replayed from its records and must match its final state hash.
- **Independent metrics:** every number comes from the **independent reducer** (`genesis/reducer.py`), which reconstructs every holding from events and must reconcile with the final state. A failed reconciliation fails the attempt.
- **Units and denominators** are always reported. A zero denominator is reported as *unavailable*, never as zero.
- **Aggregation:** per-world values come first. Across worlds, the **mean of world ratios** and the **pooled ratio** (summed numerators over summed denominators) are both reported and labelled. One is never silently substituted for the other.
- **Unit of analysis:** one world is one experimental unit. Agents within a world, including two successors, are not independent samples.
- **Controller seed:** every condition uses the same independent `controller_seed` (7). The controllers are deterministic, so seeds vary only the environment.

## Metric definitions (reducer)

| Metric | Definition |
|---|---|
| Produced alloy | Sum of `alloy` over accepted `produce` and `use_artifact` events after the run's origin tick. Starting inventory is excluded. Reported separately from final alloy holdings. |
| Production energy per alloy | Production energy ÷ produced alloy. This is **efficiency**. |
| Charged energy per alloy | Energy charged by all accepted actions (travel, gathering, production, search, evaluation, learning, exchange, storage) ÷ produced alloy. This is **total action cost**. |
| Total energy per alloy | Charged energy plus fatigue, ÷ produced alloy |
| Window | Committed ticks `t` with `start < t ≤ end`. Actions committed in tick `t` carry event tick `t`. A lifecycle transition at tick `R` happens **after** that tick's actions, so the post-removal window starts at `R + 1`. |
| Library acquisition | An accepted `inspect_artifact` |
| Use with saving | An accepted `use_artifact` whose recorded energy is below the fixed-mode baseline at the same phase. An execution that only matches the baseline counts as an execution, not a saving. |
| Accessible remaining | Resources on sites, held by active agents, or in a store with at least one active member |
| Active-agent ticks | Decisions with an observation, summed over ticks |

## `paired-phase-3`: descriptive whole-run comparison

Each seed runs seven conditions for 160 ticks: `sharing`, `restricted`, `baseline`, and retirement at tick 80 of `creators` or `matched` workers, each with sharing on or off.

**What changes between `sharing` and `restricted`:** only the `library` capability. Trade, transfers, settlement storage and the two-word message vocabulary are identical.

**Why retirement rows are descriptive.** Creators are researchers who spent many ticks searching. Matched retirees are producers. Their labour, role and inventory differ, as the v0.2.0 audit found (21–31 vs 38–42 production actions before removal). Retiree inventory now moves to *withdrawable* storage, so goods are no longer stranded, but this does not make the conditions equivalent.

## `inheritance-diagnostic-1`: controlled succession

**Design (per seed):**

1. Run one base world (sharing on, bounded search) to a committed checkpoint at tick 60.
2. **Eligibility:** at least one verified procedure exists, and the remaining ore is at least 1.5 × (ore used per tick so far) × window. An ineligible seed is recorded with its numbers and is never silently skipped.
3. Fork **matched continuations** from that checkpoint, each recorded in its manifest with an intervention and a label:

   | Continuation | Successor role | Knowledge policy | Invention |
   |---|---|---|---|
   | `successor-library` | producer | `library` | frozen |
   | `successor-no-library` | producer | `none` | frozen |
   | `successor-direct-control` | producer | `direct` (labelled debugging control) | frozen |
   | `live-library` | researcher | `library` | open |
   | `live-no-library` | researcher | `none` | open |

4. At the boundary (tick 61), the **same** verified creators retire in every continuation, under the same inventory rule (to withdrawable storage). Each is replaced by one fresh successor with no memories, no held procedures and empty inventory.
5. **Physical-parity check:** at the boundary, each diagnostic continuation's state is hashed with only the declared policy differences masked out (successor capabilities, held procedures and inheritance records; succession-package transmissions). All hashes must be identical, and the retiree lists must match.
6. **Diagnostic window:** ticks 62–101 (40 ticks). Invention is frozen identically in all three diagnostic continuations, so relearning cannot hide whether knowledge was inherited.
7. **Live continuation:** a separate experiment, ticks 62–161, with invention open. It shows the realistic interaction of inheritance and rediscovery.

**What counts as successful inheritance.** For a successor:

- a logged library acquisition, which is the permitted path, followed by
- its own execution of that procedure, and
- a measured saving against the fixed-mode baseline.

A procedure's name in memory does not count. The observatory's *Why this counts as retention* panel shows each link and marks missing ones.

**Restricted successors** start with `known = []`, no `library` capability and no memories, all recorded at the boundary. There is no class default, cloned controller state, shared registry or warm cache that could carry a skill: the controller is stateless apart from its seed, and observations list only artifacts the agent may access.

**Resources.** At 8 agents the default 240 ore per site leaves 562–568 ore at the checkpoint, so the diagnostic window never depletes. At **20 agents** the default world runs dry by tick 60 (42–54 ore left), and all three seeds were correctly marked ineligible in a first run. The 20-agent experiment therefore uses a **declared** `ore_per_site: 960`. No ore is ever added mid-run. In the 8-agent live continuation, ore **does** run out before tick 161; this is flagged as `depleted` in the report, and comparisons in that window are cost-per-alloy only.

## Interpretation limits

- The outcomes follow from designed mechanics. The software measures and exposes them; it did not discover them.
- The controllers are deterministic, so the variation across seeds is environmental only. Three seeds are a smoke test, not a sample.
- Production efficiency (energy per alloy) and output (alloy) are different things. Finite ore caps output, so in most conditions sharing changes cost, not volume.
- Partition-level evaluation feedback leaks aggregate information about the held-out set over repeated tests. The diagnostic freezes invention partly to keep this out of the window.

## Running it

```bash
python tools/generate_evidence.py
```

This regenerates everything and logs each command, exit code and duration to `evidence/v0.3.0/runs.json`. Individual steps:

```bash
python -m genesis.cli inherit --seeds 11 42 77 --checkpoint 60 --window 40 --live-window 100
python -m genesis.cli inherit --population 20 --ore-per-site 960 --out evidence/v0.3.0/twenty/inheritance
python -m genesis.cli compare --seeds 11 42 77 --ticks 160
python -m genesis.cli reduce evidence/v0.3.0/inheritance/42-successor-library.json.gz
```
