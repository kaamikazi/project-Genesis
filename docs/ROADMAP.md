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
| M5b | **Repair, allocation and prospective validation (v0.5.1).** Stale-reference and library-dependency repairs, metric dictionary and paired denominators, creation-time attribution, allocation bundle, declared mentorship, admission-panel infrastructure, sealed-3 | M5 | **done** (bundle worse; teaching did not change outcomes; see status) |
| M5c | **Independent worlds and adaptive validation** (proposed below) | M5b | next, offline |
| M6 | **One LLM controller under budgets.** A provider adapter behind `AgentController`, receiving the existing restricted observation. Budgets per run and per agent (calls, tokens, time, price), counting failures and repair calls. Recorded and redacted prompts and responses. An explicit fallback. Replay from recorded decisions. Model calls only for deliberation. Simulation skills kept separate from pretrained knowledge. | M5 | needs your choice of provider and budget |
| M7 | **Settlement institutions.** Storage policies decided by members, library governance, shared infrastructure with maintenance, reputation from observed interactions | M4 | deferred |
| M8 | **Richer invention.** A larger program language, multi-step production chains, problems where the optimum is not reachable in about 20 ticks, held-out *mechanics* (not just held-out cases) | M3 | deferred |
| M9 | **Multiple settlements, richer geography, longer worlds**, with active-agent scheduling for larger populations | M3, M7 | deferred |
| M10 | **Human visitors** acting through the same validated contracts | M7 | deferred |
| M11 | **Generalisation across unfamiliar worlds** | M8, M9 | deferred |
| M12 | **Distributed simulation**, only if measurements justify it | all | deferred |

Milestone IDs were renumbered at v0.5.0 so that M5 is the release that shipped; the LLM controller moved from M5 to M6 and later items shifted by one.

## Immediate next step: M5c, independent worlds and adaptive validation (proposed, not started)

v0.5.1 is preserved as released. Its most important finding is about the experiment itself, not the agents. Every world uses the same controller seed, and hidden parameters have only 45 combinations, so some seeds duplicated each other's invention outcomes. No further comparative claim is worth making until that is fixed. One focused milestone:

1. **Independent replicates.**
   - Derive each world's controller seed from its world seed (a declared rule change; legacy scenarios keep the fixed seed for reproduction).
   - Widen or stratify the hidden-parameter space, and require distinct hidden parameters across a protocol's evaluation seeds. The protocol must check this before freezing.
   - Choose sample size so that at least 12 distinct worlds per condition fit the runtime budget.
2. **Run the deferred admission-panel experiment**, using the infrastructure already in v0.5.1. Compare fixed validation with cohort panels for first-improvement and repaired beam. The question is whether preserved lineages still look better on admission cases than on fresh cases.
3. **A predeclared ablation of the allocation bundle**, one guard removed at a time, to test H1–H3, because the bundle as a whole made beam worse.

Teaching and libraries are carried along unchanged as measured conditions; no new mechanics are added.

Alternatives that remain open: **M6** (LLM controller; needs your provider and budget decision) and **M7** (institutions).
