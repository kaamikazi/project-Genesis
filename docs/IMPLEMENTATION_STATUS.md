# Implementation status, v0.2.0 (2026-10-14)

Engine `0.2.0` · rules `phase-world-2` · evaluator `phase-evaluator-2` · storage schema 1.

## Works and is verified

| Capability | Evidence |
|---|---|
| Grid world, two settlements, eight persistent agents, finite and replenishing resources, integer accounting with conservation invariants | `tests/test_engine.py` (rejections never mutate state, long-run accounting, production and consumption sinks, randomized invalid transfers) |
| Move, gather, consume, transfer, offer/accept trade (atomic, re-validated), finite message vocabulary, wait | rejection, trade and double-spend tests |
| Deterministic contention with rotating priority; every rejection logged with a reason | `test_contention_rotates_and_records_rejection` |
| Restricted observations: no world seed, no ledger or metrics, no evaluations, no other agents' histories | `test_observations_do_not_leak_world_seed_or_hidden_phase_inputs`, `test_real_search_transmission_and_access_boundaries` |
| Bounded AST language with node, depth, byte, step and capability limits; unknown operators rejected; no host code execution | `test_ast_capability_steps_unknown_operator_and_heldout` |
| Independent evaluator with disjoint training and held-out phases, a named baseline, explicit failure reasons | same, plus evaluator failure assertions |
| **Bounded search generates candidates during the run; verified revisions climb a lineage** (seed 42: 36 → 32 → 28 → 24 energy) | `test_search_climbs_a_verified_lineage_during_the_run`, `test_revisions_must_beat_parent_and_supersede_it` |
| Library transmission with logged paths; adoption only after a measured saving that follows a logged transmission | transmission and adoption tests; evidence dialogs in the UI |
| Sharing restriction: no artifact visibility, inspection rejected, zero adoptions | `test_real_search_transmission_and_access_boundaries[False]` |
| Creator removal and matched-control removal with inventory moved to storage; knowledge persists only through logged transfers | three removal tests |
| Transactional ticks, hash chain, snapshots, replay without controllers, fork lineage, export and verified import, corrupt-data rejection, crash rollback, idempotency under concurrent writers | `tests/test_storage_api.py` |
| Version boundary: older runs are read-only but replayable | `test_older_engine_runs_are_read_only_and_skipped_at_startup` |
| Compact deltas for shifting logs | `test_list_shift_deltas_round_trip` (300 randomized cases) |
| FastAPI control and inspection; server-owned clock; the built observatory served by the API | `test_api_offline_controls_submission_and_idempotency`, `test_built_observatory_is_served_with_the_api` |
| Observatory: atlas, run/pause/step/speed, inspector, timeline filters, artifact gallery with lineage and evaluation tables, experiments view, archive with replay, fork, checkpoints and export, removal banner, light and dark themes, phone layout | Exercised manually in the built-in browser on 2026-10-14 (see below) |

**Test suite:** `python -m pytest -q` reports **35 passed**.

## Browser verification (2026-10-14)

All of the following were exercised in the app's built-in browser against `genesis serve`:

- run and pause
- live ticks reaching a verified procedure
- the Invention lab cards, including rejection reasons
- the evidence dialog with the full case table, a four-generation lineage and transmission records
- creating a new world through the dialog with a removal policy; the matched control retired Ivo and Mira at tick 30
- the Experiments page rendering the real report
- the light theme
- the 375 px phone layout with no horizontal scroll
- no console errors

After a server restart, the same run resumed at tick 34 with an identical state hash. A duplicated step `request_id` advanced only one tick, and replaying tick 34 reproduced the hash.

## Experiment results

From `evidence/comparison/` (protocol `paired-phase-2`, seeds 11, 42 and 77, 160 ticks, removal at tick 80). **21 of 21 attempts completed, 0 failed, and every final state was replay-verified.** Exploratory; no significance claim.

| Energy per alloy | Seed 11 | Seed 42 | Seed 77 |
|---|---|---|---|
| sharing | 2.22 | 2.15 | 2.15 |
| restricted | 3.56 | 3.83 | 3.66 |
| baseline (no search) | 4.10 | 4.20 | 4.17 |

| Energy per alloy **after removal** | Seed 11 | Seed 42 | Seed 77 |
|---|---|---|---|
| sharing, creators removed | 2.00 | 2.00 | 2.00 |
| sharing, matched non-creators removed | 2.00 | 2.00 | 2.00 |
| restricted, creators removed | 3.87 | 4.11 | 3.96 |
| restricted, matched non-creators removed | 3.19 | 3.40 | 3.36 |

**Reading:**

- Every search world makes 512 alloy because ore is finite, so sharing changes cost, not volume.
- With sharing, producers used the creators' procedure 207, 225 and 210 times after the creators retired, and efficiency did not change. Under restriction, losing the creators cost 0.60–0.71 more energy per alloy than losing the same number of ordinary workers.
- These outcomes follow from the designed mechanics. The software measures and exposes them; it did not discover them.

The 120-tick demo (`evidence/offline-demo.json`, seed 42, creators removed at tick 60) recorded:

- 387 alloy and 6 verified revisions
- 19 adoptions, and 177 procedure uses after the creators left
- 0 rejected actions and 0 controller failures
- final hash `97fd102c…`

## Performance

Measured with `evidence/benchmark.json`: Ryzen 7 6800HS, Windows 11, Python 3.10.11, 8 agents, 200 ticks.

| Measure | Value |
|---|---|
| Committed tick (load, validate, engine, delta, SQLite commit with fsync) | median **75.9 ms**, p95 88.3 ms, **13.6 ticks/s** |
| Engine only (`advance`, in memory) | median 44.7 ms, p95 52.6 ms |
| Peak traced Python allocations (40 ticks) | 1.24 MB |
| Tick records | about 14.9 KB per tick; 4.7 MB database after 200 ticks |
| Export size | 7.3 MB for 120 ticks as plain JSON; 180–280 KB per 160-tick gzipped export |
| Model calls, tokens, cost | 0 |

**Initial target:** keep committed ticks above the UI's maximum of 10 ticks/s at 8 agents. That is met.

Engine time is dominated by `deepcopy` of the full state for each action attempt. Fixing that is the first task in milestone 1.

## Not implemented (by design or deferred)

- **The LLM controller.** The interface and zeroed budget counters exist, but no provider adapter does. See [AGENT_MODEL](AGENT_MODEL.md).
- **Teaching, institutions, governance, currency, contracts, reputation.** Settlement storage has no withdraw action yet, so retirees' inventory is conserved but unusable.
- **Succession with new agents** and inheritance packages. Removal is the only lifecycle event.
- **Social behaviour is scripted:** trades and gifts follow a fixed tick schedule.
- **Populations over 20, multi-settlement worlds, human visitors.**
- **A related-work review** beyond the three primary references.

## Known issues

- With deterministic controllers, seeds vary only the environment. Variance across seeds therefore understates what a stochastic controller would show.
- Researchers receive aggregate pass/fail feedback after held-out evaluation, which leaks some information over repeated tests.
- The workspace is not a git repository yet.
