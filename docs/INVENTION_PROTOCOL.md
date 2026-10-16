# Invention protocol (`phase-evaluator-3` legacy · `workshop-evaluator-1` · `workshop-sealed-1`)

An invention in GENESIS is an immutable program that is executed and measured. A claim about one changes nothing. This document describes the language, the search that generates candidates, and the evaluator that accepts or rejects them.

## The program language

Programs are typed JSON trees interpreted by `genesis/invention.py`. Nothing is passed to `eval` or `exec`.

```json
{"op": "if_phase_lt", "threshold": 6,
 "then": {"op": "mode", "value": 0},
 "else": {"op": "mode", "value": 1}}
```

| Operator | Fields | Meaning |
|---|---|---|
| `mode` | `value ∈ {0, 1}` | Choose a conversion mode. |
| `if_phase_lt` | `threshold ∈ 0..12`, `then`, `else` | Branch on the agent's locally observed phase. |

Limits: at most 15 nodes, depth 4, 2,048 canonical bytes and 8 execution steps. Executing a program requires the `converter` capability. Unknown operators, extra fields and booleans used as integers are rejected. A program can read only the phase passed to it. It has no access to world state.

## Artifacts

An artifact's ID is the SHA-256 of `{program, creator, parent, language}`. Each artifact records:

- creator, creation event and settlement
- parent and `generation` (0 for an original)
- `status`: `proposed` → `verified` | `rejected`, and later `superseded`
- the full evaluation, including every case
- transmissions (who learned it, when, and through which channel)
- uses (the last 64), each with the phase, chosen mode, energy and baseline energy
- `first_uses`: each agent's first execution, kept permanently so a successor's first use is never truncated
- independent adopters

Content hashes are re-checked whenever an artifact is accessed, loaded, imported or stored. SQLite triggers make the artifact table immutable.

## How candidates are generated: bounded search

The offline researcher (one per settlement) is **not** a language model. It searches a declared, finite space.

1. **Learn before searching.** If its library offers a verified procedure and it holds none, the researcher inspects it first. Successor researchers rely on this.
2. **Original candidates.** If it holds no verified procedure, it searches the grammar `if_phase_lt t → mode d else mode 1−d` for `t ∈ 2..9`, `d ∈ {0, 1}`: 16 programs, tried in an order keyed by the controller's private seed.
3. **Revisions.** Starting from the best verified procedure it holds, whether its own or inherited, it tries the neighbourhood `{threshold − 1, threshold + 1, swap branches}`. It stops once every neighbour has been tried (a local optimum).
4. **Budget.** 16 proposals per researcher (`search_budget`). A proposal costs 1 energy and a test costs 3. The reducer reports these as the `search` and `evaluation` energy categories.

A revision of someone else's procedure keeps the full chain: the parent's creator, the reviser, the generation, and the transmission that put the parent in the reviser's hands.

**Feedback separation.** After `test_artifact`, the proposer receives only:

- `status`
- training energy against the training baseline
- `training` and `held_out` as `pass` or `fail`
- `improves_on_parent`

Case-level results, including which held-out phases failed, stay on the artifact record, which only the observer reads. v0.2.0 leaked held-out case failures into agent memories; see [audit](audit/AUDIT-v0.2.0.md), item 8. Partition-level pass/fail still gives a little aggregate information about the held-out set over repeated tests.

## Evaluation

`PhaseEvaluator` re-executes the program on fixed cases with the same `conversion()` function that production uses.

- **Training phases:** 1, 4, 7, 10
- **Held-out phases:** 0, 2, 3, 5, 6, 8, 9, 11, disjoint from training
- **Baseline:** fixed mode 0 (the `produce` action)
- **Inputs:** every case converts 2 ore into 1 alloy. Only energy varies, so no gain can come from cheaper inputs.

A program is **verified** only if all of the following hold:

1. No case in either partition uses more energy than the baseline.
2. Each partition saves at least 25% against the baseline.
3. For a revision: total energy is strictly lower than the parent's **on the same cases**. The evaluator re-executes the parent itself and asserts that the case lists are identical.

Otherwise the program is **rejected**, and every failed criterion is listed in `evaluation.failures`. Examples: `held-out phase 5: 6 energy is worse than baseline 2`, `training saving 0% is below 25%`, `no improvement over parent (24 vs 24 energy)`. Duplicate proposals (same program, creator and parent) are rejected at proposal time as a logged `action_rejected`.

When a revision is verified, its parent becomes `superseded`. Holders of an older version may keep using it.

**Scope of "verified":** phase 0..11, 2 ore → 1 alloy, energy only, in this world.

## Optimality, scoped

