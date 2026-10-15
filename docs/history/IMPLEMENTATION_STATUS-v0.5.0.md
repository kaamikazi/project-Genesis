# Implementation status, v0.5.0 (2026-10-15)

Engine `0.5.0` · rules `phase-world-5` · evaluators `phase-evaluator-3` (legacy), `workshop-evaluator-2`, `workshop-sealed-2` · reducer `genesis.reducer/2` · storage schema 1.

- **Evidence:** [`evidence/v0.5.0/`](../../evidence/v0.5.0/README.md). The generated tables are in [SUMMARY.md](../../evidence/v0.5.0/SUMMARY.md).
- **Design decisions:** [ADR-005](../ADR-005-search-components-mentorship.md)
- **Previous status (v0.4.0):** [history/IMPLEMENTATION_STATUS-v0.4.0.md](IMPLEMENTATION_STATUS-v0.4.0.md). v0.4.0 is preserved as a tag.
- **Baseline before this milestone:** [audit/baseline-v0.4.0-verification.md](../audit/baseline-v0.4.0-verification.md) (104 passed, build OK)
- **Why v0.4 search stalled:** [audit/v0.4-search-diagnosis.json](../audit/v0.4-search-diagnosis.json)

## Verification at release

| Check | Result |
|---|---|
| `python -m pytest -q` | **125 passed** (up from 104): 19 new tests in `tests/test_v05.py` and 2 new copy-on-write scenarios |
| `npm run build` (with `tsc --noEmit`) | Succeeded |
| `python tools/generate_evidence_m5.py` | All 10 steps exited 0 |
| Mid-pipeline runtime edit | All 40 experiment worlds re-run from the clean commit: identical record hashes and final states. See the evidence README. |
| Restart during overlap mentorship and during search | 8 of 8 checks pass |
| v0.4.0 experiment-B world under v0.5 defaults | Reproduces its stored reducer output (`test_v040_cumulative_world_reproduces_under_v050_defaults`) |

## Works and is verified

| Capability | Tests / evidence |
|---|---|
| **Shared search credits.** Proposals, development tests, component tests and submissions draw on one per-lifetime pool, and exhaustion changes nothing. | `test_search_credits_are_one_shared_pool_and_exhaustion_changes_nothing`; reducer search actions reconcile with `search_spent` in every world |
| **Decision diagnostics** (operator, parent, step, stop reason, remaining budget) are kept out of world state, with no wall time and no non-finite numbers | `test_beam_decisions_record_diagnostics_with_operators_and_stops` |
| **Beam policy and restricted feedback.** No validation scores, sealed data or hidden parameters reach controllers. | `test_beam_observations_carry_no_validation_sealed_or_hidden_parameters` |
| **Components.** Extraction preserves behaviour on every case; closures are transitive and ordered; missing dependencies, cycles, non-component calls and interface mismatches are rejected; splitting a program across components grants no extra depth; calls resolve by immutable hash after a revision. | `test_extraction_*`, `test_closure_*`, `test_splitting_*`, `test_engine_rejects_calls_*`, `test_calls_resolve_by_immutable_hash_*` |
| **Dependency-aware teaching.** Strict mode rejects missing prerequisites; package mode teaches them, with work accounted per dependency. | `test_strict_policy_rejects_missing_prerequisites_and_package_policy_teaches_them` |
| **Overlapping generations.** Arrival, then retirement on schedule, never delayed by an unfinished lesson; no hidden inheritance; physical parity until the first arrival. | `test_retirement_is_not_delayed_*`, `test_overlap_lifecycle_*`, `test_library_and_none_are_physically_identical_*`; parity held in every evaluation seed |
| **Sealed-2 isolation.** Disjoint from development, validation and sealed-1; tampering is detected; frozen closures are verified by hash before scoring. | `test_sealed2_*`, `test_frozen_closures_*`, `test_no_world_path_module_imports_the_sealed_evaluator` |
| **Reducer v2** reconciles search, components, sessions and transition phases | `test_reducer_reconciles_search_components_and_sessions` |
| **Copy-on-write** equals the full copy with beam search, components, package lessons and overlap (one scenario fuzzed) | `tests/test_optimization.py` (10 scenarios) |
| **Restart and replay** during overlap mentorship and during search | `test_restart_during_overlap_*`, `evidence/v0.5.0/verification/restart.json` |
| **The full component path** (extract → admit in host → refactor → package lesson during overlap → retirement → successor execution → admitted revision → rewired workflow) | Scripted, labelled demonstration: `test_demonstration_chain_*`, `evidence/v0.5.0/demonstration/component-chain.json` |

