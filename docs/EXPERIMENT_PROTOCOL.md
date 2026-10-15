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

---

# Milestone 4 protocols (v0.4.0)

The frozen protocol is [`evidence/v0.4.0/protocol/frozen-protocol.json`](../evidence/v0.4.0/protocol/frozen-protocol.json). It was written **after** calibration and **before** any evaluation seed ran. It contains:

- the seeds, settings, objective, admission and selection rules, and performance levels
- the SHA-256 commitment to the sealed case list
- the git commit and the runtime-source hash

## Calibration and evaluation split

| | Seeds | Note |
|---|---|---|
| Calibration | 100, 101, 103 | Hidden workshop parameters differ from every evaluation seed |
| Evaluation | 11, 42, 77, 5, 23 | Never run before the freeze |

Calibration checks:

- **No immediate saturation:** best validation scores 6.9–9.2, against a lower bound of about 4.4.
- **Resource sufficiency:** about 2,300 ore remained after 180 ticks.
- **Teaching completes:** 6/6 successors acquired a procedure, with failures and retries recorded.
- **Parity holds:** physical parity at the boundaries.

Settings frozen from calibration: cohorts of 60 ticks × 3, 900 ore per site, 16 proposals per researcher lifetime; for A, checkpoint 60 and window 60. Calibration outputs are in `evidence/v0.4.0/calibration/`.

## Experiment A: `teaching-acquisition-1`

1. Each seed runs a base world (`workshop-1`, library sharing, bounded search) to tick 60.
2. **Eligibility:** every settlement has an admitted-workflow holder who is not a creator, and ore suffices for the window.
3. Four continuations are forked from that committed state. At tick 61, the same admitted-workflow creators retire (inventory to storage), fresh producers replace them, and invention is frozen.

| Continuation | Successors' knowledge path | Physical access |
|---|---|---|
| `teaching` | No library; costly teaching by existing holders | Identical |
| `library` | Library inspection (2 energy) | Identical |
| `no-transfer` | None | Identical |
| `direct-control` | Labelled debug package | Identical |

**Teaching-only boundary.** Successors lack the `library` capability. Direct packages are off. Messages cannot carry programs (two-word vocabulary plus `request_lesson`). Observations list only artifacts the agent holds or may access. The `teaching` flag is off in the other three conditions, so teaching is not a hidden path there. Physical parity is checked at the boundary, with only the policy fields masked.

**Metrics** (from the reducer): instruction cost by role (energy and ticks), ticks to acquisition, session failures and interruptions with reasons, ticks to the first use with a saving, successor and settlement production energy per alloy, charged energy per alloy, and successors active at the end.

## Experiment B: `cumulative-invention-1`

- **Design:** both conditions start from the same world (`workshop-1`, library sharing within a cohort, bounded search, teaching off). Every 60 ticks the cohort is replaced, for 3 cohorts.
  - `preserved`: the library shows earlier cohorts' admitted workflows.
  - `reset`: the library hides them.
- **Parity:** the state at tick 60 must be identical, with only the policy text masked.
- **Equal opportunity:** each researcher has the same 16-proposal budget, and all spending is reported.
- **Selection:** the engine freezes, by validation score, the best workflow *created by* the ending cohort and the best *accessible to* it.
- **Final evaluation:** sealed scores are computed only after every run closes (`sealed-results.json`).
- **Improvement:**
  - A *cross-generation revision attempt* is a proposal whose parent came from an earlier cohort.
  - An *admitted* attempt beat that parent on the same validation cases.
  - The sealed score of frozen artifacts, by cohort, is the independent check.
- **Performance levels** (validation cost per alloy, fixed in advance): 11.0, 9.0, 7.5, 6.5. The report gives the first tick each level is reached.
- **Replication unit:** one world. Five seeds is exploratory, not a sample size.

# Milestone 5 protocols (v0.5.0)

Frozen in `evidence/v0.5.0/protocol/protocol.json` before any evaluation run, together with the sealed-2 commitment and the source fingerprint.

## Calibration and evaluation split

