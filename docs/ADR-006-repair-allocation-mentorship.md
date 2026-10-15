# ADR 006: Repairs, metric dictionary, allocation bundle and declared mentorship (M5b, v0.5.1)

Accepted 2026-10-16, before any M5b evaluation run. Extends [ADR-005](ADR-005-search-components-mentorship.md). Engine `0.5.1`, rules `phase-world-5.1`, evaluator `workshop-evaluator-3`, final evaluation `workshop-sealed-3`, metrics `genesis-metrics-1`.

v0.5.0 and its evidence are unchanged. Results from v0.5.0 are described as **run with known defects**. Repaired reruns of the v0.5.0 worlds are labelled retrospective and kept separate from the prospective M5b experiments.

## 1. Submission contract (repairs the stale-reference livelock)

- **What a submission is judged against.** The candidate's *reference*: its nearest admitted ancestor, derived from the immutable parent chain, skipping the agent's private stepping stones. The engine and the observation builder share one implementation.
- **How a conflict is detected.** If the reference is no longer admitted, the submission is rejected and the reason names the stale reference and its successor. A submission may also name the reference it expects (`reference` parameter, compare-and-swap). A mismatch is rejected as a "reference conflict".
- **What it costs.** A rejected submission spends no credit and no energy, only the agent's turn. Rejected events now carry the action's parameters, so retries are auditable.
- **Recovery.** `withdraw_artifact` is free and allowed only for the creator's own proposed or development-tested candidate. It moves the candidate to `withdrawn`, which never admits. A **rebase** is an ordinary, fully charged proposal of the program against a current head (proposal, development test, submission). Earlier evaluations are never relabelled against a new reference: admission always re-scores child and reference on the same current cases.
- **Observation.** Each of the agent's own pending candidates shows its `reference` and `reference_status`.
- **Controllers (the repair).** Both policies withdraw a stale candidate at the point where they would have submitted it, so a changing head can cost at most one rejected submission and one withdrawal per candidate. Repaired policies never rebase. The policies are otherwise unchanged, so the repair stays separate from search changes.
- **Same defect class in first-improvement.** It revised a superseded workflow forever. It now revises only a current admitted workflow, or the baseline if it holds none.

## 2. Dependency-aware library copy (repairs a second defect)

Copying a workflow from the library also copies the components missing from its dependency closure. Each one is a separately charged copy with its own transmission record. If any dependency is not in the agent's library, nothing is copied and the action is rejected.

Library entries expose their dependency ids (metadata, not programs). Controllers skip entries they cannot obtain.

In v0.5.0, producers copied component-calling workflows without the components, and each later execution was rejected. That was 1,390 rejected executions in beam/preserved.

## 3. Metric dictionary and comparisons

- **Dictionary.** `genesis/metrics_dictionary.py` (`genesis-metrics-1`) defines every counter: what it counts, unit, inclusion rule and event source. The reducer (`genesis.reducer/3`) emits a `metrics` block from it; `docs/METRICS.md` is generated from the same file.
- **Distinct counters.** These are kept separate: identical program content; identical decisions on the 24 development cases; matching scores with different decisions; own-candidate tests vs held re-tests vs component tests; improvement admissions vs refactors; revisions against an earlier-cohort reference vs parent vs ancestry; and held knowledge vs knowledge created before a boundary.
- **Paired comparisons** report expected worlds, completed worlds, eligible pairs, missing values with reasons, wins/losses/ties, and the decision denominator. Means are over eligible pairs only. A missing selection is never a zero-cost score.
- **Decision rule (descriptive).** A direction is reported only if at least 75% of expected worlds are eligible pairs and one side is lower in at least 75% of them. The exact two-sided sign-test probability is shown as a description, not a test of significance.
- **Creation-time attribution.** Freezes now record `created_upto_best` and `created_inventory`: what cohorts up to k had *created* by the boundary, by creation event and creator cohort. Seniors adopting juniors' work cannot change it. Proposals record their ancestors' creator cohorts.
- **Further improvement (prospective).** Cohort k's own best workflow compared with `created_upto_best` frozen at cohort k−1's boundary. Both are selected by validation before final scoring. The frozen v0.5 metric is kept as historical.

## 4. Allocation bundle (`search_policy: beam-alloc`)

