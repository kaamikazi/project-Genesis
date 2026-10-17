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
| M5c | **Paired diverse worlds and prospective admission tests (v0.5.2).** Versioned random streams, world manifests with preflight, shared selection panel, admission-panel study, allocation leave-one-out | M5b | **done** (panels: no consistent difference; bundle harm not reproduced) |
| M6 | **One model-backed controller under budgets (v0.6.0)** ([ADR-008](ADR-008-model-controller-boundary.md)). Two-phase model step with the engine authoritative; Ollama `/api/chat` adapter; strict one-action parser with one repair; event-driven scheduler; durable call ledger with leases and no blind resends; budgets with reservations and uncertain usage; explicit fallback; state replay, decision re-execution and strict recorded continuation; sanitized observer | M5c | **done for fixtures and mocked transport**; no live provider exercised |
| M6a | **Gemini Developer API adapter (v0.6.1)** ([ADR-009](ADR-009-gemini-adapter.md)). Native stateless `generateContent`, backend-only `GEMINI_API_KEY`, origin pinning without redirects, thinking-aware usage, quota and overshoot halts, pacing, operator free-tier confirmations, disabled smoke template and launcher | M6 | **done for mocks**; no live request made |
| M6b | **First live model runs.** A small authorized smoke run ([checklist](LIVE_RUN_CHECKLIST.md)), then the model controller as one fixed condition on the M5c paired manifests with a fresh sealed-final commitment | M6 | **smoke done (v0.6.2)**: two live runs; run 1 exposed a wire-schema defect, fixed; run 2 clean. The paired-manifest study is next and needs a larger, explicitly authorized request budget |
| M7 | **Settlement institutions.** Storage policies decided by members, library governance, shared infrastructure with maintenance, reputation from observed interactions | M4 | deferred |
| M8 | **Richer invention.** A larger program language, multi-step production chains, problems where the optimum is not reachable in about 20 ticks, held-out *mechanics* (not just held-out cases) | M3 | deferred |
| M9 | **Multiple settlements, richer geography, longer worlds**, with active-agent scheduling for larger populations | M3, M7 | deferred |
| M10 | **Human visitors** acting through the same validated contracts | M7 | deferred |
| M11 | **Generalisation across unfamiliar worlds** | M8, M9 | deferred |
| M12 | **Distributed simulation**, only if measurements justify it | all | deferred |

Milestone IDs were renumbered at v0.5.0 so that M5 is the release that shipped; the LLM controller moved from M5 to M6 and later items shifted by one.

## Immediate next step: decide the first model study

The Gemini path now works live (v0.6.2). The first run found and fixed a wire-schema defect; the second was clean, with 8 of 8 responses valid. The next step from the M6 handoff is to run the model controller as one fixed condition on the M5c paired manifests with a fresh sealed-final commitment. That needs far more than 10 requests, so it needs your explicit request budget, the free-tier quota to support it, and a decision on how many worlds and inhabitants to use. No further live calls happen until then.

## Separate proposal: evidence storage

Committed evidence has grown by about 65, 131 and 86 MB in the last three releases. Exports are the main cost. Proposed for a future, separate decision, with no history rewritten:
- keep manifests, protocols, summaries, reducer outputs and hashes in Git;
- publish full compressed exports as release assets, or through Git LFS, with their SHA-256 recorded in the evidence README.
