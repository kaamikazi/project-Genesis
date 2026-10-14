# ADR 005: Budget-matched stronger search, live components, and teaching across generations

Accepted 2026-10-15. Extends [ADR-004](ADR-004-evaluation-teaching-workshop.md). Engine `0.5.0`, rules `phase-world-5`, evaluator `workshop-evaluator-2`, final evaluation `workshop-sealed-2`.

## Evidence that motivated this

[audit/v0.4-search-diagnosis.json](audit/v0.4-search-diagnosis.json) covers all 60 researcher lifetimes in the v0.4 Experiment B, produced by `tools/diagnose_v04_search.py`:

- **Budget, not time.** Every lifetime exhausted its 16-proposal budget, with about 15 ticks left.
- **Low hit rate.** 69% of proposals were development-tested but never improved enough to submit.
- **Validation disagreement.** 42% of submissions improved on development but failed validation.
- **Not measurable.** v0.4 did not log operators or "no candidate" decisions, so neighbourhood exhaustion cannot be judged from old data. "The search is the limit" therefore remains a hypothesis. This milestone instruments it before testing it.

## Decisions

1. **Search diagnostics.** A controller may expose a `diagnostic` record for each decision, which the engine stores with the decision in the tick record (not in world state). Each record carries the operator, the parent, the frontier size, the remaining budget, and the stop reason: `budget-exhausted`, `no-candidate`, `waiting`, or `energy`. Development results gain a `behavior_hash` (decisions on the development cases), so the reducer can count behaviourally equivalent proposals. The reducer derives every diagnostic from events and decisions.

2. **Shared search credits** (`budget_unit: credits`). Every `propose_artifact`, `test_artifact` and `submit_artifact` spends 1 credit from a single per-lifetime pool. That includes component work, re-tests of held parents, and failed or duplicate attempts, which are rejected without spending. Both policies get the same pool of **48** credits. The v0.4 meaning (`budget_unit: proposals`) stays the default. CPU time spent choosing a proposal is measured per policy by a separate benchmark (`tools/benchmark_search_m5.py`), not in tick records: wall time in hashed records would make them non-reproducible. It is bounded, because the beam enumerates a capped neighbourhood (200 candidates).

3. **Private stepping stones.** A proposal's lineage parent may be one of the agent's *own* development-tested workflows, not only an admitted one. **Admission is unchanged:** a submission must beat its nearest *current admitted* ancestor on the same validation cases, or, with no admitted ancestor, the baseline by 5%. Private candidates are never usable by others and are never "admitted" until they pass admission. The legacy policy never uses private parents, so the rule change does not alter its behaviour.

4. **Policies.** Both receive the same restricted observation and the same rules.
   - `first-improvement` is the v0.4 reference, unchanged.
   - `beam` keeps a frontier of the best 4 programs by development score. The frontier draws on the agent's own development-tested workflows and the held admitted ones; the baseline only when the frontier is empty. The beam expands frontier members in rotation, orders operators by their success in the agent's own history, restarts from a recombination of frontier members after 4 consecutive non-improving tests, and submits only when development beats the current best admitted workflow by at least 3%.
   - `beam-nocomponents` is the same beam without component operators. It separates algorithm effects from the use of component mechanics.

5. **Component protocol** (`workshop-evaluator-2`). A component is tested and submitted *in a host*: a held admitted workflow, named with an optional `host` parameter, where the host's field is replaced by a call to the component.
   - **Development:** the host is scored with the component and without it, and the result records whether behaviour is identical on all development cases (an *extraction*).
   - **Admission:** the component is admitted if the host-with-component scores *no worse* than the host on validation. Equal behaviour is allowed, because extraction is refactoring, not discovery.
   - **Mutation:** a mutated component (with its parent recorded) is admitted only if strictly better than the host using its parent.
   - **Refactor admission path (declared separately).** A workflow whose changed fields are all calls to held admitted components, with decisions identical to its admitted parent on every validation case, may replace that parent. It is recorded with `admission_path: refactor` and claims no improvement. Without this path an extracted component could never appear inside a published workflow (equal behaviour cannot pass strict improvement), so it could never be taught as a dependency. The reducer counts refactor admissions separately from improvement admissions.

