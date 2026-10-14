# GENESIS

**A persistent, inspectable digital world where inhabitants act under enforced rules, invent procedures that are executed and measured, and pass verified knowledge to one another.**

GENESIS runs fully offline on a laptop. It needs no API key, GPU or cloud service. Every notable event links to the evidence that produced it.

> v0.2.0 is a small but complete foundation, not a civilization yet. The inhabitants follow designed rules, and "invention" is a bounded search in a tiny program space. Nothing here is emergent. See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Quickstart (Windows, macOS or Linux)

You need Python 3.10+ and Node 22+ (tested with Python 3.10.11 and Node 24).

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
cd frontend && npm install && npm run build && cd ..
.venv\Scripts\python -m genesis.cli serve
```

Then open **<http://127.0.0.1:8000>** and press ▶. On macOS or Linux, use `.venv/bin/python` instead.

Headless, with no browser:

```bash
.venv\Scripts\python -m genesis.cli demo --ticks 120 --removal creators --removal-tick 60
```

```bash
.venv\Scripts\python -m genesis.cli compare --seeds 11 42 77 --ticks 160
```

```bash
.venv\Scripts\python -m pytest -q
```

## What happens in a run

1. Eight inhabitants in two settlements gather food and ore, eat, trade, and convert 2 ore into 1 alloy.
2. Conversion costs 2 or 6 energy depending on a hidden phase field that each agent senses only where it stands.
3. One researcher per settlement searches a bounded program language for a procedure that picks the cheaper mode. An independent evaluator tests each candidate on training cases and on held-out cases.
4. Researchers then revise their procedure. A revision is accepted only if it measurably beats its parent, so you can watch a lineage climb from 36 to 32, 28 and 24 energy.
5. With sharing on, other inhabitants learn the current procedure from their settlement library. An adoption is recorded only when a recipient's own production shows the saving after a logged transmission.
6. Optionally, the creators retire mid-run, or a matched set of ordinary workers does. The run then shows whether their knowledge keeps working.

## What the first experiment found

Three seeds, seven conditions each, 21 of 21 runs replay-verified:

- **Sharing:** about 2.15–2.22 energy per alloy. **Restricted:** 3.56–3.83. **No search:** 4.10–4.20.
- **After the creators retired**, sharing worlds stayed at 2.00, the same as when ordinary workers retired. Restricted worlds paid 0.60–0.71 more energy per alloy than their matched controls.

These are exploratory results from designed mechanics. The full protocol is in [docs/EXPERIMENT_PROTOCOL.md](docs/EXPERIMENT_PROTOCOL.md), and the raw exports are in `evidence/comparison/`.

## Documentation

| Document | What it covers |
|---|---|
| [VISION](docs/VISION.md) | The ambition and present limits |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Authority boundaries, tick execution, persistence, API |
| [WORLD_RULES](docs/WORLD_RULES.md) | Accounting, actions, the phase mechanic, removal |
| [AGENT_MODEL](docs/AGENT_MODEL.md) | State, observations, memory, controller modes |
| [INVENTION_PROTOCOL](docs/INVENTION_PROTOCOL.md) | Language, search, evaluator, revisions |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | Conditions, controls, reporting rules |
| [RELATED_WORK](docs/RELATED_WORK.md) | Primary references and open questions |
| [ROADMAP](docs/ROADMAP.md) | Milestones and their dependencies |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | What works, measurements, gaps |
| [RUNBOOK](docs/RUNBOOK.md) | Restart, replay, fork, export, debugging |
| [DEMO](docs/DEMO.md) | A five-minute guided walkthrough |
| [ADRs](docs/) | Architecture decision records |

Sample scenarios are in `scenarios/`, for example `python -m genesis.cli new --scenario scenarios/creator-removal.json`.

## Layout

```
genesis/      kernel (models, world, engine, invention), controllers, storage, experiments, API, CLI
frontend/     React + TypeScript + Vite observatory (built into frontend/dist and served by the API)
tests/        invariant, behavioural, persistence and API tests
scenarios/    sample world configurations
evidence/     real run exports, the comparison report, the benchmark
docs/         the documents above
```
