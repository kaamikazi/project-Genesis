# Implementation status, v0.4.0 (2026-10-15)

Engine `0.4.0` · rules `phase-world-4` · evaluators `phase-evaluator-3` (legacy), `workshop-evaluator-1`, `workshop-sealed-1` · storage schema 1.

- **Evidence:** [`evidence/v0.4.0/`](../../evidence/v0.4.0/README.md)
- **v0.3.0:** preserved as tag `v0.3.0`, with its evidence in `evidence/v0.3.0/`
- **Baseline before this milestone:** [audit/baseline-v0.3.0-verification.md](../audit/baseline-v0.3.0-verification.md) (70 passed, build OK)

## Verification at release

| Check | Result |
|---|---|
| `python -m pytest -q` | **104 passed** (up from 70) |
| `npm run build` | Succeeded |
| `python tools/generate_evidence_m4.py` | All 8 steps exited 0. The log is in `evidence/v0.4.0/runs.json`, with the source fingerprint at the start and end. |

## Works and is verified

| Capability | Evidence |
|---|---|
| Development, validation and sealed evaluation roles. Development returns per-case results; validation returns one admission bit; sealed scores only frozen artifacts of closed runs. | `tests/test_workshop.py`, `tests/test_sealed_cohorts.py`. The isolation tests cover the import graph, absence from world state, absence from observations including validation records, a monkeypatched sealed scorer never being called in-run, the closed-run requirement, and the commitment check. |
| Freezes select by validation evidence at each cohort boundary and when the run closes | `test_freeze_selects_by_validation_before_any_final_score` |
| `workshop-1`: interacting decisions, hidden per-world parameters, busy time, flux and food accounting, component prerequisites, bounded interpreter | `test_decisions_interact`, `test_malformed_programs_are_rejected`, `test_interpreter_bounds_nodes_depth_and_steps`, `test_flux_workflow_conserves_resources_and_sets_busy_time`, `test_oracle_lower_bound_is_not_beaten_by_any_program` |
| Teaching sessions: teacher must hold the skill; flag-gated; atomic per-role costs; reservations; acquisition only after a practice assessment; failure on missing prerequisites; interruption on retirement or stall; first independent use recorded separately; no alternate transfer paths | `tests/test_teaching.py` (9 tests) |
| Replay and restart during an active lesson | `test_replay_and_restart_during_an_active_lesson`, and `evidence/v0.4.0/verification/restart-teaching.json` (4/4 checks) |
| Cohort lifecycle: everyone retires, roles and homes are kept, inventory moves to storage, no inherited memories; reset hides earlier cohorts (inspection by ID is rejected); preserved shows them; parity until the first boundary | `tests/test_sealed_cohorts.py` |
| The reducer reconstructs sessions (outcome, practice, per-role costs), cohorts, freezes and the cross-generation lineage, and reconciles holdings and statuses | `test_reducer_reconstructs_teaching_sessions_and_cohorts`, plus reconciliation checked in every experiment world |
| Copy-on-write equals the full-copy reference in workshop, teaching and cohort worlds, with fuzzed actions of every kind | `tests/test_optimization.py` (8 scenarios). This caught a real sharing bug (`practice_step` mutated an uncopied artifact), which was fixed before any evidence was generated. |
| v0.3.0 scenarios reproduce under v0.4.0 rules | `test_v030_scenarios_reproduce_under_v040_rules` compares against the stored v0.3.0 reducer output |

## Results (exploratory, 5 evaluation seeds, offline designed controllers)

### Experiment A: teaching and acquisition

20 continuations; physical parity at the boundary in all 5 seeds; no failures.

| Condition | Acquired | Median ticks to acquisition | Used with a saving | Successor production energy per alloy (pooled) | Settlement charged energy per alloy (mean of worlds) | Failed lessons | Teaching energy (teacher / learner) |
|---|---|---|---|---|---|---|---|
| teaching | 10/10 | 14.5 | 10/10 | 5.33 | 6.56 | 3 (all retried and then acquired) | 91 / 225 |
| library | 10/10 | 2 | 10/10 | 5.66 | 6.52 | — | — |
| no-transfer | 0/10 | — | 0/10 | 8.60 | 7.06 | — | — |
| direct-control | 10/10 (package) | 0 | 10/10 | 5.51 | 6.40 | — | — |

**Teaching works, and it is slower than the library at about the same total cost.**

- **Speed:** acquisition took a median 14.5 ticks against 2 for the library.
- **Why lessons failed:** all 3 failed lessons had a practice run costlier than the baseline under the learner's local conditions. For example, seed 42: 15.0 against 14.0 per alloy. The retries passed.
- **Opportunity cost:** teachers spent 4 ticks and 7 energy per lesson.
- **What the learner figure includes:** the learner's 225 energy includes its real practice production.

### Experiment B: cumulative invention

10 worlds (5 seeds × preserved/reset), 3 cohorts of 60 ticks; parity at the first boundary in all seeds; no failures; 2,244–2,396 ore left, so no depletion.

| Seed | Sealed baseline | Preserved: final best (validation / sealed) | Reset: final best (validation / sealed) |
|---|---|---|---|
| 11 | 13.43 | 7.26 / 9.33 | 8.72 / 9.88 |
| 42 | 16.06 | 7.16 / 9.98 | 6.91 / 9.09 |
| 77 | 14.90 | 8.60 / 10.20 | 10.15 / 11.45 |
| 5 | 12.63 | 6.00 / 7.54 | 7.75 / 10.04 |
| 23 | 13.05 | 6.51 / 8.26 | 7.06 / 8.21 |
| **mean of worlds (sealed)** | | **9.06** | **9.73** |

