# Roadmap

Each milestone depends on the ones above it. Statuses: **done** (implemented and tested), **partial**, **next**, **deferred**.

| # | Milestone | Depends on | Status |
|---|---|---|---|
| F1 | Contracts, world mechanics, accounting, restricted observations, bounded interpreter | — | done |
| F2 | Deterministic and bounded-search controllers, independent evaluator, library transmission, adoption provenance | — | done |
| F3 | Transactional ticks, hash chain, snapshots, replay, fork, import/export, idempotency, version boundary | — | done |
| F4 | Observatory, server-owned clock, paired experiment runner, benchmark | — | done |
| F5 | Verified revisions with lineage; creator-removal experiment with matched control | — | done |
| 1 | **Twenty inhabitants and active-agent scheduling.** Raise the population limit, move from full-state deepcopy to per-action copy-on-write, add an event-driven scheduler so idle agents cost nothing, and run exploratory comparisons. | F1–F5 | next |
| 2 | **One LLM controller under budgets.** A provider adapter behind `AgentController`; per-run and per-agent call, token, time and price budgets, counting failures and repair calls; recorded prompts and responses with redaction; an explicit fallback; replay that consumes recorded decisions. Model calls only for deliberation, never for routine movement. | 1 | next |
| 3 | **Teaching and better memory.** A `teach` action with a cost; recipients must demonstrate the skill; memory summaries that keep source references. | 2 | deferred |
| 4 | **Settlement institutions.** Withdraw/deposit rules for settlement storage, shared infrastructure with maintenance, library governance, reputation from observed interactions. | 3 | deferred |
| 5 | **Succession and inheritance.** New agents receive configured knowledge packages; retention measured across generations. | 4 | deferred |
| 6 | **Cumulative improvement.** Larger program languages, multi-step production chains, revisions of other agents' artifacts. | 3, 5 | deferred |
| 7 | **Multiple settlements, richer geography, longer worlds.** | 1, 4 | deferred |
| 8 | **Human visitors** acting through the same validated contracts. | 4 | deferred |
| 9 | **Generalisation across unfamiliar worlds** with held-out mechanics. | 6, 7 | deferred |
| 10 | **Distributed simulation and large populations**, only once measurements justify it. | all | deferred |

## Immediate next step

Milestone 1. Its prerequisite is a profile of where tick time goes. The current benchmark suggests `deepcopy` of the full state per action dominates; this needs measuring before anything is changed.
