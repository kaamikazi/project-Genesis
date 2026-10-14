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
| M4 | **Teaching and acquisition costs.** A `teach` action between agents, with costs on both sides; the recipient must demonstrate the skill before it counts. Memory summaries that keep source references. Inheritance experiments where the only path is teaching. | M3 | next |
| M5 | **One LLM controller under budgets.** A provider adapter behind `AgentController`, receiving the existing restricted observation. Budgets per run and per agent (calls, tokens, time, price), counting failures and repair calls. Recorded and redacted prompts and responses. An explicit fallback. Replay from recorded decisions. Model calls only for deliberation. Simulation skills kept separate from pretrained knowledge. | M3 (M4 helps) | next, needs your choice of provider and budget |
| M6 | **Settlement institutions.** Storage policies decided by members, library governance, shared infrastructure with maintenance, reputation from observed interactions | M4 | deferred |
| M7 | **Richer invention.** A larger program language, multi-step production chains, problems where the optimum is not reachable in about 20 ticks, held-out *mechanics* (not just held-out cases) | M3 | deferred |
| M8 | **Multiple settlements, richer geography, longer worlds**, with active-agent scheduling for larger populations | M3, M6 | deferred |
| M9 | **Human visitors** acting through the same validated contracts | M6 | deferred |
| M10 | **Generalisation across unfamiliar worlds** | M7, M8 | deferred |
| M11 | **Distributed simulation**, only if measurements justify it | all | deferred |

## Immediate next step: M4 (teaching)

**Prerequisites, all present in v0.3.0:**

- the `library` capability split, which makes a no-library control possible
- successor agents
- the reducer's acquisition and use milestones

**Design question to settle first.** Teaching must have a cost and a failure mode. Otherwise it is just a library with another name.

**Why M7 matters soon.** In v0.3.0 the optimum (24 energy) is reached within about 20 ticks. Every inheritance result is therefore about keeping a solved procedure, not about building on it. Cumulative improvement across generations needs a problem that cannot be solved in one lifetime.

**Performance headroom.** 20 agents run comfortably above the UI's 10 ticks per second (see [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)). Larger populations (M8) will need event-driven scheduling and less per-tick copying.
