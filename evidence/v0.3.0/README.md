# Evidence: GENESIS v0.3.0

Engine `0.3.0` · rules `phase-world-3` · evaluator `phase-evaluator-3` · storage schema 1. Generated 2026-10-14 by:

```bash
python tools/generate_evidence.py
```

`runs.json` records every step's command, exit code and duration. All 11 steps exited 0. SQLite working databases are git-ignored, and the gzipped exports are the durable record. Older evidence is kept unchanged in [`../superseded/v0.2.0/`](../superseded/v0.2.0/VERSION.md).

**Controller mode, all runs:** offline deterministic and bounded search, `controller_seed = 7`, held privately. Model calls, tokens and cost are all 0. Controller privileges are recorded in every run manifest.

| Path | What it is | Files | Compressed | Uncompressed |
|---|---|---|---|---|
| `inheritance/inheritance.json` | Controlled succession, 8 agents: seeds 11, 42 and 77; eligibility, parity and per-continuation reducer summaries | 1 | — | — |
| `inheritance/{seed}-{continuation}.json.gz` | Full exports (manifest with fork lineage and intervention, every tick record, snapshots, checksum) | 15 | 2.08 MB | 29.7 MB |
| `inheritance/{seed}-{continuation}.reducer.json` | Independent reducer output for each export | 15 | — | — |
| `twenty/inheritance/` | The same protocol at 20 agents with the declared `ore_per_site: 960` | 31 | 4.98 MB (exports) | 71.7 MB |
| `comparison/comparison.json` | Descriptive `paired-phase-3`: 21 attempts, each with config hash, engine metrics and reducer output | 1 | — | — |
| `comparison/{seed}-{condition}.json.gz` | Full exports | 21 | 5.07 MB | 67.1 MB |
| `demo/offline-demo.json` | 120-tick world, seed 42: creators retire at tick 60 and are replaced by library successors | 1 | — | 8.0 MB |
| `invention/search-space.json` | Exhaustive evaluation of every single-threshold program, and the 24-energy lower bound | 1 | — | — |
| `verification/restart.json` | Resume after restart, duplicate-step idempotency, replay hash and lifecycle records through the real API app | 1 | — | — |
| `benchmark/profile-before-optimization.json` | 8 and 20 agents, full-copy reference: 3 × 100 ticks plus a cProfile run | 1 | — | — |
| `benchmark/profile-after-optimization.json` | The same, with scoped copy-on-write | 1 | — | — |
| `benchmark/benchmark-{8,20}.json` | 200-tick committed and engine-only timing, plus separate memory | 2 | — | — |

**Reproducing one number:**

```bash
python -m genesis.cli reduce evidence/v0.3.0/inheritance/42-successor-library.json.gz
```

This prints the window, units, denominators, successor milestones and the reconciliation result.

**Failures and exclusions.** No attempt in this evidence failed.

A first 20-agent run at the default `ore_per_site: 240` marked all three seeds **ineligible**: 42–54 ore were left at the checkpoint, against more than 1,000 needed. That run was superseded by this declared-scale run and is described in [EXPERIMENT_PROTOCOL](../../docs/EXPERIMENT_PROTOCOL.md). Partial outputs from a run that was interrupted for a rule change were discarded before generation and never committed.
