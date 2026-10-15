# GENESIS

**A persistent, inspectable digital world where inhabitants act under enforced rules, invent procedures that are executed and measured, and pass verified knowledge on, including to successors after their creators retire.**

GENESIS runs fully offline on a laptop. It needs no API key, GPU or cloud service. Every reported number is recomputed from immutable events by an independent reducer.

> **v0.5.1 (M5b)** repairs three defects found after v0.5.0:
> - a stale-reference resubmission loop
> - first-improvement revising superseded workflows
> - library copies that left out components
>
> It also corrects metric definitions and comparison denominators, and runs two prospective experiments: allocation and mentorship. v0.5.0 is preserved unchanged and is described as run with those defects.
>
> The inhabitants still follow designed offline policies, and nothing is emergent. **The allocation bundle made search worse, and teaching did not improve outcomes.** See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md). v0.5.0, v0.4.0 and v0.3.0 are preserved as git tags.

## What happens in a run

1. Eight inhabitants in two settlements gather food and ore, eat, trade, share communal storage, and convert 2 ore into 1 alloy.
2. Conversion costs 2 or 6 energy, depending on a hidden phase field that each agent senses only where it stands.
3. One researcher per settlement searches a bounded program language. An independent evaluator tests each candidate on training and held-out cases. The proposer learns only aggregate feedback.
4. Researchers revise their procedures. A revision is accepted only if it beats its parent on the same cases: 32 → 28 → 24 energy. Here 24 is provably the minimum for this evaluation set.
5. With library access, other inhabitants learn the current procedure. An adoption counts only after a logged transmission followed by a measured saving.
6. Creators can retire and be replaced by **fresh successors**. A successor starts with nothing and must acquire the procedure through the path its policy allows. The observatory's *Why this counts as retention* panel shows every link.

## What v0.5.1 found

**Repairs.** Minimal reproductions that failed on every tick in v0.5.0 now fail 0 times. In the repaired rerun of the v0.5.0 worlds, beam/preserved's alloy rose from 1,560 to 2,230: its v0.5.0 production deficit came from 1,390 executions rejected for a missing component. The rerun is labelled retrospective.

**Prospective experiments.** Protocol frozen first; seeds 221–226; fresh sealed-3 cases. Scores are cost per alloy, so lower is better.

| Final held best, sealed-3 (mean of 6) | preserved access | reset access |
|---|---|---|
| repaired beam | 10.56 | 10.32 |
| beam + allocation bundle | 11.05 | 12.74 |
| first-improvement (reference) | 9.71 | 11.66 |

- **The allocation bundle was worse than plain beam** in every world. It did remove repeated behaviour (211 → 100) and untested proposals (4 → 0), but it spent fewer credits and withdrew stepping stones. Which guard caused the loss is not identified.
- **Dependency teaching now finishes sometimes.** On the 80/40 schedule chosen in calibration, 8 of 26 dependency lessons were acquired, and learners used the taught component workflows 233 times after their teachers retired. Final outcomes still matched no-transfer in 5 of 6 worlds.
- **Caveat found after the runs.** Seeds 221/222 and 225/226 have identical hidden parameters, and the controller seed is the same everywhere, so those pairs duplicated each other's invention outcomes. There are 4 distinct worlds, not 6; the post-hoc analysis over them agrees with every direction above.

**Earlier milestones:** the v0.5.0 results (beam search, components, overlapping generations) are in [evidence/v0.5.0](evidence/v0.5.0/README.md), with labelled corrections in [evidence/v0.5.1/corrections-v0.5.0](evidence/v0.5.1/corrections-v0.5.0/CORRECTIONS.md). The v0.4.0 results (protected evaluation, teaching, cumulative cohorts) are in [evidence/v0.4.0](evidence/v0.4.0/README.md) and [docs/history](docs/history/IMPLEMENTATION_STATUS-v0.4.0.md). The v0.3.0 results (phase-1 task, controlled succession) are in [evidence/v0.3.0](evidence/v0.3.0/README.md). The v0.2.0 corrections are in the [audit](docs/audit/AUDIT-v0.2.0.md).

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
| [ROADMAP](docs/ROADMAP.md) | Milestones and their dependencies |
| [RUNBOOK](docs/RUNBOOK.md) | Restart, replay, forks with interventions, export, reducer, profiling |
| [DEMO](docs/DEMO.md) | A guided walkthrough |
| [RELATED_WORK](docs/RELATED_WORK.md) | Primary references and open questions |
| ADRs: [001](docs/ADR-001-foundation.md), [002](docs/ADR-002-revisions-removal-versioning.md), [003](docs/ADR-003-storage-succession-audit.md), [004](docs/ADR-004-evaluation-teaching-workshop.md), [005](docs/ADR-005-search-components-mentorship.md), [006](docs/ADR-006-repair-allocation-mentorship.md) | Architecture decisions |

## Layout

```
genesis/      kernel (models, world, engine, invention), controllers, storage, reducer, experiments, profiling, API, CLI
frontend/     React + TypeScript + Vite observatory (built into frontend/dist and served by the API)
tests/        invariant, lifecycle, storage, reducer, optimisation, persistence and API tests
tools/        evidence generation per release, calibration, diagnosis, restart verification, CPU benchmark, audits
scenarios/    sample world configurations
evidence/     v0.5.1/ (current: bugfix, corrections, rerun, calibration, protocol, allocation, mentorship, sealed-3), v0.5.0/, v0.4.0/, v0.3.0/, superseded/v0.2.0/
docs/         the documents above
```
