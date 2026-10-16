# ADR 007: Paired diverse worlds and a bounded admission-panel study (M5c, v0.5.2)

Accepted 2026-10-16, before any M5c calibration or evaluation run. Extends [ADR-006](ADR-006-repair-allocation-mentorship.md). Engine `0.5.2`, rules `phase-world-5.2`, evaluator `workshop-evaluator-4`, final evaluation `workshop-sealed-4`.

## Scope

**In scope:**
- Versioned random streams and paired world manifests with a preflight check.
- One primary admission-policy study, one secondary allocation leave-one-out study (only if the declared budget allows), observer updates, and an M6 handoff.

**Out of scope:** new world mechanics, teaching changes, new search algorithms, paid inference, and widening workshop physics. Teaching, libraries, the submission contract and retirement schedules carry over unchanged.

## Corrected framing from v0.5.1

- **A shared controller seed** limits the variation studied; it is not by itself an invalid design.
- **Repeated hidden-parameter draws** reduce task coverage; they do not make a result fraudulent.
- **Two different counts:** distinct invention parameterisations and distinct physical worlds are counted separately, because terrain still matters for teaching.
- **Coverage:** twelve of the 45 combinations improve coverage of a finite task family. They do not establish open-world generalisation.
- **The M5b allocation bundle** was harmful in its tested setting, and the responsible guard is unidentified.

## Decisions

1. **Random streams (`seed_scheme: streams-1`).**
   - Hidden invention parameters come from a declared `hidden_combo`.
   - Terrain, resource placement and per-tick phase/humidity come from `terrain_seed`.
   - Controller randomness comes from `controller_seed`.
   - Evaluation partitions stay precommitted, and teaching has no randomness.
   - The label `seed` is not a randomness source under streams-1.
   - The default `legacy` scheme reproduces every earlier world.
   - All of these fields live in the scenario config. The config is persisted and replayed, but agents never observe it; observation stays an explicit allow-list (tested).
2. **Paired blocks.**
   - Every condition in a block shares hidden parameters, physical initial state and controller seed.
   - Controller randomness is keyed by the controller seed, agent identity and the candidate, never by condition label.
   - Policies consume randomness differently, so trajectories are not claimed to stay identical after they diverge.
   - Controller seeds differ across blocks.
3. **Manifest (`tools/world_manifest_m5c.py`, `m5c-worlds-1`).**
   - Combinations are stratified by `split`, keyed within each stratum, and drawn round-robin without replacement.
   - 3 calibration blocks, then 12 evaluation blocks, each with a distinct combination.
   - Terrain and controller seeds are keyed by block id.
   - Selection never depends on outcomes.
   - **Preflight** checks: distinct combinations; no calibration reuse; distinct controller and terrain seeds; matched initial conditions within blocks; disjoint partitions; resource horizon (at least 25% of ore left in calibration); runtime and storage budget; free disk.
4. **Primary study: admission policy under preserved knowledge.**
   - Conditions: first-improvement and repaired beam, each with fixed `validation-24` admission and with cohort panels.
   - Settings: 8 agents, 3 cohorts × 60 ticks, no overlap, 48 credits, panel cap 12.
   - The claim is about admission-policy effects under preservation only. No reset conditions are run, so nothing is claimed about preservation versus reset.
5. **Panel rules.**
   - Panel k is active while cohort k is current.
   - Agents see one admission bit per submission plus their own query count; each may submit at most 12 times per panel.
   - Child and reference are re-scored on the identical active panel.
   - Older artifacts stay admitted and usable.
   - A submission costs the same in both admission policies.
   - Admission scores from different panels are never compared.
6. **Final selection (`final_selection: selection-panel`, every condition).**
   - At each freeze, the newest 16 or fewer admitted or superseded workflows held by the cohort are scored on one shared `selection-0` panel. It is disjoint from development, validation and all admission panels.
   - The lowest score is frozen as `selection_panel_best`.
   - This is observer-side and never fed back to agents. It is selection-used, not a final test.
   - Evaluations are counted in `selection_accounting`.
   - Primary endpoint: the sealed-4 score of the final freeze's `selection_panel_best`.
7. **Secondary study: allocation leave-one-out.**
   - Conditions, all with fixed admission and preserved knowledge: repaired beam, the full bundle, and the bundle without the stale-frontier guard, without the reserve guard, and without the novelty guard (`alloc_disable`).
   - Submit-time stale protection stays on in every variant; a stale reference never bypasses validation.
   - The beam/fixed worlds are shared with the primary study (identical frozen configuration) and are not re-run.
   - Each leave-one-out contrast is conditional on the other guards.
   - The study runs only if preflight estimates show both studies fit the declared budget of 150 minutes and 120 MB. Otherwise it is recorded as planned but not executed.
8. **Freeze and stop.**
   - Protocol, manifest hash, sealed-4 commitment, budgets and rules are frozen before evaluation.
   - Sealed-4 is scored only after closure, and no policy is tuned afterwards.
   - The study ends at its endpoint whatever it shows. No automatic M5d/M5e tuning cycle follows; the next milestone is M6 controller integration.

## Declared limitations

- One controller realisation per combination, so controller-by-environment variation is partly confounded. No nested controller replication.
- The 12 evaluation combinations are not balanced on `flux_threshold` (6 of 12 have flux 4).
- Within-world units (agents, artifacts, transitions) are not replicates.
- The paired rule is descriptive.

## Outcome (recorded after evaluation; no decision above was changed)

- **Run.** Preflight passed and both studies ran within budget. 12 of 12 blocks completed in every condition; none were excluded or missing.
- **Primary.** Cohort panels made no consistent difference to the sealed-4 score of the final pick, for first-improvement (6–5–1) or for beam (5–7). first-improvement was lower than beam in 10 of 12 worlds under panels; not consistently under fixed admission.
- **Secondary.** The bundle vs plain beam showed no consistent difference (7–4–1), so M5b's harmful result did not reproduce. Removing the reserve guard left every final pick identical. The stale-frontier and novelty leave-one-out contrasts were not consistent.
- **Stopping.** The study ended at its endpoint. The next milestone is M6.
