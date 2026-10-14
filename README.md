# GENESIS

**A persistent, inspectable digital world where inhabitants act under enforced rules, invent procedures that are executed and measured, and pass verified knowledge on, including to successors after their creators retire.**

GENESIS runs fully offline on a laptop. It needs no API key, GPU or cloud service. Every reported number is recomputed from immutable events by an independent reducer.

> v0.3.0 is a small, audited foundation, not a civilization. The inhabitants follow designed rules, "invention" is a bounded search that reaches its optimum within about 20 ticks, and succession is simulated lifecycle management. Nothing here is emergent. See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) and the [v0.2.0 audit](docs/audit/AUDIT-v0.2.0.md).

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
.venv\Scripts\python tools/generate_evidence.py
```

```bash
.venv\Scripts\python -m genesis.cli inherit --seeds 11 42 77
```

```bash
.venv\Scripts\python -m pytest -q
```

## What happens in a run

1. Eight inhabitants in two settlements gather food and ore, eat, trade, share communal storage, and convert 2 ore into 1 alloy.
2. Conversion costs 2 or 6 energy, depending on a hidden phase field that each agent senses only where it stands.
3. One researcher per settlement searches a bounded program language. An independent evaluator tests each candidate on training and held-out cases. The proposer learns only aggregate feedback.
4. Researchers revise their procedures. A revision is accepted only if it beats its parent on the same cases: 32 → 28 → 24 energy. Here 24 is provably the minimum for this evaluation set.
5. With library access, other inhabitants learn the current procedure. An adoption counts only after a logged transmission followed by a measured saving.
6. Creators can retire and be replaced by **fresh successors**. A successor starts with nothing and must acquire the procedure through the path its policy allows. The observatory's *Why this counts as retention* panel shows every link.

## What v0.3.0 found

All results are exploratory, come from designed mechanics, and cover three seeds.

**Controlled succession** (forks from one checkpoint, physical parity verified):

| Successors | Learned the procedure | Used it with a saving | Production energy / alloy |
|---|---|---|---|
| With library access | 6 of 6, at tick 63 (they joined at tick 61) | 6 of 6, first saving at ticks 65–69 | **2.00** |
| Without library access | 0 of 6 | 0 of 6 | **4.21** (pooled) |

The same pattern holds at **20 agents** (declared ore scale): 2.00 vs 4.19.

**Live continuation** (successors may also invent): successors without library access re-derived the optimum by search, verifying it at tick 72, and paid more charged energy per alloy (3.05–3.09 vs 2.93–2.96). Library successors learned it at tick 63, and each of their three revision attempts was rejected as no improvement over the inherited optimum.

**Descriptive whole-run comparison** (21 of 21 worlds replay-verified):

| Condition | Production energy / alloy |
|---|---|
| Sharing | 2.13–2.20 |
| Restricted | 3.56–3.73 |
| No search | 4.10–4.20 |

18 of 21 worlds reached the 512-alloy ceiling now that retirees' goods can be withdrawn. The other three ended at 511, with 2 ore still accessible.

**Corrected from v0.2.0** (see [audit](docs/audit/AUDIT-v0.2.0.md)):

- Not "every world reached 512": only 9 of 21 did in v0.2.0.
- The retirement comparison was not labour-matched.
- The world seed and held-out case details leaked into controller inputs.

## Documentation

| Document | What it covers |
|---|---|
| [VISION](docs/VISION.md) | The ambition and present limits |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Authority boundaries, tick execution, persistence, copy-on-write, API |
| [WORLD_RULES](docs/WORLD_RULES.md) | Accounting, storage, actions, the phase mechanic, retirement and succession |
| [AGENT_MODEL](docs/AGENT_MODEL.md) | State, observations, the hidden-parameter independence test, controllers |
| [INVENTION_PROTOCOL](docs/INVENTION_PROTOCOL.md) | Language, search, evaluator, feedback separation, scoped optimality |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | Descriptive vs controlled experiments, metric definitions, aggregation |
| [audit/AUDIT-v0.2.0](docs/audit/AUDIT-v0.2.0.md) | Claim-by-claim audit of the previous release |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | What works, measurements, gaps |
| [ROADMAP](docs/ROADMAP.md) | Milestones and their dependencies |
| [RUNBOOK](docs/RUNBOOK.md) | Restart, replay, forks with interventions, export, reducer, profiling |
| [DEMO](docs/DEMO.md) | A guided walkthrough |
| [RELATED_WORK](docs/RELATED_WORK.md) | Primary references and open questions |
| ADRs: [001](docs/ADR-001-foundation.md), [002](docs/ADR-002-revisions-removal-versioning.md), [003](docs/ADR-003-storage-succession-audit.md) | Architecture decisions |

## Layout

```
genesis/      kernel (models, world, engine, invention), controllers, storage, reducer, experiments, profiling, API, CLI
frontend/     React + TypeScript + Vite observatory (built into frontend/dist and served by the API)
tests/        invariant, lifecycle, storage, reducer, optimisation, persistence and API tests
tools/        evidence generation, search-space enumeration, restart verification, the v0.2 audit
scenarios/    sample world configurations
evidence/     v0.3.0/ (current) and superseded/v0.2.0/ (kept, with VERSION.md)
docs/         the documents above
```
