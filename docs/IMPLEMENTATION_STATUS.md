# Implementation status, v0.3.0 (2026-10-14)

Engine `0.3.0` · rules `phase-world-3` · evaluator `phase-evaluator-3` · storage schema 1. Evidence: [`evidence/v0.3.0/`](../evidence/v0.3.0/README.md). The previous release's claims are audited in [audit/AUDIT-v0.2.0.md](audit/AUDIT-v0.2.0.md).

**Verification run at release:**

- `python -m pytest -q`: **70 passed** (it was 35 before this milestone, recorded in [audit/baseline-verification.md](audit/baseline-verification.md))
- `npm run build`: succeeded
- `python tools/generate_evidence.py`: 11 of 11 steps exited 0

## Works and is verified

| Capability | Evidence |
|---|---|
| Independent reducer: holdings, energy by category, windows, successor milestones, reconciliation | `tests/test_reducer.py`. Every energy change per agent is explained by events alone, holdings match the final state, and zero denominators are reported as unavailable. The reducer does not import the engine. |
| Settlement storage: deposit, withdraw, membership, reach, stock contention, flows ledger | `tests/test_lifecycle_storage.py`. Unauthorized access is rejected, competing withdrawals never overdraw, the ledger is preserved, and production continues from deposited ore. |
| Retirement to withdrawable storage; retired agents cannot act by any path | `test_retirement_moves_inventory_to_withdrawable_storage`, `test_retired_agents_cannot_act_by_any_path` |
| Fresh successors with a declared inheritance package (library / none / direct control) | `test_successors_start_fresh_with_only_the_declared_package`, `test_direct_transfer_control_is_labelled` |
| Library successors discover, learn and use the procedure, with logged evidence | `test_library_successor_discovers_learns_and_uses_with_logged_evidence`, `test_successor_evidence_is_derived_from_events` |
| Restricted successors have no alternate path (direct IDs, observations, transmissions) | `test_restricted_successor_has_no_alternate_path_to_procedures` |
| Cross-generation revision attempts with an intact lineage | `test_successor_researcher_revises_the_inherited_procedure` |
| Fork interventions validated and recorded; physical parity across matched continuations | `test_forked_continuations_share_physical_conditions`, `test_fork_interventions_are_validated` |
| Replay reconstructs every tick, including lifecycle, storage and successors; export and import | `test_replay_reconstructs_lifecycle_and_storage_at_every_tick` |
| Observation boundary: independent of hidden parameters; agent feedback carries no held-out case detail | `test_observations_are_independent_of_hidden_parameters`, `test_agent_feedback_never_carries_held_out_case_detail` |
| Copy-on-write attempts identical to the full-copy reference | `tests/test_optimization.py`: 6 scenarios, including 20 agents and fuzzed submissions of every action kind, with shared-state verification |
| Resume after restart, idempotent steps and actions | `evidence/v0.3.0/verification/restart.json` (6 of 6 checks), plus the existing storage and API tests |
| All v0.1–v0.2 behaviour (accounting, contention, trades, the evaluator, revisions, hash chain, corruption rejection, crash rollback, version boundary) | the original tests, retained |

## Browser verification (built-in browser, 2026-10-14)

Checked against `genesis serve` with a world in which the creators retire at tick 30 and library successors replace them:

- The removal banner names the retirees and their successors with the access policy, and shows the post-removal window.
- The inspector shows "Succeeded by Oren" and "Retired at tick 30 · history archived, not inherited".
- The Inhabitants page lists active agents first and retirees last, with links in both directions.
- The *Why this counts as retention* panel shows all six links for both successors.
- Settlement storage shows the retirement, deposit and withdrawal flows.
- The Experiments page renders the inheritance diagnostic (with parity badges), the live continuation, the 20-agent replication, and the descriptive comparison from the reducer.
- At 375 px, none of the five pages scrolls horizontally, and there are no console errors.
- Screenshots sometimes timed out because the app window was behind another window. Text and DOM checks were used instead.

## Corrected claims from v0.2.0

| v0.2.0 claim | Correction (evidence) |
|---|---|
| "Every world hits the same 512-alloy cap" | 512 is the theoretical maximum (1,024 ore ÷ 2). In v0.2.0 it was reached in **9 of 21** worlds; retirement worlds stranded 2–6 ore in storage that could not be withdrawn. In v0.3.0, **18 of 21** reach 512, and the other three end at 511 with 2 ore still accessible. |
| "Retirement comparison is fair / isolates knowledge" | It is **descriptive only**: the retired creators were researchers (21–31 pre-removal productions) and the matched retirees were producers (38–42). The controlled test is the inheritance diagnostic. |
| "Controllers never receive the world seed" | v0.2.0 leaked a seed-derived value. The seed was recovered in at most 78 guesses. Fixed: an independent controller seed, never observed, guarded by a test. |
| "Held-out cases never shown case by case" | v0.2.0 leaked 38 held-out case failures into memories (seed 42). Fixed: agents now receive aggregate feedback only. |
| "24 energy is optimal" | Now scoped and proved: a lower bound of 2 energy × 12 cases, reached only by threshold 6 (`invention/search-space.json`). |
| "Lineage 36 → 32 → 28 → 24" | That was v0.2.0's ordering. With the independent controller seed it is 32 → 28 → 24 (Hearth); Haven finds 24 directly. |

## Results (exploratory; 3 seeds; designed mechanics)

### Controlled succession, 8 agents

Fork at tick 60, retirement at tick 61, diagnostic window ticks 62–101, invention frozen. Physical parity was verified for all three seeds.

