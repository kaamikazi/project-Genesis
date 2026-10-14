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
| M5 | **One LLM controller under budgets.** A provider adapter behind `AgentController`, receiving the existing restricted observation. Budgets per run and per agent (calls, tokens, time, price), counting failures and repair calls. Recorded and redacted prompts and responses. An explicit fallback. Replay from recorded decisions. Model calls only for deliberation. Simulation skills kept separate from pretrained knowledge. | M4 | next, needs your choice of provider and budget |
| M6 | **Settlement institutions.** Storage policies decided by members, library governance, shared infrastructure with maintenance, reputation from observed interactions | M4 | deferred |
| M7 | **Richer invention.** A larger program language, multi-step production chains, problems where the optimum is not reachable in about 20 ticks, held-out *mechanics* (not just held-out cases) | M3 | deferred |
| M8 | **Multiple settlements, richer geography, longer worlds**, with active-agent scheduling for larger populations | M3, M6 | deferred |
| M9 | **Human visitors** acting through the same validated contracts | M6 | deferred |
| M10 | **Generalisation across unfamiliar worlds** | M7, M8 | deferred |
| M11 | **Distributed simulation**, only if measurements justify it | all | deferred |

## Immediate next step

[IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md) records what Milestone 4 found. The dependency-aware options are:

- **M7a: improve the search before scaling it.** The offline researcher's first-improvement hill-climb with a 16-proposal budget is the main limit on cumulative improvement in `workshop-1`. A better offline search, using the same budget and the same evaluation roles, would show whether inherited knowledge compounds when each generation can actually extend it. No model is needed.
- **M5: an LLM controller**, using the protected evaluation roles built here. It needs your provider and budget decision.
- **M6: institutions** (library governance, storage policies). Teaching now exists to build on.
