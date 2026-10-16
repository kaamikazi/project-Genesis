# GENESIS

**A persistent, inspectable digital world where inhabitants act under enforced rules, invent procedures that are executed and measured, and pass verified knowledge on, including to successors after their creators retire.**

GENESIS runs fully offline on a laptop. It needs no API key, GPU or cloud service. Every reported number is recomputed from immutable events by an independent reducer.

> **v0.5.2 (M5c)** adds:
> - versioned random streams and paired world manifests with preflight checks
> - a bounded, frozen study of admission panels on 12 distinct task parameterisations, with fresh sealed-4 final cases
> - leave-one-out tests of the allocation bundle
>
> The inhabitants still follow designed offline policies, and nothing is emergent. **Admission panels made no consistent difference. The allocation bundle's earlier harm did not reproduce.** The next milestone is the M6 controller integration ([handoff](docs/M6_HANDOFF.md)). See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md). Earlier releases are preserved as git tags.

## What happens in a run

1. Eight inhabitants in two settlements gather food and ore, eat, trade, share communal storage, and convert 2 ore into 1 alloy.
2. Conversion costs 2 or 6 energy, depending on a hidden phase field that each agent senses only where it stands.
3. One researcher per settlement searches a bounded program language. An independent evaluator tests each candidate on training and held-out cases. The proposer learns only aggregate feedback.
4. Researchers revise their procedures. A revision is accepted only if it beats its parent on the same cases: 32 → 28 → 24 energy. Here 24 is provably the minimum for this evaluation set.
5. With library access, other inhabitants learn the current procedure. An adoption counts only after a logged transmission followed by a measured saving.
6. Creators can retire and be replaced by **fresh successors**. A successor starts with nothing and must acquire the procedure through the path its policy allows. The observatory's *Why this counts as retention* panel shows every link.

## What v0.5.2 found

**Design.** A frozen protocol ran on 12 paired worlds, each with a distinct hidden parameterisation. Within a block, every condition shares the same world and controller randomness. Final picks are chosen on one shared selection panel and scored on fresh sealed-4 cases. Lower is better. No world failed and none is missing.

| Final pick, sealed-4 (mean of 12) | fixed admission | cohort panels |
|---|---|---|
| first-improvement | 9.01 | 8.93 |
| repaired beam | 9.54 | 9.51 |

- **Admission panels vs fixed admission cases:** no consistent difference for either policy (6–5–1 and 5–7 wins–losses–ties).
- **First-improvement vs beam:** first-improvement was lower than beam in 10 of 12 worlds under panels. Under fixed admission the difference was not consistent.
- **Allocation bundle vs plain beam:** no consistent difference (7–4–1). M5b's finding that the bundle was harmful did not reproduce.
  - Removing the reserve guard changed no final pick in any world.
  - Neither the stale-frontier guard nor the novelty guard showed a consistent effect.

**Earlier milestones:** the v0.5.1 results (repairs, allocation, mentorship) are in [evidence/v0.5.1](evidence/v0.5.1/README.md). the v0.5.0 results (beam search, components, overlapping generations) are in [evidence/v0.5.0](evidence/v0.5.0/README.md), with labelled corrections in [evidence/v0.5.1/corrections-v0.5.0](evidence/v0.5.1/corrections-v0.5.0/CORRECTIONS.md). The v0.4.0 results (protected evaluation, teaching, cumulative cohorts) are in [evidence/v0.4.0](evidence/v0.4.0/README.md) and [docs/history](docs/history/IMPLEMENTATION_STATUS-v0.4.0.md). The v0.3.0 results (phase-1 task, controlled succession) are in [evidence/v0.3.0](evidence/v0.3.0/README.md). The v0.2.0 corrections are in the [audit](docs/audit/AUDIT-v0.2.0.md).

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
| [METRICS](docs/METRICS.md) | The versioned metric dictionary |
| [M6_HANDOFF](docs/M6_HANDOFF.md) | Controller interfaces and the remaining integration work for M6 |
| [ROADMAP](docs/ROADMAP.md) | Milestones and their dependencies |
| [RUNBOOK](docs/RUNBOOK.md) | Restart, replay, forks with interventions, export, reducer, profiling |
| [DEMO](docs/DEMO.md) | A guided walkthrough |
| [RELATED_WORK](docs/RELATED_WORK.md) | Primary references and open questions |
| ADRs: [001](docs/ADR-001-foundation.md), [002](docs/ADR-002-revisions-removal-versioning.md), [003](docs/ADR-003-storage-succession-audit.md), [004](docs/ADR-004-evaluation-teaching-workshop.md), [005](docs/ADR-005-search-components-mentorship.md), [006](docs/ADR-006-repair-allocation-mentorship.md), [007](docs/ADR-007-paired-worlds-admission.md) | Architecture decisions |

## Layout

```
genesis/      kernel (models, world, engine, invention), controllers, storage, reducer, experiments, profiling, API, CLI
frontend/     React + TypeScript + Vite observatory (built into frontend/dist and served by the API)
tests/        invariant, lifecycle, storage, reducer, optimisation, persistence and API tests
tools/        evidence generation per release, calibration, diagnosis, restart verification, CPU benchmark, audits
scenarios/    sample world configurations
evidence/     v0.5.2/ (current: manifest, preflight, calibration, protocol, primary, ablation, sealed-4), v0.5.1/, v0.5.0/, v0.4.0/, v0.3.0/, superseded/v0.2.0/
docs/         the documents above
```
