# Evidence: GENESIS v0.4.0 (Milestone 4)

Engine `0.4.0` · rules `phase-world-4` · evaluators `workshop-evaluator-1` and `workshop-sealed-1` (legacy `phase-evaluator-3` unchanged). Generated 2026-10-14/15 by:

```bash
python tools/generate_evidence_m4.py
```

`runs.json` logs each step's command, exit code, duration and finish time. **All 8 steps exited 0.**

## Source used

| | |
|---|---|
| Git commit | `01e7a2d` |
| Dirty at the protocol freeze and during evaluation | `genesis/api.py` only: a 9-line addition to the observer's `/api/experiments` endpoint, saved exactly in [`dirty-at-generation-api.patch`](dirty-at-generation-api.patch) |
| Effect of the dirty file | The experiment runners do not import `api.py`, so every world, reducer output and sealed score comes from commit `01e7a2d`'s world and experiment code. Only the profiler's UI-payload timing used the patched endpoint module. |
| Also changed by the end | `tools/summarize_m4.py` was added (read-only summariser) |
| Fingerprints | SHA-256 over all runtime sources at start, freeze and end, recorded in `runs.json` and `protocol/frozen-protocol.json` |

## Order of operations, enforced by the script

1. **Calibration** on development seeds 100, 101 and 103 (`calibration/`). Their hidden workshop parameters differ from every evaluation seed.
2. **Protocol freeze** (`protocol/frozen-protocol.json`): seeds, settings, objective, admission and selection rules, performance levels, and the **SHA-256 commitment to the 48 sealed cases**. The script stops if this step fails, and refuses to overwrite an existing freeze.
3. **Evaluation**: Experiment A (`teaching/`) and Experiment B (`cumulative/`) on seeds 11, 42, 77, 5 and 23, which were never run before the freeze.
4. **Sealed scoring** of the closed B runs' frozen artifacts (`cumulative/sealed-results.json`). The seed and commitment are in `protected/sealed-manifest.json`, outside every world.
5. **Verification and profiling** (`verification/`, `benchmark/`).

## Contents

| Path | What | Files | Compressed | Uncompressed |
|---|---|---|---|---|
| `teaching/teaching.json` | A: per seed, per continuation, per successor; sessions; parity; aggregates | 1 | — | — |
| `teaching/{seed}-A-{condition}.json.gz` / `.reducer.json` | Full exports (manifest with the fork intervention and label, tick records, snapshots, checksum) and reducer output | 20 + 20 | 3.9 MB | 57.0 MB |
| `cumulative/cumulative.json` | B: per world, per cohort, freezes, lineage, costs, parity | 1 | — | — |
| `cumulative/{seed}-B-{condition}.json.gz` / `.reducer.json` | Full exports and reducer output | 10 + 10 | 6.7 MB | 96.4 MB |
| `cumulative/sealed-results.json` | Sealed scores of every frozen artifact plus the sealed baseline, per world | 1 | — | — |
| `cumulative/summary.json` | Compact per-world summary (`tools/summarize_m4.py`) | 1 | — | — |
| `calibration/` | The same protocols on development seeds, with `calibration-summary.json` | 39 | 6.4 MB | 91.8 MB |
| `verification/restart-teaching.json` | Interrupt during an active lesson, reopen, replay and continue: 4/4 checks | 1 | — | — |
| `benchmark/profile-workshop-teaching.json`, `profile-phase1.json` | 8 and 20 agents: timing, cProfile breakdown, export, snapshot, UI payload, memory | 2 | — | — |

**Totals:** 110 tracked files, 19.9 MB. SQLite working databases are git-ignored.

## Failures and exclusions

No world, continuation or step failed. No seed was ineligible. Nothing was excluded.

During development, before the protocol freeze, three problems were fixed. None of their outputs is presented as evidence.

- **Two calibration passes:** the first ran before the producer-upgrade fix, so a second pass replaced it.
- **A reducer bug:** practice sessions were not tracked.
- **A copy-on-write sharing bug:** `practice_step` mutated an artifact that had not been copied.

## Reproducing a number

```bash
python -m genesis.cli reduce evidence/v0.4.0/teaching/42-A-teaching.json.gz
```

This recomputes sessions, acquisition and costs from events, and reconciles them with the final state.