6. **Dependency closures.** Components may call components. Proposals, execution, teaching and freezes all use the **transitive closure by hash**.
   - Proposal and execution require holding every dependency in the closure.
   - The inlined closure must respect the global limits (48 nodes, depth 6, 64 steps). Splitting a program across artifacts grants no extra allowance.
   - Cycles are impossible by content addressing and are also checked during resolution.
   - Freeze records store the closure, and sealed scoring receives exactly that closure.

7. **Package lessons** (`teaching_policy: package`).
   - **Teacher eligibility:** the teacher must hold the whole closure.
   - **At acceptance:** the closure is split into *already known* and *to teach*. Instruction work is 3 units per artifact taught, with each dependency's work accounted separately.
   - **Practice and acquisition:** practice runs the root workflow, which exercises the components. Acquisition grants the root plus the taught dependencies, each with its own transmission record.
   - **Strict mode:** `strict-prerequisites` (the v0.4 behaviour) still fails a lesson whose prerequisites are missing.

8. **Mentorship overlap** (`cohort_overlap: O`, **O = 30** of 60 ticks in experiment T, chosen on calibration seeds: 15 and 20 left almost every cross-generation lesson interrupted by retirement). Successors arrive O ticks before each boundary. Both cohorts coexist, with the population doubled by declaration in every condition, and then the old cohort retires at the boundary whatever lessons are unfinished. Sessions with a retiring participant are interrupted, never extended.

9. **Experiments** (exploratory, seeds frozen before running).
   - **P, primary:** policy (`first-improvement`, `beam`, `beam-nocomponents`) × knowledge (`preserved`, `reset`), 3 cohorts, no overlap (as in v0.4), credit budget 48.
   - **T, teaching:** `beam` with overlap; transfer by `library` (cross-cohort library on, teaching off), `teaching-only` (cross-cohort library hidden, teaching on with package lessons), or `none`. The physical lifecycle is identical across conditions.
   - **Seeds:** calibration seeds 300–302 are distinct from the evaluation seeds. The evaluation seeds 201–205 are worlds never used before.
   - **Held-best selection.** Freeze records gain `held_best`: the best admitted workflow held by the cohort's members, however acquired. `accessible_best` counts only the library view, so it ignores workflows a reset cohort acquired by teaching; `held_best` is the primary selection for T and for further-improvement comparisons.

10. **Fresh final evaluation.** `workshop-sealed-2` is a new manifest with an OS-drawn seed. Its 48 cases are disjoint from development, validation and `workshop-sealed-1`. The commitment is recorded in the frozen protocol before any evaluation run. The v0.4 sealed results are now known, so they are retrospective diagnostics only.

11. **Learner requests rotate** across neighbours under `teaching_policy: package` (always the first neighbour under v0.4 rules). Without rotation, juniors only ever asked one senior, so most cross-generation lessons were never offered.

12. **Demonstration fixture** (`genesis/demo5.py`). A scripted, labelled chain on seed 101: extraction, in-host admission, refactor admission, package lesson during the overlap, retirement on schedule, execution by the successor, an admitted revision, and the rewired workflow. Its actions are submitted overrides validated by the ordinary rules. It is not experimental evidence.

## Compatibility

Defaults (`search_policy: first-improvement`, `budget_unit: proposals`, `teaching_policy: strict-prerequisites`, `cohort_overlap: 0`) reproduce v0.4 behaviour. A regression test re-runs a stored v0.4 Experiment B world and compares its reducer output. v0.3 and v0.4 runs in databases are read-only under the v0.5 engine.
