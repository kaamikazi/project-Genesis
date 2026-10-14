# ADR 001: An inspectable, offline foundation

Accepted 2026-10-13. This workspace started empty; no inherited repository instructions or code were present.

Use a modular Python monolith, Pydantic action contracts, SQLite transactions, FastAPI, and React/TypeScript/Vite. The kernel receives restricted controller proposals and owns all world mutations. The browser observes committed state; one server scheduler advances time. No model service is needed.

The first world is a configurable 24 × 16 island with two settlements and eight persistent agents. Finite ore and replenishing food sites, integer inventories, fatigue, adjacent movement and atomic exchange provide actual constraints. Scenario abundance is explicit, not emergency rescue.

The invention task is a fictional phase-sensitive ore converter. Programs are bounded JSON decision trees selecting one of two conversion modes using a local phase measurement. A fixed mode is the baseline. A finite, declared search generates candidates during a run; an independent evaluator measures energy on training and held-out phase cases using the same conversion function as production. Successful recipients must inspect then execute a procedure. No claims of open-ended invention or emergence.

Resolution uses tick-rotating agent priority. Observations come from the start of a tick; ownership, proximity and resource preconditions are rechecked in sequence. Each action executes on a disposable copy, so rejection cannot partially mutate state. A tick, its decisions, events, state delta, state hash and periodic snapshot commit in one transaction. Replay applies recorded deltas and checks hashes without controllers.

Milestones, in dependency order:

1. Contracts, world mechanics, accounting, observations and bounded interpreter.
2. Deterministic controllers, independent evaluation and transfer provenance.
3. Transactional persistence, replay, checkpoints, forks, import/export and CLI.
4. Observatory, server-owned clock and integration verification.
5. Paired seed comparison, real evidence export, measured benchmark and runbook.

Deferred: paid model adapter, institutions, succession, arbitrary code execution, distributed simulation. Later capabilities must build on the evidence and authority boundaries above.
