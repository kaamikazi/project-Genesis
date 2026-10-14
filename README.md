# GENESIS

**A persistent, inspectable digital world where inhabitants act under enforced rules, invent procedures that are executed and measured, and pass verified knowledge on, including to successors after their creators retire.**

GENESIS runs fully offline on a laptop. It needs no API key, GPU or cloud service. Every reported number is recomputed from immutable events by an independent reducer.

> **v0.4.0** adds three things:
> - **protected evaluation:** development, validation and sealed roles
> - **costly teaching:** sessions with practice, assessment and failure
> - **a richer invention task** (`workshop-1`), run across scheduled cohorts
>
> The inhabitants still follow designed offline policies, and nothing is emergent. See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md). v0.3.0 is preserved as git tag `v0.3.0`.

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
.venv\Scripts\python tools/generate_evidence_m4.py
```

This runs calibration, freezes the protocol (with a sealed-case commitment), runs Experiments A and B, scores the frozen artifacts on sealed cases, and profiles. It takes about 15 minutes.

```bash
.venv\Scripts\python tools/generate_evidence.py
```

This regenerates the v0.3.0-protocol evidence.

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

## What v0.4.0 found

These results are exploratory: 5 evaluation seeds, frozen before they ran, with offline controllers.

**Experiment A: how fresh successors get a workshop procedure.** Matched forks from one checkpoint, with physical parity verified.

| Path | Acquired | Median ticks | Successor energy / alloy | Settlement charged energy / alloy |
|---|---|---|---|---|
| Teaching (costly sessions) | 10/10 | 14.5 | 5.33 | 6.56 |
| Library | 10/10 | 2 | 5.66 | 6.52 |
| No transfer | 0/10 | — | 8.60 | 7.06 |

- **Teaching works,** but it is slower than the library, at about the same total cost.
- **3 lessons failed honestly:** a practice run cost more than the baseline. All three were retried and acquired.

**Experiment B: does preserved knowledge build across cohorts?** Three cohorts, preserved versus reset library.

| | Mean sealed score of the final best (lower is better) |
|---|---|
| Preserved | 9.06 |
| Reset | 9.73 |

- **Preserved knowledge won in only 3 of 5 worlds on sealed cases.**
- **The second cohort improved** on its inheritance in all 5 preserved worlds. In reset worlds, the second cohort fell back in all 5.
- **The third cohort improved** on sealed cases in only 1 of 5. Some of its revisions beat the validation set but lost on sealed cases, which is overfitting to adaptive feedback.
- **Descendants retained knowledge; sustained improvement did not happen.**

**Earlier milestones:** the v0.3.0 results (phase-1 task, controlled succession) are in [evidence/v0.3.0](evidence/v0.3.0/README.md). The v0.2.0 corrections are in the [audit](docs/audit/AUDIT-v0.2.0.md).

## Documentation

| Document | What it covers |
|---|---|
| [VISION](docs/VISION.md) | The ambition and present limits |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Authority boundaries, tick execution, persistence, copy-on-write, API |
| [WORLD_RULES](docs/WORLD_RULES.md) | Accounting, storage, actions, the phase mechanic, retirement and succession |
| [AGENT_MODEL](docs/AGENT_MODEL.md) | State, observations, the hidden-parameter independence test, controllers |
| [INVENTION_PROTOCOL](docs/INVENTION_PROTOCOL.md) | Language, search, evaluator, feedback separation, scoped optimality |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | Descriptive vs controlled experiments, metric definitions, aggregation, Milestone 4 protocols |
| [audit/AUDIT-v0.2.0](docs/audit/AUDIT-v0.2.0.md) | Claim-by-claim audit of the previous release |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | What works, measurements, gaps |
| [ROADMAP](docs/ROADMAP.md) | Milestones and their dependencies |
| [RUNBOOK](docs/RUNBOOK.md) | Restart, replay, forks with interventions, export, reducer, profiling |
| [DEMO](docs/DEMO.md) | A guided walkthrough |
| [RELATED_WORK](docs/RELATED_WORK.md) | Primary references and open questions |
| ADRs: [001](docs/ADR-001-foundation.md), [002](docs/ADR-002-revisions-removal-versioning.md), [003](docs/ADR-003-storage-succession-audit.md), [004](docs/ADR-004-evaluation-teaching-workshop.md) | Architecture decisions |

## Layout

```
genesis/      kernel (models, world, engine, invention), controllers, storage, reducer, experiments, profiling, API, CLI
frontend/     React + TypeScript + Vite observatory (built into frontend/dist and served by the API)
tests/        invariant, lifecycle, storage, reducer, optimisation, persistence and API tests
tools/        evidence generation, search-space enumeration, restart verification, the v0.2 audit
scenarios/    sample world configurations
evidence/     v0.4.0/ (current: protocol, calibration, A, B, sealed results), v0.3.0/, superseded/v0.2.0/
docs/         the documents above
```
