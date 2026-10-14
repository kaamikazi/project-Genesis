# Invention protocol (`phase-evaluator-3`)

An invention in GENESIS is an immutable program that is executed and measured. A claim about one changes nothing. This document describes the language, the search that generates candidates, and the evaluator that accepts or rejects them.

## The program language

Programs are typed JSON trees interpreted by `genesis/invention.py`. Nothing is passed to `eval` or `exec`.

```json
{"op": "if_phase_lt", "threshold": 6,
 "then": {"op": "mode", "value": 0},
 "else": {"op": "mode", "value": 1}}
```

| Operator | Fields | Meaning |
|---|---|---|
| `mode` | `value ∈ {0, 1}` | Choose a conversion mode. |
| `if_phase_lt` | `threshold ∈ 0..12`, `then`, `else` | Branch on the agent's locally observed phase. |

Limits: at most 15 nodes, depth 4, 2,048 canonical bytes and 8 execution steps. Executing a program requires the `converter` capability. Unknown operators, extra fields and booleans used as integers are rejected. A program can read only the phase passed to it. It has no access to world state.

## Artifacts

An artifact's ID is the SHA-256 of `{program, creator, parent, language}`. Each artifact records:

- creator, creation event and settlement
- parent and `generation` (0 for an original)
- `status`: `proposed` → `verified` | `rejected`, and later `superseded`
- the full evaluation, including every case
- transmissions (who learned it, when, and through which channel)
- uses (the last 64), each with the phase, chosen mode, energy and baseline energy
- `first_uses`: each agent's first execution, kept permanently so a successor's first use is never truncated
- independent adopters

Content hashes are re-checked whenever an artifact is accessed, loaded, imported or stored. SQLite triggers make the artifact table immutable.

## How candidates are generated: bounded search

The offline researcher (one per settlement) is **not** a language model. It searches a declared, finite space.

1. **Learn before searching.** If its library offers a verified procedure and it holds none, the researcher inspects it first. Successor researchers rely on this.
2. **Original candidates.** If it holds no verified procedure, it searches the grammar `if_phase_lt t → mode d else mode 1−d` for `t ∈ 2..9`, `d ∈ {0, 1}`: 16 programs, tried in an order keyed by the controller's private seed.
3. **Revisions.** Starting from the best verified procedure it holds, whether its own or inherited, it tries the neighbourhood `{threshold − 1, threshold + 1, swap branches}`. It stops once every neighbour has been tried (a local optimum).
4. **Budget.** 16 proposals per researcher (`search_budget`). A proposal costs 1 energy and a test costs 3. The reducer reports these as the `search` and `evaluation` energy categories.

A revision of someone else's procedure keeps the full chain: the parent's creator, the reviser, the generation, and the transmission that put the parent in the reviser's hands.

**Feedback separation.** After `test_artifact`, the proposer receives only:

- `status`
- training energy against the training baseline
- `training` and `held_out` as `pass` or `fail`
- `improves_on_parent`

Case-level results, including which held-out phases failed, stay on the artifact record, which only the observer reads. v0.2.0 leaked held-out case failures into agent memories; see [audit](audit/AUDIT-v0.2.0.md), item 8. Partition-level pass/fail still gives a little aggregate information about the held-out set over repeated tests.

## Evaluation

`PhaseEvaluator` re-executes the program on fixed cases with the same `conversion()` function that production uses.

- **Training phases:** 1, 4, 7, 10
- **Held-out phases:** 0, 2, 3, 5, 6, 8, 9, 11, disjoint from training
- **Baseline:** fixed mode 0 (the `produce` action)
- **Inputs:** every case converts 2 ore into 1 alloy. Only energy varies, so no gain can come from cheaper inputs.

A program is **verified** only if all of the following hold:

1. No case in either partition uses more energy than the baseline.
2. Each partition saves at least 25% against the baseline.
3. For a revision: total energy is strictly lower than the parent's **on the same cases**. The evaluator re-executes the parent itself and asserts that the case lists are identical.

Otherwise the program is **rejected**, and every failed criterion is listed in `evaluation.failures`. Examples: `held-out phase 5: 6 energy is worse than baseline 2`, `training saving 0% is below 25%`, `no improvement over parent (24 vs 24 energy)`. Duplicate proposals (same program, creator and parent) are rejected at proposal time as a logged `action_rejected`.

When a revision is verified, its parent becomes `superseded`. Holders of an older version may keep using it.

**Scope of "verified":** phase 0..11, 2 ore → 1 alloy, energy only, in this world.

## Optimality, scoped

[`evidence/v0.3.0/invention/search-space.json`](../evidence/v0.3.0/invention/search-space.json) evaluates every single-threshold program (thresholds 0–12, both orientations) and both constants.

**Lower bound.** Every case costs at least 2 energy under `conversion()`, and there are 12 cases, so **no program in the language can score below 24** on this evaluation set. Threshold 6 (then mode 0) reaches 24 and is the only program that does. Four programs in the controller's grammar verify (thresholds 6, 7, 8 and 9 with mode 0).

"24 is optimal" therefore means optimal **for these 12 cases, this conversion rule, and energy as the objective**, and nothing more.

## What a run actually shows (v0.3.0)

With the default controller seed, the Hearth researcher climbs 32 → 28 → 24 and the Haven researcher finds 24 directly (all seeds; see `test_search_climbs_a_verified_lineage_during_the_run`). In the live succession continuation, successor researchers learn the inherited 24-energy procedure and then propose its three neighbours. All three are rejected for not improving on the parent. This is a real, recorded cross-generation revision attempt, and it fails because the inherited procedure is already optimal.

This is a small hill-climb in a 1-D space. It is real and measured, and it is not open-ended invention.

## Known limitations

- The search space is tiny and designed by hand. The optimum is reachable by design and is reached within about 20 ticks.
- Partition-level feedback slowly leaks aggregate information about the held-out set.
- No arbitrary code is executed. An unrestricted-code sandbox would be a separate project.
