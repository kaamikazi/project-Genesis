# Implementation status, v0.5.1 / M5b (2026-10-16)

Engine `0.5.1` · rules `phase-world-5.1` · evaluators `phase-evaluator-3` (legacy), `workshop-evaluator-3`, `workshop-sealed-3` · reducer `genesis.reducer/3` · metrics `genesis-metrics-1` · storage schema 1.

- **Evidence:** [`evidence/v0.5.1/`](../../evidence/v0.5.1/README.md); generated tables in [SUMMARY.md](../../evidence/v0.5.1/SUMMARY.md); metric definitions in [METRICS.md](../METRICS.md)
- **Decisions:** [ADR-006](../ADR-006-repair-allocation-mentorship.md)
- **Baseline and reproductions before any change:** [audit/baseline-v0.5.0-verification.md](../audit/baseline-v0.5.0-verification.md)
- **Previous status:** [v0.5.0](IMPLEMENTATION_STATUS-v0.5.0.md) and [v0.4.0](IMPLEMENTATION_STATUS-v0.4.0.md). v0.5.0 and its evidence are preserved unchanged; its results were produced **with the defects listed below**.

## Verification

| Check | Result |
|---|---|
| `python -m pytest -q` | **148 passed**: 21 new v0.5.1 tests and 2 new copy-on-write scenarios, one fuzzed with withdrawals and named references |
| `npm run build` (with `tsc --noEmit`) | Succeeded |
| `python tools/generate_evidence_m5b.py` | All 21 steps exited 0, from runtime commit `1e7dcad`, which was clean at the start and the end |
| Reporting fix after generation (`e20e84e`) | The reducer's freeze copy omitted `created_upto_best`, which left creation-attributed validation values empty. Fixed. Only the summaries step was regenerated; runs and exports are unaffected. |
| Restart with a pending submission and during mentorship | 8 of 8 checks pass |
| v0.4.0 experiment-B world under current defaults | Reproduces its stored reducer output |

## Defects found and repaired

Each repair is shown on minimal reproductions run against tag v0.5.0 and the current code (`evidence/v0.5.1/bugfix/`). Rejected actions per 10 ticks:

| Defect | v0.5.0 | v0.5.1 |
|---|---|---|
| Beam resubmitted a candidate whose reference had been superseded | 10 of 10 | 0 |
| first-improvement kept revising a superseded workflow | 10 of 10 | 0 |
| A library copy of a component-calling workflow did not copy its component, so every execution failed | 5 of 5 | 0 |

**Repairs:**
- An explicit submission contract: the reference is shown, can be named in the submission (compare-and-swap), and conflicts are reported with their cause.
- A free `withdraw_artifact` action.
- Controllers withdraw a stale candidate instead of resubmitting it.
- first-improvement revises only a currently admitted workflow.
- Library copies bring the missing dependency closure, charged separately, or are refused.

**What the defects did to v0.5.0** (raw evidence unchanged; analysis in `corrections-v0.5.0/` and `production/`):

- **Missing-component rejections.** v0.5.0 beam/preserved made 1,390 production attempts that were rejected for a missing component. Against first-improvement/preserved it produced 657 less alloy, which the identity *alloy = actions × yield* splits into −542 from fewer production actions and −115 from lower yield. Other component-using conditions had 356–903 such rejections; beam-nocomponents had none.
- **Stale resubmissions.** In T/library, 209 resubmissions against a superseded reference were rejected, in 7 of 30 researcher lifetimes.
- **Repaired retrospective rerun** (all 40 v0.5.0 worlds, labelled retrospective):
  - beam/preserved alloy rose from 1,560 to 2,230 (first-improvement: 2,217), and its search outcomes were unchanged.
  - T/library stale rejections fell from 209 to 1 (a same-tick race, then a single withdrawal).
  - T/library's final held-best sealed-2 mean moved from 9.25 to 9.29. Sealed-2 is retrospective here, because those cases were already known.

## Corrected measurements

`genesis-metrics-1` defines every counter: units, inclusion rules and event sources. The v0.5.0 counters were reconciled against it:

| v0.5.0 statement | Status | Correct value (beam/preserved) |
|---|---|---|
| "45 proposals were never tested" | **Defect** in the narrative arithmetic: component proposals are tested by component tests | **7** never tested, all within 5 ticks of retirement |
| 226 "repeated evaluation results" (diagnosis) vs 259 "duplicate behaviour" (summary) | Intentional, different scopes | `repeated_decisions_own` = 213 (own-candidate tests only); `repeated_decisions_world` = 236 (world scope, component tests excluded) |
| 6 "cross-generation admitted revisions" vs 9 "inherited-reference admissions" | Intentional: immediate parent (refactors included) vs admission reference | `improvements_on_earlier_cohort_parent` = 5; `improvements_on_earlier_cohort_reference` = 9 |