## Results

Exploratory: 5 new evaluation worlds (seeds 201–205), offline designed controllers, and a claim rule frozen before running (a direction counts only if it holds in at least 4 of 5 paired seeds). Scores are pooled cost per alloy on held-out cases; **lower is better**. "Final held best" is the best admitted workflow held by the final cohort's members at the closing freeze, selected by validation.

### Experiment P: search policy under the same credit pool

Physical parity held on the initial state in all 5 seeds, and access parity at the first boundary for both policies. There were no failures.

| Seed | Sealed baseline | first-improvement preserved (val / sealed) | first-improvement reset | beam preserved | beam reset | beam without components, preserved |
|---|---|---|---|---|---|---|
| 201 | 13.79 | 7.31 / 9.98 | 7.68 / 9.00 | 7.54 / 8.33 | 7.89 / 8.34 | 7.55 / 9.25 |
| 202 | 14.18 | 8.60 / 10.48 | 9.34 / 9.39 | 8.29 / 10.50 | 10.44 / 13.27 | 8.29 / 10.50 |
| 203 | 14.92 | 6.29 / 9.02 | 7.42 / 8.24 | 7.24 / 8.15 | 10.75 / 14.26 | 7.24 / 8.15 |
| 204 | 13.32 | 7.36 / 8.11 | 9.04 / 9.40 | 9.19 / 10.56 | 8.58 / 8.90 | 9.03 / 16.11 |
| 205 | 14.26 | 7.59 / 10.29 | 8.10 / 7.57 | 9.70 / 10.20 | 10.77 / 11.79 | 9.70 / 10.20 |
| **mean** | | **7.43 / 9.58** | **8.32 / 8.72** | **8.39 / 9.55** | **9.69 / 11.31** | **8.36 / 10.84** |

**Beam search is not stronger.**

- **Validation:** first-improvement was better in 4 of 5 seeds under both preserved and reset access.
- **Sealed, preserved:** no consistent difference (beam lower in 3, first-improvement in 2; means 9.55 vs 9.58).
- **Sealed, reset:** no consistent difference by the claim rule (first-improvement lower in 3 of 5), but the mean favours first-improvement (8.72 vs 11.31).
- **Component operators:** removing them made no consistent difference (validation: 1 better, 1 worse, 3 ties).

**Preserved access looked better than reset on validation in 5 of 5 seeds, but was worse on sealed in 4 of 5** (first-improvement; means 9.58 vs 8.72). Lineages that build on inherited workflows were admitted again and again against the same 24 adaptive validation cases. Their sealed scores sit 2.15 above validation on average, against 0.40 for reset lineages.

This repeats, more strongly, the v0.4 warning: validation-selected improvement across generations does not reliably transfer to fresh cases. For beam the ordering held (preserved better than reset on sealed in 4 of 5).

### Search diagnosis (P, preserved access; all 30 researcher lifetimes per condition)

