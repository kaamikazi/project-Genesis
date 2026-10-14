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
| Create a world, print its run ID | `python -m genesis.cli new --seed 7 [--restricted] [--baseline] [--removal creators --removal-tick 80]` |
| Create from a scenario file | `python -m genesis.cli new --scenario scenarios/creator-removal.json` |
| Advance a world headless | `python -m genesis.cli step RUN_ID --ticks 50` |
| List runs | `python -m genesis.cli list` |
| One-shot demo with export | `python -m genesis.cli demo --ticks 120 --out evidence/offline-demo.json` |
| Paired experiment | `python -m genesis.cli compare --seeds 11 42 77 --ticks 160` |
| Benchmark | `python -m genesis.cli benchmark --ticks 200` |
| Tests | `python -m pytest -q` |

## Interruption and restart

Each tick commits atomically. If the server or CLI is killed, the database holds the last complete tick, and the next `serve` resumes the newest run the current engine can continue. A step that was interrupted mid-transaction leaves no trace; just retry it. A UI step retried with the same `request_id` returns the original result instead of advancing twice.

## Checkpoints, replay and forks

| Task | Command |
|---|---|
| Checkpoint | `python -m genesis.cli checkpoint RUN_ID` (or the ◫ button) |
| Replay to a tick | `python -m genesis.cli replay RUN_ID 40`. Prints the state hash; no controllers run. |
| Fork from a tick | `python -m genesis.cli fork RUN_ID 40`. Creates a new run ID with `parent` lineage; the original is untouched. |

In the UI, **Archive** has the same functions: inspect a tick read-only, fork the displayed state, or jump to a checkpoint.

## Export and import

```bash
python -m genesis.cli export RUN_ID --out evidence/my-run.json
python -m genesis.cli --db other.sqlite import evidence/my-run.json          # .json or .json.gz
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
- delete experiment databases under `evidence/comparison/experiments.sqlite`; the gzipped exports next to them are the durable evidence

`data/` and `*.sqlite` are git-ignored.
