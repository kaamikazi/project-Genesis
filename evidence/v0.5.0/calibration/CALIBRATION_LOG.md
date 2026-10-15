# v0.5.0 calibration log

Calibration used development seeds **300, 301, 302** only. The evaluation seeds (201–205) and the sealed-2 cases were not used. This log records every design change made while calibrating, including the ones that did not help. The final calibration run with the frozen settings is in `calibration-summary.json` (with full reports in `P/` and `T/`).

## Fixed before calibration

- **Task and lifecycle:** workshop-1, 8 agents, 3 cohorts × 60 ticks, ore 900 per site (as in v0.4).
- **Budget:** a shared pool of 48 credits per researcher lifetime. v0.4 allowed 16 proposals, and each proposal needed 3 actions (propose, test, submit), so 48 credits allow the same number of complete attempts.

## Iterations

1. **First beam implementation.** The frontier included the baseline, composition could pair with the baseline, and operators were ordered by early success rates computed from one or two trials. On all three seeds the beam spent many expansions on the baseline and on constant-heavy operators, and it did worse than the legacy policy on cohort-0 validation.
2. **Revision 1.** The baseline enters the frontier only when the frontier is empty, and composition partners exclude the baseline.
3. **Revision 2.** Operator success rates are used only after 6 trials. After this, cohort-0 validation was still not better than legacy: legacy scored 9.97 / 10.37 / 6.78 and beam about 11.4 / 11.1 / 9.4 (lower is better).
   - **Diagnosis:** development scores of the two policies were comparable. Most of the gap came from development–validation disagreement, not from failing to find good development candidates.
   - **Decision:** stop tuning the beam here. Further tuning on three seeds would overfit them, and the specification asks for one stronger policy to be tested, not tuned until it wins.
4. **Components never appeared in published workflows.** Extraction produced components that behave identically to the field they replace, so a workflow refactored to call one could never pass strict improvement admission.
   - **Rule change:** added the declared refactor admission path (ADR-005, decision 5).
   - **Controller changes:** the beam first tries to refactor its champion to call a held component, and submits such a refactor when its development score equals the champion's.
   - **Effect:** on seeds 300–302, components reached admitted workflows in every run, and in seed 302 a cohort-2 freeze carried a closure of one component.
5. **Learner requests always went to the first neighbour.** Juniors asked one senior, so most cross-generation lessons were never offered. Requests now rotate over neighbours under `teaching_policy: package`.
6. **Overlap length.** With 15 or 20 ticks of overlap, almost all cross-generation lessons were interrupted by scheduled retirement. With 30 ticks (half a cohort), seeds 300–302 gave 4, 1 and 5 cross-generation acquisitions, still with many failures (practice costlier than baseline) and interruptions. Overlap was frozen at 30.
7. **Dependencies taught in package lessons.** This stayed at about 0 in calibration runs, because few published workflows call components when lessons happen. It was not tuned further; it is reported as a finding.

## Instrumentation changes made during calibration (no effect on behaviour)

- Wall-clock CPU was removed from decision diagnostics, because it would make hashed records non-reproducible. It is now measured by `tools/benchmark_search_m5.py`.
- Non-finite numbers in diagnostics are recorded as unavailable.
- Freeze records gained `held_best`, because `accessible_best` ignores workflows a reset cohort acquired by teaching.