| Measure | first-improvement | beam | Difference |
|---|---|---|---|
| Credits spent / available | 1,423 / 1,440 | 1,375 / 1,440 | beam left 48 more unspent (max 6 in any lifetime) |
| Allocation: proposals · own-candidate tests · re-tests of held · component tests · submissions | 630 · 630 · 20 · 0 · 143 | 620 · 575 · 18 · 38 · 124 | beam left **45 proposals never tested** and spent 38 credits on component tests |
| Novel evaluations (own-candidate tests with decisions new to the agent) | 499 (79% of own tests) | 349 (61%) | **−30%** |
| Repeated evaluation results (a different program with the same decisions on all 24 development cases) | 131 | 226 | **+73%** |
| Novel evaluations per 100 credits | 35.1 | 25.4 | −28% |
| Duplicate programs (identical content proposed again by the same agent) | 0 | 0 | none in either |
| Energy pauses | 24 one-tick pauses, all followed by more search | 84 one-tick pauses followed by more search; 10 one-tick pauses at the end of a lifetime | no sustained inability to act in either |
| Admitted / submitted | 76 / 143 (53%) | 43 / 124 (35%; 39 improvements + 4 refactors) | |
| Final held best: development / validation / sealed (means) | 8.09 / 7.43 / 9.58 | 8.81 / 8.39 / 9.55 | |

The budget was matched in total, but **allocation was not equivalent**. With almost the same number of credits, beam produced 150 fewer novel evaluations. It spent credits on untested proposals and component tests, and its own-candidate tests repeated already-seen behaviour far more often. The many "energy" stop reasons were transient one-tick pauses, not a binding constraint.

Explanations **not established** by this design (hypotheses):