- **Calibration** used seeds 300–302 only. Every iteration, including those that did not help, is in `evidence/v0.5.0/calibration/CALIBRATION_LOG.md`.
- **Evaluation** used seeds 201–205: new worlds with their own hidden parameters, never run before.
- **Settings:** 8 agents, 3 cohorts × 60 ticks, ore 900 per site, 48 search credits per researcher lifetime. Overlap is 0 in P and 30 in T.
- **Final scores:** sealed-2 scores are computed only after every run is closed, for artifacts frozen by validation.

## Experiment P: `search-policy-1`

- **Conditions:** `first-improvement/preserved`, `first-improvement/reset`, `beam/preserved`, `beam/reset`, and separately `beam-nocomponents/preserved` (the language-capability comparison). Teaching is off.
- **Parity:** physical parity is checked on the initial state, since policies differ from the first decision. Access parity (preserved vs reset, same policy) is checked at the first boundary.
- **Primary measure:** the final freeze's `held_best`, by validation and by sealed-2, paired by seed within each access condition.
- **Claim rule:** a direction is called consistent only if it holds in at least 4 of 5 paired seeds. No significance test is claimed.

## Experiment T: `overlap-teaching-1`

- **Setup:** beam search, `teaching_policy: package`, and successor cohorts arriving 30 ticks before every boundary in all conditions. Retirement is never delayed.
- **Conditions:** `library` (cross-cohort library visible, no teaching), `teaching-only` (cross-cohort library hidden, teaching on), and `none`.
- **Parity:** `library` and `none` must be physically identical at the first arrival (checked). `teaching-only` teaches within cohort 0 from tick 0, so it is not expected to match.
- **Measures:** cross-generation lessons and their outcomes; dependencies taught and acquired; uses of earlier cohorts' artifacts; and further improvement, meaning a cohort's own best admitted workflow strictly beats the best workflow the previous cohort's members held at their freeze.
- **Optional direct-transfer diagnostic:** not run.

## Running it

```
python tools/generate_evidence_m5.py
```

The pipeline runs calibration, then the protocol freeze (it refuses to overwrite an existing protocol), P, T, sealed-2 scoring, the demonstration fixture, the restart check, the search CPU benchmark, the 8- and 20-agent profiles, and the summaries (`evidence/v0.5.0/SUMMARY.md`).

# M5b protocols (v0.5.1)

Frozen in `evidence/v0.5.1/protocol/protocol.json` before evaluation, with implementation and controller fingerprints, seeds, settings, conditions, primary contrasts, selection rules, metric version, missing-data handling, stopping and exclusion rules, and the sealed-3 commitment.

Results are kept in separate stages and are never merged into one claim:

1. **Regression and bugfix evidence.** Minimal reproductions against tag v0.5.0 and the current code.
2. **Post-hoc corrections to v0.5.0 summaries.** Computed from the unchanged raw evidence.
3. **Repaired retrospective rerun.** Every v0.5.0 world configuration re-run under v0.5.1. Its sealed-2 scores are retrospective, because those cases were already known.
4. **Calibration on seeds 310–312.** The mentorship schedule and the sample size are chosen by rules written before running (`tools/calibrate_m5b.py`).
5. **Prospective allocation experiment (`allocation-1`).**
   - Conditions: repaired beam vs beam + allocation bundle, × preserved/reset access, plus first-improvement as a fixed reference.
   - Primary measure: final held-best sealed-3 score, paired by seed.
   - Limit: identifies the bundle's combined effect, not each guard's.
6. **Prospective mentorship experiment (`mentorship-1`).**
   - Conditions: library / teaching-only (package-scheduled) / none, on the calibrated schedule, identical in every condition.
   - Primary measures: dependency-lesson eligibility, attempts and outcomes, independent post-retirement execution, and final held-best sealed-3 for teaching-only vs none.
7. **Validation-panel experiment.** Infrastructure only; deferred.

**Paired-comparison rule** (descriptive). A direction is reported only if at least 75% of expected worlds are eligible pairs and one side is lower in at least 75% of eligible pairs. Every comparison lists expected, eligible and missing worlds with reasons, and the denominator. The exact sign-test probability is shown as a description. Agents and cohort transitions within a world are not independent replications.

```
python tools/generate_evidence_m5b.py
```