[`evidence/v0.3.0/invention/search-space.json`](../evidence/v0.3.0/invention/search-space.json) evaluates every single-threshold program (thresholds 0–12, both orientations) and both constants.

**Lower bound.** Every case costs at least 2 energy under `conversion()`, and there are 12 cases, so **no program in the language can score below 24** on this evaluation set. Threshold 6 (then mode 0) reaches 24 and is the only program that does. Four programs in the controller's grammar verify (thresholds 6, 7, 8 and 9 with mode 0).

"24 is optimal" therefore means optimal **for these 12 cases, this conversion rule, and energy as the objective**, and nothing more.

## What a run actually shows (v0.3.0)

With the default controller seed, the Hearth researcher climbs 32 → 28 → 24 and the Haven researcher finds 24 directly (all seeds; see `test_search_climbs_a_verified_lineage_during_the_run`). In the live succession continuation, successor researchers learn the inherited 24-energy procedure and then propose its three neighbours. All three are rejected for not improving on the parent. This is a real, recorded cross-generation revision attempt, and it fails because the inherited procedure is already optimal.

This is a small hill-climb in a 1-D space. It is real and measured, and it is not open-ended invention.

## Known limitations

- The search space is tiny and designed by hand. The optimum is reachable by design and is reached within about 20 ticks.
- Partition-level feedback slowly leaks aggregate information about the held-out set.
- No arbitrary code is executed. An unrestricted-code sandbox would be a separate project.


---

## v0.4: evaluation roles and the `workshop-1` task

The legacy `phase-1` task and its `verified` label are unchanged. They mean *verified on training and held-out partitions, both adaptive*: the proposer received pass/fail on each.

### Three roles

| Role | Cases | Visible to the proposer | Status |
|---|---|---|---|
| Development | 24, public partition seed | Per-case cost, alloy and feasibility, plus the score against the baseline | `dev-tested` |
| Validation | 24, disjoint from development | **Only** admitted / not admitted | `admitted` (operational, validation-adaptive) or `not-admitted` |
| Sealed | 48, disjoint from both, drawn from a seed in `evidence/v0.4.0/protected/sealed-manifest.json` | Nothing, ever | A final score in experiment reports only |

**Admission rule.** An original is admitted if its validation score is at least 5% below the baseline. A revision is admitted only if its score is strictly below its parent's on the same 24 cases; the evaluator recomputes the parent and asserts the case lists match.

**Objective (fixed in advance):** pooled `(energy + 4·ore wasted + 3·food) / alloy`. An infeasible case costs 10 and yields no alloy.

**Selection, then evaluation.** The engine records freezes by validation score at each cohort boundary and when the run closes. `genesis/sealed.py` scores only the frozen artifacts, only for closed runs, and only after the protocol has committed to the sealed case hash. No world-path module imports it (`test_no_world_path_module_imports_the_sealed_evaluator`).

So sealed scores are independent estimates for artifacts **selected without them**. Validation scores are not independent: every submission returned one bit about the validation set.

### Information paths from final evaluation to an agent

| Path | Status |
|---|---|
| World state, observations, memories, `dev_notes` | Contain no sealed seed, case or score (tested) |
| Freeze records | Contain validation-based selections only |
| Sealed module | Not importable from the world path. Its manifest file is outside world state, and no controller has file access. |
| Results | Written only to `evidence/v0.4.0/cumulative/sealed-results.json` after all runs close. No run reads them. |

### Bounds

