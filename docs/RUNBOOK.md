# Runbook

Commands assume the repository root and an activated virtual environment (`.venv\Scripts\activate` on Windows). `python -m genesis.cli` and the `genesis` script are equivalent. The global option `--db PATH` selects the database; the default is `data/genesis.sqlite`.

## Setup (once)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
cd frontend && npm install && npm run build
```

## Daily use

| Task | Command |
|---|---|
| Start the observatory | `python -m genesis.cli serve`, then open <http://127.0.0.1:8000> |
| Frontend hot reload | Run `serve` in one terminal, then `cd frontend && npm run dev` (port 5173 proxies `/api`) |
| Create a world, print its run ID | `python -m genesis.cli new --seed 7 [--population 20] [--restricted] [--baseline] [--removal creators --removal-tick 80 --succession fresh --successor-access library\|none\|direct]` |
| Create from a scenario file | `python -m genesis.cli new --scenario scenarios/creator-removal.json` |
| Advance a world headless | `python -m genesis.cli step RUN_ID --ticks 50` |
| List runs | `python -m genesis.cli list` |
| One-shot demo with export | `python -m genesis.cli demo --ticks 120 --removal creators --removal-tick 60 --succession fresh` |
| **Regenerate v0.5.2 (M5c) evidence** | `python tools/generate_evidence_m5c.py` (manifest, calibration, preflight, protocol freeze with sealed-4, primary admission study, allocation ablations or a deferral record, sealed-4 scoring, restart, server speed, evidence sizes, summaries; logs to `evidence/v0.5.2/runs.json`) |
| World manifest and preflight | `python tools/world_manifest_m5c.py manifest OUT.json`, then `python tools/world_manifest_m5c.py preflight MANIFEST.json OUT.json [CALIBRATION.json]` |
| **Regenerate v0.5.1 (M5b) evidence** | `python tools/generate_evidence_m5b.py` (bugfix before/after, v0.5.0 corrections, repaired rerun, calibration, protocol freeze with sealed-3, allocation and mentorship experiments, sealed-3 scoring, production accounting, demonstration, restart, CPU, server speed, profiles, summaries; logs to `evidence/v0.5.1/runs.json`; the freeze step refuses to overwrite an existing protocol) |
| Production accounting for any experiment | `python tools/production_accounting.py REPORT.json OUT.json [COND_A COND_B ...]` |
| Achieved server speed | `python tools/measure_server_speed.py OUT.json 10` (also shown live in the transport bar: target vs achieved) |
| Metric definitions | `docs/METRICS.md` (generated from `genesis/metrics_dictionary.py`) |
| **Regenerate v0.5.0 evidence** | `python tools/generate_evidence_m5.py` (calibration, protocol freeze, P, T, sealed-2, demonstration, restart, CPU, profiles, summaries; logs every step to `evidence/v0.5.0/runs.json`). The freeze step refuses to overwrite an existing protocol: move `evidence/v0.5.0` aside first. |
| v0.5 search diagnosis and inherited improvements | `python tools/diagnose_v05_search.py evidence/v0.5.0 OUT.json`, `python tools/inherited_m5.py evidence/v0.5.0 OUT.json` |
| v0.5 demonstration fixture (scripted, labelled) | `python -c "from genesis.demo5 import component_chain, summary; print(summary(component_chain(101)))"` |
| Earlier evidence | `python tools/generate_evidence_m4.py` (v0.4.0), `python tools/generate_evidence.py` (v0.3.0) |
| Inheritance experiment | `python -m genesis.cli inherit --seeds 11 42 77` (20 agents: `--population 20 --ore-per-site 960 --out evidence/v0.3.0/twenty/inheritance`) |
| Descriptive comparison | `python -m genesis.cli compare --seeds 11 42 77 --ticks 160` |
| Independent metrics for any export | `python -m genesis.cli reduce PATH.json.gz` (or `reduce-run RUN_ID` for a stored run) |
| Profile 8 and 20 agents | `python -m genesis.profiling OUT.json 100 3 [scoped\|full]` |
| Benchmark | `python -m genesis.cli benchmark --ticks 200 --population 20` |
| Tests | `python -m pytest -q` |

## Interruption and restart

Each tick commits atomically. If the server or CLI is killed, the database holds the last complete tick, and the next `serve` resumes the newest run the current engine can continue. A step that was interrupted mid-transaction leaves no trace; just retry it. A UI step retried with the same `request_id` returns the original result instead of advancing twice.

## Checkpoints, replay and forks

| Task | Command |
|---|---|
| Checkpoint | `python -m genesis.cli checkpoint RUN_ID` (or the ◫ button) |
| Replay to a tick | `python -m genesis.cli replay RUN_ID 40`. Prints the state hash; no controllers run. |
| Fork from a tick | `python -m genesis.cli fork RUN_ID 40`. Creates a new run ID with `parent` lineage; the original is untouched. |
| Fork with an intervention | `python -m genesis.cli fork RUN_ID 60 --intervention '{"removal":"creators","removal_tick":61,"succession":"fresh","successor_access":"none","invention":"frozen","max_ticks":101}' --label diag-none`. Only lifecycle, invention and `max_ticks` may change, and the intervention is recorded in the child manifest. |

In the UI, **Archive** has the same functions: inspect a tick read-only, fork the displayed state, or jump to a checkpoint.

## Export and import

```bash
python -m genesis.cli export RUN_ID --out my-run.json
python -m genesis.cli --db other.sqlite import my-run.json          # .json or .json.gz
```

Import re-verifies the checksum, every record hash, the chain links and every intermediate state hash before writing anything. A tampered export is rejected.

## After upgrading GENESIS

Runs written by a different engine, rule or evaluator version remain listed (marked read-only in the Archive) and can still be replayed and exported. Stepping, running, forking or checkpointing them fails with an explicit message. Start a new world to continue; old history is never rewritten.

## Debugging

| Symptom | Where to look |
|---|---|
| Why did an action fail? | Click the event in the timeline or the inspector's *Latest action*. `reason` is the exact rule that rejected it. |
| Did a controller crash? | Filter the timeline to *Rejections & failures* and look for `controller_failure` events. |
| Suspected corruption | `replay RUN_ID <tick>` verifies hashes along the way and raises on the first mismatch. |
| Engine paused in the UI | The red banner shows the clock thread's exception. |
| Raw evidence | `export`, then read `ticks[].record.events` / `.decisions`; each decision carries its controller label and observation hash. |

## Disk use

The benchmark reports bytes per tick (see [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)). To keep things small:

- raise `snapshot_every`, which trades replay speed for space
- delete experiment databases (`evidence/v0.*/**/*.sqlite`, which git ignores); the gzipped exports next to them are the durable evidence

`data/` and `*.sqlite` are git-ignored.