"Final best" is the best accessible admitted workflow at the closing freeze, chosen by validation score. Lower is better.

**What this does and does not show:**

- **Preserved knowledge helped in 3 of 5 worlds on sealed cases** (11, 77 and 5). It was worse in 42 and roughly tied in 23. Validation shows a larger and more consistent advantage (4 of 5), but validation is adaptive: every submission returned one bit about it.
- **Improvement across generations happened, but mostly once:**
  - The second cohort's best created workflow improved on the first cohort's on sealed cases in **all 5** preserved worlds. In seed 42 the gain was marginal (10.02 → 9.98).
  - In the **reset** condition, by contrast, the second cohort's best created workflow was *worse* than the first cohort's on sealed cases in all 5 worlds, because it restarted from the baseline. Sealed scores went 10.49→11.85, 10.02→11.29, 11.73→14.57, 8.80→9.81 and 8.48→10.08.
  - The third cohort improved on sealed cases in only **1 of 5** preserved worlds (seed 77: 10.93 → 10.20). In seed 23 it created no admitted workflow.
  - In seed 11, the third cohort's revision beat its inherited parent on validation (7.68 → 7.26) but was *worse* on sealed cases (9.00 → 9.33). That is overfitting to the adaptive validation set.
  - In seeds 42 and 5, the third cohort's best created workflow was worse on both measures than what it inherited.
  - **Descendants retained knowledge, and the first descendants improved it; later descendants mostly did not.**
- **Cross-generation revisions:** 158 attempts across the preserved worlds, 15 admitted (9.5%). Admitted means it beat its inherited parent on the same validation cases.
- **Lineages:** preserved worlds built deeper lineages (final generation 5–8 against 3–4 in reset).
- **Performance level 7.5** (validation): reached in 4/5 preserved worlds against 3/5 reset. Level 6.5 was reached only once (seed 5, preserved, at tick 88).
- **The search, not resources, is the limit.** No cohort got near the per-case lower bound of about 4.3–4.9. The offline researcher's first-improvement hill-climb with 16 proposals per lifetime, guided only by 24 development cases, overfits the adaptive validation set and stalls by the third generation.

## Performance (v0.4.0)

Measured with the new systems active by `python -m genesis.profiling`. Setup: Ryzen 7 6800HS, Windows 11, Python 3.10.11, SQLite WAL with `synchronous=FULL`, seed 42, 3 × 100-tick timing runs plus a separate cProfile run and a separate tracemalloc run. Files: `evidence/v0.4.0/benchmark/`.

| Measure | 8 agents | 20 agents |
|---|---|---|
| **workshop-1 with teaching on** (sharing off, so lessons occur): committed tick median ± run-to-run SD | 56.9 ± 1.1 ms (19.1 ticks/s) | 79.3 ± 3.5 ms (12.8 ticks/s) |
| Legacy phase-1, same protocol | 32.1 ± 0.5 ms (30.2 ticks/s) | 62.6 ± 3.6 ms (16.5 ticks/s) |
| v0.3.0 phase-1, for comparison (earlier evidence) | 33.3 ms | 58.2 ms |
| Profiled shares, workshop at 20 agents (overlapping) | state copy 64%, observations 17%, canonical JSON 17%, SHA-256 12% | state copy 70%, observations 20%, canonical JSON 14%, SHA-256 11% |
| UI payload `GET /api/runs/{id}` after 100 ticks, workshop | 76 ms, 293 KB | 103 ms, 385 KB |
| Export after 100 ticks, workshop (uncompressed → gzip) | 3.8 MB → 0.29 MB | 6.8 MB → 0.58 MB |
| Peak traced Python memory (separate 30-tick pass) | 2.3 MB | 4.0 MB |

**Reading:**

- Workshop worlds cost more per tick than phase-1. They store development and validation case tables on every artifact, which enlarges state copying, hashing and serialisation.
- 20 agents with teaching active stay above the UI's maximum of 10 ticks per second.
- Phase-1 at 8 agents is unchanged within noise. At 20 agents it is about 7% slower than the v0.3.0 measurement, from the additional state fields.

## Corrections and clarifications to earlier claims

- v0.3.0 labelled its partitions "training" and "held-out". Both were adaptive. The legacy label `verified` is kept, and its meaning is now stated explicitly.
- v0.3.0 said the controller "learns before searching". In `workshop-1`, producers originally never upgraded from a superseded workflow. This was found and fixed during calibration, before the freeze.

## Not implemented / limitations

- **LLM controller:** not implemented. The `AgentController` interface is unchanged.
- **Components:** the offline researcher composes only by recombining fields, never by creating components. Component calls exist and are tested but do not appear in the experiments.
- **Teaching scope:** tested between agents of the same period (Experiment A). Experiment B used library access only.
- **Seeds:** with deterministic controllers, seeds vary only the environment. Five worlds per condition is a smoke test, and agents within a world are not independent.
- **Evaluation partitions:** development and validation cases are reused across cohorts, so validation becomes increasingly adaptive over generations. Only sealed scores are independent, and only for frozen artifacts.