- **Paired comparisons** now report expected, eligible and missing worlds and the denominator. Example: v0.5.0's "final cohort best, sealed: 0 / 1 / 0" for beam vs first-improvement had **1 eligible pair of 5**. In the other 4 worlds beam's final cohort created no admitted workflow.
- **Further improvement is now attributed by creation event.** Freezes record what earlier cohorts had *created* by the boundary, so seniors adopting juniors' work cannot change it.

## Prospective results

The protocol was frozen before evaluation (`evidence/v0.5.1/protocol/protocol.json`), with fresh seeds 221–226 and sealed-3 cases committed in advance. Scores are cost per alloy, so **lower is better**. "Held best" is the best admitted workflow held by the final cohort, selected by validation. Claim rule: at least 75% of expected worlds are eligible pairs, and one side is lower in at least 75% of them (descriptive).

> **Sample-size caveat found after the runs.** Hidden world parameters have only 45 combinations, and every world uses the same controller seed. Invention outcomes depend on those two things, not on terrain or timing. Seeds 221 and 222 share parameters, as do 225 and 226, and they produced **identical** invention outcomes. The frozen comparisons below therefore count 6 worlds of which only **4 are distinct**. Each row also gives the post-hoc result over the 4 distinct worlds. Teaching interactions do differ between duplicate seeds, because terrain affects movement.

### Allocation experiment (repaired beam vs beam + allocation bundle)

| Seed | beam pres. (val / sealed) | beam reset | beam-alloc pres. | beam-alloc reset | first-impr. pres. | first-impr. reset |
|---|---|---|---|---|---|---|
| 221 (= 222) | 8.89 / 10.57 | 8.21 / 9.95 | 8.21 / 11.22 | 11.68 / 13.45 | 6.03 / 9.58 | 7.65 / 10.82 |
| 223 | 9.04 / 11.09 | 8.33 / 10.37 | 8.33 / 11.61 | 11.89 / 14.08 | 6.13 / 9.95 | 7.77 / 11.38 |
| 224 | 9.56 / 10.82 | 8.94 / 11.20 | 8.56 / 10.86 | 10.47 / 12.11 | 8.21 / 10.31 | 9.35 / 12.98 |
| 225 (= 226) | 9.19 / 10.16 | 8.58 / 10.23 | 9.34 / 10.71 | 10.09 / 11.68 | 7.36 / 9.41 | 9.04 / 11.98 |
| **mean of 6 frozen worlds (sealed)** | **10.56** | **10.32** | **11.05** | **12.74** | **9.71** | **11.66** |

**The allocation bundle made the repaired beam worse.**

- **Primary contrast, sealed-3:** plain beam was lower in 6 of 6 frozen worlds (4 of 4 distinct), both with preserved access (10.56 vs 11.05) and reset access (10.32 vs 12.74).
- **Validation, preserved access:** no consistent difference (bundle lower in 4 of 6).
- **First-improvement** beat both beams on preserved sealed-3 in 6 of 6.
- **Preserved vs reset access:** preserved was better on sealed-3 for every policy (6 of 6). For first-improvement this is the opposite of v0.5.0, where reset beat preserved on sealed-2 in 4 of 5. The two small studies disagree; neither generalises.

What the bundle did, from the counters (6 worlds each, preserved / reset):

| Counter | beam | beam-alloc |
|---|---|---|
| Credit actions | 1,653 / 1,674 | 1,543 / 1,515 |
| Repeated development decisions (own) | 211 / 216 | **100 / 133** |
| Untested proposals | 4 / 6 | **0 / 0** |
| Candidates skipped by exact novelty | — | 481 / 191 |
| Reserve stops | — | 43 / 47 |
| Withdrawals of stale-lineage candidates | 0 / 0 | **102 / 159** |
| Improvement admissions | 54 / 94 | 55 / 85 |

The bundle did what it was designed to do: fewer repeated behaviours and no untested proposals. It also spent 110–160 fewer credits, and it withdrew 102–159 private stepping stones whose reference had changed. Those stepping stones were ones the plain beam kept expanding.

