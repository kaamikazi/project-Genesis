# Architecture

GENESIS is a single-process modular monolith: Python 3.10+, Pydantic, SQLite, FastAPI, and a React/TypeScript/Vite observatory.

```
 controllers ──propose──▶ engine (validate · resolve · apply) ──▶ storage (one SQLite tx per tick)
      ▲                         │                                       │
      └── restricted observation┘                                       ▼
                                                      API (read + control) ──▶ observatory (read-only views)
```

**Authority:** controllers propose, the engine validates and applies, storage records, and the UI only reads. The kernel (`world.py`, `engine.py`, `invention.py`, `models.py`) does not import HTTP, UI or storage code.

## Modules

| File | Responsibility |
|---|---|
| `genesis/models.py` | `Scenario` and `Action` contracts (strict Pydantic), canonical JSON, SHA-256 digests, keyed randomness, and the protocol interfaces `WorldRules`, `AgentController`, `ObservationBuilder`, `MemoryStore`, `ArtifactEvaluator`, `EventStore`, `BudgetManager`, `ExperimentRunner`. |
| `genesis/world.py` | World generation, conservation totals, invariants, memory retrieval, and the restricted observation builder. |
| `genesis/engine.py` | Action rules, the disposable-copy `attempt`, scheduled removal, and `advance`, which runs one complete tick. |
| `genesis/invention.py` | The bounded AST interpreter, phase evaluator, candidate grammar and revision neighbourhood. |
| `genesis/controllers.py` | The offline deterministic and bounded-search controller, plus the search budget. |
| `genesis/storage.py` | Event store: transactional ticks, hash-chained records, snapshots, replay, fork, import/export, idempotency, and the version boundary. |
| `genesis/experiments.py` | The paired-condition runner, metrics and benchmark. |
| `genesis/api.py` | FastAPI control and inspection; a single server-owned clock thread. |
| `genesis/cli.py` | Headless commands. |
| `frontend/src/` | `main.tsx` (pages, inspector, evidence dialogs), `Atlas.tsx` (canvas map), `Experiments.tsx`. |

## Determinism and randomness

There is no `random` module in the kernel. Every random-looking value is `keyed(seed, stream, *keys)`, the first 64 bits of SHA-256 over canonical JSON. The streams are:

- `world-terrain` (x, y)
- `environment-phase` (tick, x, y)
- `controller-stream` (agent), which derives each controller's seed
- `controller-search` and `controller-revision`, which order candidates

Because environment values are keyed by time and place, paired conditions see the same phase field wherever and whenever their agents happen to stand.

Two runs with the same scenario produce identical state hashes at every tick (`test_long_run_accounting_and_determinism`). This holds because the controllers are deterministic. A future LLM controller would make live runs diverge, while replay would stay exact.

## Persistence

SQLite in WAL mode with `synchronous=FULL`:

| Table | Content |
|---|---|
| `runs` | manifest (versions, config and hash, random streams, parent run, removal policy), initial state, materialized current state and hash |
| `ticks` | one canonical record per tick: `before_hash`, `state_hash`, `previous_record_hash` (a hash chain), events, decisions with observation hashes and controller labels, and a state **delta** |
| `snapshots` | full states: the origin, every `snapshot_every` ticks, and manual checkpoints |
| `artifacts` | content-addressed immutable programs |
| `requests` | idempotency keys and payload fingerprints |
| `action_ids` | IDs of externally submitted actions, to reject replays |

Triggers make `ticks` and `artifacts` append-only and immutable.

Each tick is one `BEGIN IMMEDIATE` transaction that writes the record, artifacts, materialized state and any periodic snapshot together. A crash before commit leaves the previous tick fully intact (`test_crash_rolls_back_entire_tick`).

**Deltas** are structural diffs. Bounded logs such as memories and usage lists are encoded as "drop *n* from the front, append these". This shrank a 120-tick export from about 18 MB to the size reported in [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md). The decoder still accepts the plain-value form.

**Replay** loads the nearest snapshot at or before the target tick, then applies deltas. At every step it verifies the record hash, the chain link, the before hash and the resulting state hash. It never calls a controller.

**Fork** replays to a committed tick and creates a new run with `parent = {run_id, tick, state_hash}`. **Export** writes the manifest, initial state, every tick record, snapshots and a checksum. **Import** re-verifies the whole chain before inserting anything, under a new run ID with `imported_from`.

## Version boundary

The manifest stores the engine, rule, evaluator and schema versions. A run written by different versions stays **readable and replayable**, because replay only applies recorded deltas. It **refuses continuation** (step, run, fork, checkpoint, import) with an explicit message. History is never rewritten. The server resumes the newest run the current engine can continue.

## The server clock

A single daemon thread owned by `SimulationService` advances the selected run at 1–10 ticks per second. Browsers poll `GET /api/runs/{id}` about once a second, and that request never advances the world. Opening several viewers changes nothing, and the animation speed in the browser does not affect results.

`step` requests and submitted actions require a `request_id`. Repeating one returns the committed result. Reusing it with a different payload returns 409.

## API summary

| Method and path | Purpose |
|---|---|
| `GET /api/health`, `GET /api/status` | Liveness, the selected run, and clock state |
| `GET /api/runs` | All runs, with a `compatible` flag |
| `POST /api/runs` | Create a world from a `Scenario` (starts paused) |
| `GET /api/runs/{id}?tick=N` | State (or a replayed state), metrics, last 100 events, checkpoints, telemetry |
| `POST /api/control` | `run` / `pause` / `step` / `speed` / `select` |
| `POST /api/runs/{id}/actions` | Submit a validated action (idempotent) |
| `POST /api/runs/{id}/checkpoint`, `/fork` | Persistence operations |
| `GET /api/runs/{id}/export` | Full export download |
| `GET /api/experiments` | The latest `evidence/comparison/comparison.json` |
