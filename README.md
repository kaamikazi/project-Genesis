# GENESIS

**A persistent, inspectable digital world where inhabitants act under enforced rules, invent procedures that are executed and measured, and pass verified knowledge on, including to successors after their creators retire.**

GENESIS runs fully offline on a laptop. It needs no API key, GPU or cloud service. Every reported number is recomputed from immutable events by an independent reducer.

> **v0.5.0** adds:
> - **search diagnostics and shared search credits:** proposals, tests and submissions draw on one pool per researcher lifetime
> - **a beam search policy**, compared under the same pool with the v0.4 first-improvement policy, which is kept as the reference
> - **live reusable components:** extraction, in-host admission, refactoring, revision, and closures resolved by hash
> - **dependency-aware lessons** and **overlapping generations**
> - **a fresh sealed final evaluation** (`workshop-sealed-2`)
>
> The inhabitants still follow designed offline policies, and nothing is emergent. **Beam search turned out not to be stronger.** See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md). v0.4.0 and v0.3.0 are preserved as git tags.

## What happens in a run

1. Eight inhabitants in two settlements gather food and ore, eat, trade, share communal storage, and convert 2 ore into 1 alloy.
2. Conversion costs 2 or 6 energy, depending on a hidden phase field that each agent senses only where it stands.
3. One researcher per settlement searches a bounded program language. An independent evaluator tests each candidate on training and held-out cases. The proposer learns only aggregate feedback.
4. Researchers revise their procedures. A revision is accepted only if it beats its parent on the same cases: 32 → 28 → 24 energy. Here 24 is provably the minimum for this evaluation set.
5. With library access, other inhabitants learn the current procedure. An adoption counts only after a logged transmission followed by a measured saving.
6. Creators can retire and be replaced by **fresh successors**. A successor starts with nothing and must acquire the procedure through the path its policy allows. The observatory's *Why this counts as retention* panel shows every link.

## What v0.5.0 found

These results are exploratory: 5 new evaluation worlds, a protocol and claim rule frozen before running, and offline controllers. Scores are cost per alloy, so lower is better. A direction is claimed only if it holds in at least 4 of 5 paired worlds.

**Experiment P: is beam search stronger under the same 48-credit budget?** No.

| Final held best | first-improvement (v0.4 policy) | beam |
|---|---|---|
| Preserved access, validation / sealed | 7.43 / 9.58 | 8.39 / 9.55 |
| Reset access, validation / sealed | 8.32 / 8.72 | 9.69 / 11.31 |

- **Validation:** first-improvement was better in 4 of 5 worlds.
- **Sealed cases:** no consistent difference.
- **Credits:** both spent almost all of them, but beam turned them into 30% fewer novel evaluations. It produced more repeated results, left more proposals untested, and spent credits on component tests.
- **Component operators** made no consistent difference.

**Preserved knowledge looked better on validation (5 of 5) but was worse on fresh sealed cases (4 of 5)** for the first-improvement policy. Lineages repeatedly admitted against the same adaptive validation cases overfit them.

**Experiment T: does teaching carry knowledge across overlapping generations?**

- **Yes, but as retention.** 49 cross-generation lessons: 22 acquired, 12 failed, 15 interrupted (mostly by scheduled retirement).
- In 2 of 5 worlds, teaching carried a better workflow to the next generation, which then created nothing better.
- **Teaching-only vs none:** no consistent difference.
- **Library vs none:** library better in 4 of 5.
- **Dependencies:** the 4 lessons that carried a component dependency were all cut off by retirement. A complete component handoff is shown only by a labelled, scripted demonstration.

**Earlier milestones:** the v0.4.0 results (protected evaluation, teaching, cumulative cohorts) are in [evidence/v0.4.0](evidence/v0.4.0/README.md) and [docs/history](docs/history/IMPLEMENTATION_STATUS-v0.4.0.md). the v0.3.0 results (phase-1 task, controlled succession) are in [evidence/v0.3.0](evidence/v0.3.0/README.md). The v0.2.0 corrections are in the [audit](docs/audit/AUDIT-v0.2.0.md).

## Documentation

| Document | What it covers |
|---|---|
| [VISION](docs/VISION.md) | The ambition and present limits |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Authority boundaries, tick execution, persistence, copy-on-write, API |
| [WORLD_RULES](docs/WORLD_RULES.md) | Accounting, storage, actions, the phase mechanic, retirement and succession |
| [AGENT_MODEL](docs/AGENT_MODEL.md) | State, observations, the hidden-parameter independence test, controllers |
| [INVENTION_PROTOCOL](docs/INVENTION_PROTOCOL.md) | Language, search, evaluator, feedback separation, scoped optimality |
| [EXPERIMENT_PROTOCOL](docs/EXPERIMENT_PROTOCOL.md) | Descriptive vs controlled experiments, metric definitions, aggregation, Milestone 4 and 5 protocols |
| [audit/AUDIT-v0.2.0](docs/audit/AUDIT-v0.2.0.md) | Claim-by-claim audit of the previous release |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | What works, measurements, gaps |
| [ROADMAP](docs/ROADMAP.md) | Milestones and their dependencies |
| [RUNBOOK](docs/RUNBOOK.md) | Restart, replay, forks with interventions, export, reducer, profiling |
| [DEMO](docs/DEMO.md) | A guided walkthrough |
| [RELATED_WORK](docs/RELATED_WORK.md) | Primary references and open questions |
| ADRs: [001](docs/ADR-001-foundation.md), [002](docs/ADR-002-revisions-removal-versioning.md), [003](docs/ADR-003-storage-succession-audit.md), [004](docs/ADR-004-evaluation-teaching-workshop.md), [005](docs/ADR-005-search-components-mentorship.md) | Architecture decisions |

## Layout

```
genesis/      kernel (models, world, engine, invention), controllers, storage, reducer, experiments, profiling, API, CLI
frontend/     React + TypeScript + Vite observatory (built into frontend/dist and served by the API)
tests/        invariant, lifecycle, storage, reducer, optimisation, persistence and API tests
tools/        evidence generation per release, calibration, diagnosis, restart verification, CPU benchmark, audits
scenarios/    sample world configurations
evidence/     v0.5.0/ (current: protocol, calibration, P, T, sealed-2, diagnosis, demonstration), v0.4.0/, v0.3.0/, superseded/v0.2.0/
docs/         the documents above
```