Which guard caused the loss is **not identified**. The design measures the bundle as a whole. Hypotheses:
- **H1:** withdrawing stale stepping stones removed useful frontier members.
- **H2:** reserve stops left budget unspent.
- **H3:** novelty skipping changed which neighbours were tried, without making them better.

A predeclared ablation would be needed to separate them.

### Mentorship experiment (schedule 80/40, chosen in calibration: 60/30 produced no dependency lessons)

| Seed | library (val / sealed) | teaching-only | none | Dependency lessons acquired / offered | Executions of taught dependency workflows after the teacher retired |
|---|---|---|---|---|---|
| 221 | 8.89 / 10.57 | 8.21 / 9.95 | 8.21 / 9.95 | 3 / 5 | 83 |
| 222 | 8.89 / 10.57 | 8.21 / 9.95 | 8.21 / 9.95 | 2 / 3 | 61 |
| 223 | 9.04 / 11.09 | 8.33 / 10.37 | 8.33 / 10.37 | 2 / 6 | 59 |
| 224 | 9.66 / 10.77 | 8.94 / 11.20 | 8.94 / 11.20 | 0 / 4 | 0 |
| 225 | 9.03 / 9.11 | 8.58 / 10.23 | 8.58 / 10.23 | 0 / 2 | 0 |
| 226 | 9.03 / 9.11 | 9.19 / 10.16 | 8.58 / 10.23 | 1 / 6 | 30 |

**Dependency teaching now works in exploratory worlds, but it did not change outcomes.**

- **Dependency lessons:** 26 offered, 8 acquired, carrying 8 components in 4 of 6 worlds. Learners executed the taught component-calling workflows 233 times after their teachers had retired: real, independent use.
- **Eligibility:** 8 of 12 cohort transitions had a senior component-calling workflow, so an opportunity existed.
- **All cross-generation lessons:** 90 in total, of which 28 were acquired, 34 failed practice and 28 were interrupted.
- **Final outcome:** teaching-only matched no-transfer's final held best in 5 of 6 worlds (4 of 4 distinct identical). Teaching's acquisitions did not end up as the final cohort's best.
- **Library vs none:** no consistent difference on sealed-3 (3 vs 3); none was lower on validation in 6 of 6.
- **Further improvement** (creation-attributed, 12 transitions per condition): sealed-3 improvement in 10 transitions (library), 11 (teaching-only) and 12 (none). No transfer route improved on independent re-search.
- **Cost:** teaching-only produced 868 less alloy than none (identity: −819 from fewer production actions).

## Costs and performance

- **Controller CPU per proposal decision** (seeds 310–311, `benchmark/search-cpu.json`):

  | Policy | Mean (ms) | p95 (ms) |
  |---|---|---|
  | beam | 15.2 | 29.9 |
  | first-improvement | 23.7 | 38.5 |
  | beam-alloc | 27.1 | **102.2** |

  The novelty check is cheap on average, but its tail is long.
- **Population.** Base population is 8 or 20; overlap doubles active agents to 16 or 40 for the overlap window.
- **Achieved speed through the real server clock** (target 10 ticks/s, durability unchanged). Pacing is now fixed-rate and the UI shows target vs achieved. Two measurements on the same commit:

  | Base agents | Active agents | Pipeline run (ticks/s) | Repeat (ticks/s) |
  |---|---|---|---|
  | 8 | 8 | 9.9 | 9.8 |
  | 8 | 16 (overlap) | 4.8 | 6.7 |
  | 20 | 20 | 5.8 | 8.5 |
  | 20 | 40 (overlap) | 3.0 | 4.1 |

  The spread shows machine-state sensitivity. Before the pacing fix the clock waited a full 1/speed after each step, so even a fast engine fell short of the target.
- **Profile with every feature on** (cohorts 50/25, beam-alloc, scheduled mentorship): 8 base agents 145.8 ms/tick (7.2 ticks/s); 20 base agents 187.7 ms/tick (5.6 ticks/s). State copying still dominates. No optimisation was attempted in this release.

## Not implemented, limitations and uncertainty

- **Independence of worlds.** A constant controller seed and only 45 hidden-parameter combinations make some seeds duplicates for invention measures. Every M5b invention comparison rests on 4 distinct worlds. Agents and transitions within a world are not independent.
- **Admission-panel experiment:** infrastructure only, deferred.
- **Allocation bundle:** its per-guard effects are not identified.
- **Teaching evidence** shows mechanics and use, not benefit. Final selections were unchanged.
- **LLM controller:** not implemented; it needs your choice of provider and budget.
