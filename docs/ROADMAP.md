# Roadmap

Each milestone depends on the ones above it. Statuses: **done** (implemented and tested), **next**, **deferred**.

| # | Milestone | Depends on | Status |
|---|---|---|---|
| F1 | Contracts, world mechanics, accounting, restricted observations, bounded interpreter | — | done (v0.1) |
| F2 | Deterministic and bounded-search controllers, independent evaluator, library transmission, adoption provenance | F1 | done (v0.1) |
| F3 | Transactional ticks, hash chain, snapshots, replay, fork, import/export, idempotency, version boundary | F1 | done (v0.1–0.2) |
| F4 | Observatory, server-owned clock, paired runner, benchmark | F2, F3 | done (v0.2) |
| F5 | Verified revisions with lineage; descriptive creator-removal comparison | F2 | done (v0.2) |
| M3 | **Audit and inheritance (v0.3.0).** Audit of v0.2 claims; independent event reducer; usable storage; knowledge as a capability; retirement and succession with typed inheritance packages; controlled succession experiment with physical parity; cross-generation revision attempts; observation-boundary repairs; copy-on-write optimisation; 20-agent validation | F1–F5 | **done** |
| M4 | **Protected evaluation, costly teaching, richer invention (v0.4.0).** Development, validation and sealed evaluation roles; freezes; a teaching session contract with costs, reservations, interruption and assessed acquisition; the `workshop-1` task; cohort lifecycle; Experiments A and B | M3 | **done** |
| M5 | **Search diagnostics, budget-matched search, live components, teaching across generations (v0.5.0).** Shared search credits and decision diagnostics; a beam policy beside the unchanged v0.4 reference; components with in-host admission, refactor path, closures by hash; dependency-aware lessons; overlapping cohorts; sealed-2; Experiments P and T | M4 | **done** (beam not stronger; see status) |
| M5b | **Controlled search follow-up** (proposed below) | M5 | next, offline |
| M6 | **One LLM controller under budgets.** A provider adapter behind `AgentController`, receiving the existing restricted observation. Budgets per run and per agent (calls, tokens, time, price), counting failures and repair calls. Recorded and redacted prompts and responses. An explicit fallback. Replay from recorded decisions. Model calls only for deliberation. Simulation skills kept separate from pretrained knowledge. | M5 | needs your choice of provider and budget |
| M7 | **Settlement institutions.** Storage policies decided by members, library governance, shared infrastructure with maintenance, reputation from observed interactions | M4 | deferred |
| M8 | **Richer invention.** A larger program language, multi-step production chains, problems where the optimum is not reachable in about 20 ticks, held-out *mechanics* (not just held-out cases) | M3 | deferred |
| M9 | **Multiple settlements, richer geography, longer worlds**, with active-agent scheduling for larger populations | M3, M7 | deferred |
| M10 | **Human visitors** acting through the same validated contracts | M7 | deferred |
| M11 | **Generalisation across unfamiliar worlds** | M8, M9 | deferred |
| M12 | **Distributed simulation**, only if measurements justify it | all | deferred |

Milestone IDs were renumbered at v0.5.0 so that M5 is the release that shipped; the LLM controller moved from M5 to M6 and later items shifted by one.

## Immediate next step: M5b, a controlled search follow-up (proposed, not started)

v0.5.0 is preserved as released. The beam policy was not stronger, and three things it measured deserve a separate, pre-registered test rather than tuning on the v0.5 evaluation seeds:

1. **Fix the known defect first, as a declared change:** a researcher must drop a pending candidate whose admission reference is no longer current (it livelocked in T/library). Re-run T/library alone on the v0.5 seeds as a labelled repair check, not as new evidence for any claim.
2. **Isolate allocation from algorithm.** Hold the 48-credit pool fixed and vary one factor at a time, each on new calibration seeds and fresh evaluation seeds with a new sealed set: (a) beam with behaviour-hash de-duplication before proposing (does H1, redundant neighbours, explain the 30% fewer novel evaluations?); (b) beam that never proposes without the credits to test (no untested proposals); (c) first-improvement with private stepping stones (does the frontier, not the operator order, cause the lower admission rate, H2?).
3. **Make validation less adaptive across generations,** since preserved lineages overfit it: e.g. rotate validation partitions per cohort, or charge admission against a fresh partition, so that "further improvement" can be judged without sealed-only checks (H3).
4. **Give dependency lessons room to finish:** forbid a teacher from offering a lesson that cannot complete before its scheduled retirement, or start dependency lessons earlier in the overlap; measure whether dependencies are then acquired and used.

Alternatives that remain open: **M6** (LLM controller, needs your provider and budget decision) and **M7** (institutions).
