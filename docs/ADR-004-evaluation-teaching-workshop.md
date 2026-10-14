# ADR 004: Protected evaluation, costly teaching, and a richer invention task

Accepted 2026-10-14. Extends [ADR-003](ADR-003-storage-succession-audit.md). Engine `0.4.0`, rules `phase-world-4`.

## Context

v0.3.0 removed per-case held-out feedback, but every proposal still received pass/fail on its "held-out" partition, so that partition was adaptive feedback rather than an unseen test. Knowledge could move only through the library or a debug package. The 16-program task reaches its optimum within about 20 ticks, so inheritance experiments could show retention but not cumulative improvement.

## Decisions

### 1. Three evaluation roles

| Role | Who sees what | Label |
|---|---|---|
| **Development cases** (24 per task version) | The proposer gets per-case results from `test_artifact` | `dev-tested` |
| **Validation cases** (24) | `submit_artifact` returns only *admitted / not admitted*, so this set **is feedback**: every submission learns one bit | `admitted (operational, validation-adaptive)` |
| **Sealed cases** (48) | Generated from a seed kept in a protected manifest outside world state. Scored only by `genesis/sealed.py`, after a run is closed, on artifacts frozen by validation evidence. No engine, controller, observation, storage or API code imports it. | final score |

**Selection.** At each cohort boundary and at the run's end, the engine records a **freeze**. The freeze picks, by validation score with no sealed input, the best admitted artifact created by the ending cohort, and the best one accessible to it. Sealed scores are computed afterwards and written only to experiment reports. They never enter the world database or affect any trajectory, and a test checks this.

**Commitment.** The frozen protocol records a SHA-256 commitment to the sealed case list before any evaluation run.

**Legacy task.** The `phase-1` task keeps its v0.3 evaluator and its `verified` label. It is now documented as "verified (legacy: training and held-out partitions, both adaptive)". Historical labels are not renamed.

### 2. Teaching sessions (`teaching-1`)

`state.sessions[id]` records the teacher, learner, artifact, stage, costs per participant, work done, practice outcomes, assessment, interruption, and the first independent use. The lifecycle:

```
offered ──accept──▶ instruction ──(teacher 3 work + learner 3 work)──▶ practice ──(2 runs)──▶ acquired | failed
   │                    │                                                  │
   └ expires (6 ticks)  └──── interrupted (retirement, inactivity, 8 ticks without progress, abandonment) ─┘
```

**Consolidation.** "Accepted" and "instruction" are one stage, because acceptance starts instruction. "Assessed" is the transition at the end of practice, and the assessment is stored on the session.

**Eligibility.** The teacher must already *hold* the artifact. The learner must not hold it, must hold every component the program calls (prerequisites), and both must be active members of the same settlement. Naming an artifact ID grants nothing.

**Costs and scheduling.**

| Action | Requirements | Cost |
|---|---|---|
| `teach_step` | Co-located (≤ 1 tile) | 2 energy to the teacher |
| `learn_step` | Co-located (≤ 1 tile) | 1 energy to the learner |
| `practice_step` | Learner's own ore and energy | One real supervised execution of the program |

During instruction, both participants are **reserved**: they may only take their session step, `consume` or `abandon_session`. During practice the learner is not reserved, but practice consumes its action for that tick, and the session interrupts if it stalls.

**Assessment.** The learner passes if both practice runs were feasible and each cost no more per alloy than the baseline program under the same conditions. Only then is the artifact added to the learner's holdings, with a transmission via the session. A later `use_artifact` outside the session is recorded as the **first independent use**.

Exposure (the offer), acquisition (assessment passed) and successful use are three separate milestones. There are no random failures.

**Request channel.** A learner signals need with the message `request_lesson`, which is a claim, not a program. That word exists only when `teaching` is enabled. No message can carry a program.

### 3. Richer task `workshop-1`

The workflow is a multi-stage batch. A program decides **batch size** (1–4), **heat** (0–3), **mode** (0/1) and **flux** (0/1, costing 1 food), from local measurements (`phase`, `humidity`) and its own holdings (`ore`, `energy`).

Hidden per-world parameters are drawn from the world seed:

- a phase split `s` ∈ 4–8
- a heat offset `o` ∈ 0–2, with optimal heat `h* = min(3, (humidity + o) // 3)`
- a flux threshold `f` ∈ 4–6

| Quantity | Rule |
|---|---|
| Energy | `3 + b·(2 if the mode matches the phase else 5) + 2h`. Batching amortises setup. |
| Ore | `2b` is consumed. Alloy yield is `b − ⌈b·|h − h*|/3⌉`, minus 1 if the air is humid and no flux is used. |
| Time | The agent is busy for `b − 1` extra ticks. |
| Infeasible batch | Too little ore or energy: rejected in the world, or a penalty of 10 per case in evaluation. |

**Objective (fixed in advance):** pooled `(energy + 4·ore wasted + 3·food) / alloy` over a case set. Lower is better. The baseline is `batch 1, heat 1, mode 0, no flux`, which is what `produce` runs.

The decisions interact:

- The right heat depends on humidity.
- Batch size trades setup savings against feasibility, which depends on ore and energy and therefore on mode correctness.
- Flux matters only above a hidden threshold.

**Language.** `workflow{batch, heat, mode, flux}` over expressions `const | if_lt(measure, threshold, then, else) | call(component)`. Components are separate artifacts (`component{expr}`). Executing a call requires *holding* the component, which makes components real prerequisites. Limits: 48 nodes, depth 6, 4096 bytes, 64 evaluation steps. Nothing is executed as host code.

**Search.** The offline researcher hill-climbs over a declared neighbourhood: constant ±1, threshold shift ±1, splitting a leaf on one measure, and recombining a field from another held artifact (composition). It uses development feedback only, and submits a candidate when its development score beats the current best. Every agent has the same budget per lifetime.

### 4. Cohort lifecycle (`lifecycle: cohorts`)

Every `cohort_ticks`, the engine:

1. records a freeze,
2. retires every active agent, moving their inventory to storage,
3. creates a fresh cohort with the same homes and roles.

`cross_cohort_access` decides whether the library shows artifacts from earlier cohorts. Within a cohort, library sharing is identical in both conditions. Teaching is off in this experiment, so the library is the only route between cohorts.

### 5. Compatibility

New behaviour is gated by scenario fields whose defaults reproduce v0.3 behaviour: `task: phase-1`, `teaching: false`, `lifecycle: single`. A regression test re-runs a v0.3.0 evidence configuration and compares its reducer output with the stored v0.3.0 reducer file. Tag `v0.3.0` preserves the exact code. Runs written by v0.3 remain read-only, as before.

## Consequences

Final evaluation becomes an independent estimate *for frozen artifacts only*. Teaching becomes a third knowledge path, with measurable costs and failure modes. Whether knowledge preservation produces cumulative improvement on `workshop-1` is a question for the experiments, not something built in.