- **H1:** frontier rotation and recombination generate behaviourally redundant neighbours, because frontier members are similar to each other.
- **H2:** choosing among more development-evaluated stepping stones selects candidates that overfit the 24 development cases (a winner's curse). This would explain the lower admission rate.
- **H3:** the validation advantage of first-improvement is partly adaptive overfitting. On sealed cases the two policies tie under preserved access.

Each is testable in a follow-up (below).

Beam/preserved also produced less alloy (1,560 against 2,217 for first-improvement/preserved). This is **not explained** by these analyses.

### Inherited-parent improvements (post-hoc sealed diagnostic)

These are submissions whose admission reference was created by an earlier cohort. The sealed scores of non-frozen artifacts were computed after every run closed and are labelled post-hoc.

| Condition | Submissions against an inherited reference | Admitted as improvements | Of those, better on sealed | Not better on sealed |
|---|---|---|---|---|
| P first-improvement / preserved | 44 | 16 | 11 | 5 |
| P beam / preserved | 27 | 9 | 8 | 1 |
| P beam without components / preserved | 22 | 9 | 6 | 3 |
| T library | 29 | 9 (+1 refactor) | 9 | 0 |
| T teaching-only | 3 | 1 (+1 refactor) | 1 | 0 |

**Further improvement beyond all earlier-generation work** is a corrected, post-hoc metric. It compares cohort k's own best with the best workflow any earlier cohort produced. Results by condition (10 transitions each):

| Condition | Beat earlier work on validation | Also on sealed |
|---|---|---|
| P first-improvement / preserved | 9 | 6 |
| P first-improvement / reset | 3 | 3 |
| P beam / preserved | 5 | 5 |
| T library | 7 | 6 |
| T teaching-only | 6 | 5 |
| T none | 6 | 5 |

Why the frozen metric was corrected: with library access during the overlap, seniors adopted juniors' workflows, so "the previous cohort's held best" sometimes contained the current cohort's own work.

### Experiment T: teaching across overlapping generations

Library and none were physically identical at the first arrival in all 5 seeds. There were no failures.

| Seed | library (val / sealed) | teaching-only | none | Cross-generation lessons in teaching-only (acquired / failed / interrupted) |
|---|---|---|---|---|
| 201 | 7.21 / 8.21 | 7.89 / 8.34 | 7.89 / 8.34 | 7 (3 / 1 / 3) |
| 202 | 8.28 / 9.39 | 10.44 / 13.27 | 10.44 / 13.27 | 12 (3 / 4 / 5) |
| 203 | 7.24 / 8.15 | 7.24 / 8.15 † | 10.75 / 14.26 | 9 (5 / 3 / 1) |
| 204 | 9.17 / 10.29 | 8.58 / 8.90 | 8.58 / 8.90 | 9 (4 / 2 / 3) |
| 205 | 9.70 / 10.20 | 7.97 / 9.09 † | 10.77 / 11.79 | 12 (7 / 2 / 3) |
| **mean** | **8.32 / 9.25** | **8.42 / 9.55** | **9.69 / 11.31** | **49 (22 / 12 / 15)** |

† The final cohort held a cohort-1 workflow acquired **by teaching**.

**Knowledge crossed generations by teaching, but it was retention, not further improvement.**

- **Library vs none:** library beat none in 4 of 5 seeds on both validation and sealed. This is despite a controller defect that handicapped the library condition (evidence README: stale-reference re-submissions, 209 wasted turns in 7 lifetimes).
- **Teaching-only vs none:** no consistent difference. Teaching-only was better in 2 seeds and identical in 3. In those 2 seeds (203, 205) the only difference was that teaching carried cohort 1's better workflow to cohort 2, which then created nothing better. Teaching-only produced 1 admitted improvement on an inherited reference in all 5 worlds; library produced 9.
- **Lesson outcomes** (49 cross-generation lessons):
  - 22 acquired.
  - 12 failed: a practice run was costlier than the baseline under the learner's conditions.
  - 15 interrupted: 13 by scheduled retirement, 2 by stalling.
- **Dependency teaching:** 4 cross-generation lessons carried a component dependency. All 4 were interrupted by the teacher's scheduled retirement, so **no dependency was acquired by teaching in any experiment world**. Only the scripted demonstration completes that path.
- **Teaching costs** (teaching-only, 5 worlds): 450 teacher energy, 190 learner instruction energy, and 936 practice energy (practice is real production). There were 450 energy of lesson-request messages, against 40–64 exchange energy in the other conditions. Total alloy was 2,401, against 2,801 (library) and 2,705 (none).
- **T/none vs P/beam-reset:** every freeze pick in T/none is identical to P/beam-reset, although the overlap changed timing. Without transfer, a cohort's search outcome here appears independent of when the cohort starts. That is a hypothesis about determinism of private search sequences, not tested directly.

### Costs and performance

- **Controller CPU per proposal decision** (`benchmark/search-cpu.json`, seeds 300–301): first-improvement 17.5 ms mean (p95 28.1), beam 16.5 ms (p95 36.7), beam without components 17.1 ms (p95 35.3). All policies take about 8.7 s per 180-tick world.
- **Tick time with every v0.5 feature active** (cohorts with a 20-tick overlap, beam, credits, package lessons): 8 agents 87.4 ± 2.9 ms (12.6 ticks/s); 20 agents 172.6 ± 4.9 ms (6.6 ticks/s). The population doubles during overlaps. **20 agents is now below the UI's 10 ticks/s.** State copying is 61–70% of profiled step time.
- **Evidence generation:** 30 minutes in total. Experiment worlds took about 20–28 s each including replay verification.

## Not implemented / limitations

- **Beam is not a stronger search** in this task and budget. The comparison does not support calling it stronger.
- **Known defect:** beam does not check that a pending submission's admission reference is still current. It livelocked in T/library and was left unfixed in this release (evidence README).
- **Dependencies were never acquired by teaching in the experiments.** Lessons that carried components were all cut off by scheduled retirement.
- **Validation is adaptive and reused across generations,** and it increasingly overstates preserved lineages. Only sealed-2 scores are independent: frozen artifacts in the protocol, and the labelled post-hoc diagnostic.
- **Five worlds per condition is a smoke test.** Agents within a world are not independent. No significance test is claimed.
- **LLM controller:** not implemented. It needs your choice of provider and budget.