| Continuation | Successors acquiring via library | With a measured saving | Successor production energy / alloy (mean of 6 · pooled) | Settlement production energy / alloy, by seed |
|---|---|---|---|---|
| successor-library | 6 / 6 (tick 63) | 6 / 6 (ticks 65–69) | 2.00 · 2.00 | 2.00, 2.00, 2.00 |
| successor-no-library | 0 / 6 | 0 / 6 | 4.21 · 4.21 | 2.60, 2.52, 2.46 |
| successor-direct-control | package | 6 / 6 (ticks 64–67) | 2.00 · 2.00 | 2.00, 2.00, 2.00 |

Charged energy per alloy for the whole settlement, by seed:

- library: 2.76, 2.87, 2.80
- no library: 3.31, 3.32, 3.26

Ore left at the end of the window: 236–244, so there was no depletion.

### Controlled succession, 20 agents (declared `ore_per_site: 960`)

Parity was verified for all seeds. Library successors: 6 of 6 acquired the procedure (ticks 63–65), 6 of 6 showed a saving, at 2.00. No-library successors: 0 of 6, pooled 4.19. Settlement production energy per alloy was 2.00 vs 2.18–2.22. 1,948–1,976 ore remained.

At the default ore scale, 20 agents left only 42–54 ore at tick 60, and every seed was correctly marked **ineligible**.

### Live continuation (separate experiment; successor researchers; invention open; ticks 62–161)

- **Library successors** learned the inherited procedure at tick 63. Each proposed its three neighbours, and all were rejected (`no improvement over parent`, against a 24-energy parent). No new verified creator appeared.
- **No-library successors** made 8 proposals each and re-verified the optimum at tick 72.
- Production efficiency ended equal (2.00). Total charged energy per alloy differed: 2.93–2.96 with the library, 3.05–3.09 without (8 agents).
- **Caveat:** 8-agent live runs ran out of ore before tick 161 (flagged `depleted`). 20-agent live runs did not (792–864 ore left).

### Descriptive whole-run comparison (`paired-phase-3`, 21/21 completed and replay-verified)

| Condition | Production energy / alloy | Charged energy / alloy |
|---|---|---|
| sharing | 2.16, 2.13, 2.20 | 3.11, 3.10, 3.15 |
| restricted | 3.56, 3.73, 3.64 | 4.46, 4.65, 4.55 |
| baseline | 4.10, 4.20, 4.17 | 4.91, 5.02, 4.99 |

Retirement rows are in `comparison.json`. They are descriptive only.

## Performance

Ryzen 7 6800HS, Windows 11, Python 3.10.11, SQLite WAL with `synchronous=FULL`, seed 42.

| Measure | 8 agents | 20 agents |
|---|---|---|
| Committed tick, full-copy reference (3 × 100 ticks, median · run-to-run SD) | 65.1 ms · 0.3 | 215.7 ms · 3.5 |
| Committed tick, scoped copy (same protocol) | **33.3 ms** · 0.7 (30.3 ticks/s) | **58.2 ms** · 2.2 (16.9 ticks/s) |
| 200-tick benchmark, committed median / p95 | 42.5 / 65.3 ms (22.5 ticks/s) | 60.2 / 82.7 ms (16.1 ticks/s) |
| Engine only (`advance`, in memory), median | 12.5 ms | 25.1 ms |
| Profiled share of state copying, before → after | 85% → 64% | 93% → 65% |
| Other notable shares after (overlapping) | observations 19%, canonical JSON 13%, SHA-256 12%, commit + fsync 6% | 21%, 14%, 12%, 5% |
| UI payload `GET /api/runs/{id}` after 100 ticks | 46 ms, 152 KB uncompressed | 63 ms, 214 KB |
| Export after 100 ticks: build / serialise / gzip | 0.08 / 0.03 / 0.08 s; 2.59 MB → 0.19 MB | 0.19 / 0.05 / 0.16 s; 4.65 MB → 0.37 MB |
| Snapshot size / serialise time | 118 KB / 6.3 ms | 196 KB / 10.9 ms |
| Tick records (200-tick run) | 15.2 KB per tick | 26.1 KB per tick |
| Peak traced Python memory (separate pass) | 0.9–2.1 MB | 1.6–3.9 MB |

**Notes:**

- cProfile shares overlap, because nested calls are counted at each level, and profiling adds overhead.
- In the earlier pre-release profile the commit and fsync time was hidden in `Connection.__exit__`. The profiler now captures it.
- The 200-tick benchmark is slower per tick than the 100-tick profiles, because state, events and artifacts grow over the run.
- Both populations exceed the UI's maximum of 10 ticks per second.

## Not implemented

- **LLM controller:** the interface exists, but no adapter. Building one needs your choice of provider and budget.
- **Teaching, institutions, governance, currency, contracts, reputation:** not implemented.
- **Successor births** are scheduled by the scenario. There is no reproduction, and nothing is inherited beyond the declared package.
- **Social behaviour** (trades and gifts) is scripted.
- **Invention** reaches its optimum within about 20 ticks, so the inheritance results concern *retention* of a solved procedure, not cumulative improvement across generations.

## Known issues and limitations

- The controllers are deterministic, so variation across seeds is environmental only. Three seeds are a smoke test.
- Successors in one world are not independent samples. Pooled successor ratios are labelled as such.
- Partition-level evaluation feedback leaks aggregate information about the held-out set over repeated tests.
- `artifact.uses` keeps only the last 64 uses. The observatory therefore labels a "first saving" taken from that list as the earliest *retained* one; the reducer gives the exact first tick.
- The 8-agent live continuation depletes ore before its window ends.