For a given world and case set, the minimum pooled ratio over *per-case* decisions (Dinkelbach's method over all 64 decisions per case) is a lower bound for every program. It is about 4.3–4.9 across the seeds checked; `test_oracle_lower_bound_is_not_beaten_by_any_program` checks it. The baseline scores about 13–16.

### Search and composition

The declared neighbourhood is:

- field recombination from another held workflow (`composition`, recorded with `sources`)
- constant ±1
- threshold ±1
- splitting a leaf on `phase`, `humidity`, `ore` or `energy` at fixed thresholds

Components (`component{field, expr}`) and `call` are enforced prerequisites: execution, teaching acceptance and proposals all require holding the called component. Under v0.4 rules the offline researcher composed by recombining fields and did not create components. v0.5 activates them (below).

## v0.5: credits, beam search and live components (`workshop-evaluator-2` · `workshop-sealed-2`)

### Search credits and diagnostics

With `budget_unit: credits`, every proposal, development test (including a component test) and submission spends 1 credit from a single per-lifetime pool of 48. A rejected action spends nothing. Every decision of the offline researcher records a diagnostic: the step, operator, parent, remaining budget and, when it does not search, the stop reason (`budget-exhausted`, `energy` or `no-candidate`). The reducer turns these into stop-reason counts and per-operator admission rates.

### Private stepping stones

A proposal may name one of the agent's own development-tested workflows as its parent. Admission compares against the **nearest admitted ancestor** (skipping private stepping stones), or the baseline rule when there is none. Others never see private candidates.

### The beam policy

The frontier holds the agent's best 4 own development-tested workflows and held admitted workflows; the baseline appears only when nothing else exists. The policy rotates over frontier members, expands neighbours not yet tried, orders operators by the agent's own success rates once it has 6 trials, and restarts by recombination after 4 consecutive non-improving tests. It submits when the development score beats the best held admitted workflow by 3%, and it submits behaviour-preserving refactors (below). It uses only permitted information: its own development results, its private history, held artifacts and held components. `beam-nocomponents` is the same policy without component operators.

### Components

| Operation | Rule |
|---|---|
| **Extract** (`extract:<field>`) | A component equal to a non-constant field of a held admitted workflow. This is refactoring, not discovery. |
| **Test** | Inside a host: a held admitted workflow with the component's field replaced by a call. The development result records the host's score with and without the component, and whether behaviour is identical on every development case. |
| **Admit (no parent)** | Admitted if the host with the component scores no worse than the host on validation. |
| **Revise** (`mutate-component`) | A neighbouring expression with the old component as parent. Admitted only if the host with it is strictly better than the host with the parent. It supersedes the parent, but workflows that call the parent keep calling the parent's hash. |
| **Call** (`call:<field>`) | A workflow whose field is replaced by a call to a held admitted component. If its decisions are identical to its admitted parent on every validation case, it may pass the declared **refactor admission path** (`admission_path: refactor`, no improvement claimed). Otherwise strict improvement applies. |
| **Closures** | Proposals, execution, teaching and freezes resolve the transitive closure by hash. The inlined closure must respect the global limits (48 nodes, depth 6, 64 shared steps), and interfaces must match. Missing dependencies and cycles are rejected. |

### Final evaluation

`workshop-sealed-2` is a new protected manifest (OS-drawn seed) whose 48 cases exclude development, validation and every `workshop-sealed-1` case. The exclusion is verified against sealed-1's commitment. Its commitment was written into the frozen protocol before any evaluation run. Sealed scoring verifies every frozen artifact and its closure by hash.

## v0.5.1: submission contract, exact novelty, panels (`workshop-evaluator-3` · `workshop-sealed-3`)

- **Submission contract.** A submission is judged against its candidate's reference: the nearest admitted ancestor, skipping private stepping stones.
  - If the reference is no longer admitted, the submission is rejected with the stale reference and its successor named, at no credit or energy cost.
  - `reference` lets a submitter state the reference it expects (compare-and-swap).
  - `withdraw_artifact` (free) retires a pending candidate. A rebase is an ordinary, fully charged proposal against a current head.
  - Child and reference are always re-scored on the same current cases; nothing is relabelled.
- **Exact decision novelty** (used only by `beam-alloc`). Two workflows are equivalent when, for every field, their expressions agree at one point per threshold interval.
  - Programs compare measures only through `measure < threshold`, so this decides equality for every integer input. It is not equality on the 24 development cases, which would be a sample.
  - The check uses no task cases, outcomes or hidden parameters. Its work is recorded as point evaluations.
- **Admission panels** (`validation_policy: cohort-panels`, experiment deferred). A precommitted 24-case panel per cohort, disjoint from development, validation and every other panel, with a per-agent query allowance. Freezes re-score on the active panel.
- **`workshop-sealed-3`.** 48 cases disjoint from development, validation, sealed-1, sealed-2 and all ten panels, committed in the frozen M5b protocol before any evaluation run.

## v0.5.2: shared final selection (`workshop-evaluator-4` · `workshop-sealed-4`)

- **Selection.** With `final_selection: selection-panel`, each freeze scores the newest 16 or fewer admitted or superseded workflows held by the cohort on one shared 24-case `selection-0` panel, and freezes the lowest as `selection_panel_best`.
  - The panel is disjoint from development, validation and the ten admission panels.
  - It is observer-side, never shown to agents, and counted (`selection_accounting`).
  - The same rule applies under fixed admission and under cohort panels, so champions are comparable across admission policies. Admission scores from different panels are never compared.
  - The selection panel is selection-used, not a final test.
- **Final evaluation.** `workshop-sealed-4` (48 cases) is disjoint from development, validation, sealed-1 to sealed-3, the ten admission panels and `selection-0`. It is committed in the frozen M5c protocol before any evaluation run.