The repaired beam plus four declared guards. The design identifies the bundle's combined effect, not each guard's.

1. **Reserve.** Propose only when the shared pool can fund proposal, test and submission (3 credits) and the declared schedule leaves at least 4 ticks before retirement.
2. **Exact novelty.** Skip a candidate whose decisions equal, for every possible integer input, those of a program the agent has proposed or holds.
   - Equality is decided per field by evaluating both expressions at one point per threshold interval. Programs compare measures only through `measure < threshold`, so this is exact, not sampled.
   - It uses no task cases, outcomes or hidden parameters, and spends no credits. Its work is recorded as point evaluations in the decision diagnostic and reducer.
   - It deliberately does **not** filter on equality over the 24 development cases. That would discard candidates that differ on future cases, and computing it would be an uncharged evaluation.
   - Refactor and extraction operators are exempt, because they are equivalent by design. The comparison set is the agent's own and held programs (its access); there is no cache across decisions or agents.
   - Trade-off, stated plainly: the filter only removes exact duplicates of behaviour. It cannot make search find better programs, and it changes which neighbour is tried next.
3. **Bounded generation.** At most 200 candidates are examined per decision across all frontier nodes; then the policy stops with `no-candidate`.
4. **No spending on stale lineages.** Stale pending candidates are withdrawn before any further credit is spent on them.

Validation rejection remains possible; nothing guarantees admission.

## 5. Admission panels (infrastructure; experiment deferred)

`validation_policy: cohort-panels` is implemented and tested; no experiment is run in this release.

- **Panels.** Each cohort has a precommitted 24-case panel, disjoint from development, validation and every other panel. A panel becomes active when its cohort becomes current.
- **Feedback and limits.** Agents see one admission bit per submission plus their own query count. Each agent may query a panel `panel_queries` times; a further submission is rejected for free.
- **Comparisons.** Parent and child are scored on the same current panel.
- **Freezes.** Historical scores from different panels are not comparable, so freezes re-score candidates on the active panel (observer-side).
- **Continuity.** Previously admitted artifacts stay usable. Costs are as for any submission.
- **Caveat.** Changing panels does not remove adaptivity: any panel queried through admission is adaptive.

## 6. Declared mentorship (`teaching_policy: package-scheduled`)

Package lessons (ADR-005), plus three rules:

- **Upgrade requests.** A junior re-requests lessons from earlier-cohort neighbours every 8 ticks, even after it holds something.
- **No repeat offers.** A teacher skips workflows it has already offered to that learner, using its own recent memory.
- **Feasibility window.** A teacher never starts a lesson that cannot finish before its own scheduled retirement. The estimate is acceptance + 3 work units per artifact + 2 practice runs + 3 slack ticks.

The observation shows the declared public schedule: own cohort, scheduled retirement, and neighbours' cohort labels.

The mentorship schedule (cohort length and overlap) is chosen on calibration seeds by a rule written in `tools/calibrate_m5b.py` before running, and is identical in every mentorship condition. Retirement is never delayed and nothing is seeded into a learner.

## 7. Server pacing

The clock now schedules ticks at a fixed rate rather than 1/speed after each step, and caps catch-up at 1 s. Status reports target speed, achieved speed, step time, lag, base population and active agents. Simulation results do not depend on pacing.

## Compatibility

Defaults reproduce v0.4/v0.5 behaviour where no defect was involved; the stored v0.4 experiment-B regression still matches. Runs written by v0.5.0 are read-only under 0.5.1.

## Outcome (recorded after evaluation; no decision above was changed)

- **Repairs.** All three defects are repaired on minimal reproductions (10, 10 and 5 rejected actions per 10 ticks under v0.5.0, 0 after). In the repaired rerun, beam/preserved's production deficit disappeared.
- **Allocation bundle.** It made the repaired beam worse on sealed-3 in every frozen world (6 of 6; 4 of 4 distinct), although it removed repeated behaviour and untested proposals. Which guard caused the loss is not identified.
- **Declared mentorship.** At 80/40, chosen in calibration, 8 of 26 dependency lessons were acquired and the taught workflows were used independently after the teachers retired. Final selections matched no-transfer in 5 of 6 worlds.
- **Sample.** A constant controller seed plus a small hidden-parameter space made two seed pairs duplicates, so the evaluation has 4 distinct worlds.

Details: [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md).
