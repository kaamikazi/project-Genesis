# Invention protocol (`phase-evaluator-2`)

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
- uses, each with the phase, chosen mode, energy and baseline energy
- independent adopters

Content hashes are re-checked whenever an artifact is accessed, loaded, imported or stored. SQLite triggers make the artifact table immutable.

## How candidates are generated: bounded search

The offline researcher (one per settlement) is **not** a language model. It searches a declared, finite space.

1. **Original candidates:** the grammar `if_phase_lt t → mode d else mode 1−d` for `t ∈ 2..9`, `d ∈ {0, 1}`, giving 16 programs. Each researcher tries them in an order keyed by its own controller seed. It stops at the first verified result.
2. **Revisions:** once it has a current verified artifact, the researcher tries the neighbourhood `{threshold − 1, threshold + 1, swap branches}`. The order is again keyed. It stops when every neighbour of its current best has been tried, which is a local optimum.
3. **Budget:** 16 proposals per researcher (`search_budget`), counting originals and revisions. Each proposal costs 1 energy and each test costs 3. These search costs appear in the metrics.

The researcher does not know where the optimal threshold lies. It learns only pass/fail and total energy from its own tests, through its memory of the action results. Held-out cases are never shown case by case to any controller. The observer UI can show them.

## Evaluation

`PhaseEvaluator` re-executes the program on fixed cases with the same `conversion()` function that production uses.

- **Training phases:** 1, 4, 7, 10
- **Held-out phases:** 0, 2, 3, 5, 6, 8, 9, 11, disjoint from training
- **Baseline:** fixed mode 0 (the `produce` action)

A program is **verified** only if all of the following hold:

1. No case uses more energy than the baseline.
2. The training partition saves at least 25% against the baseline.
3. The held-out partition saves at least 25% against the baseline.
4. For a revision: its total energy is strictly lower than the parent's. The evaluator recomputes the parent's energy itself and does not read the stored value.

Otherwise the program is **rejected**, and every failed criterion is listed in `evaluation.failures`. For example: `phase 5: 6 energy is worse than baseline 2`, `held-out saving 0% is below 25%`, or `no improvement over parent (36 vs 36 energy)`.

When a revision is verified, its parent becomes `superseded` (`superseded_by` points to the revision). The library then offers only the newest version. Agents who learned an older version may keep using it.

**Scope of "verified":** phase 0..11, 2 ore → 1 alloy, energy only, in this world. It says nothing about generalising across worlds.

## What a run actually shows

With seed 42, both researchers first verify `threshold 9`, which uses 36 energy against a baseline of 48. They then climb verified revisions to 8 (32), 7 (28) and 6 (24). Here 6 is the optimum, and the evaluator rejects every neighbour of it. Each step is a separate artifact linked to its parent. `tests/test_engine.py::test_search_climbs_a_verified_lineage_during_the_run` checks this behaviour.

This is a small hill-climb in a 1-D space. It is real and measured, and it is not open-ended invention.

## Known limitations

- The search space is tiny and was designed by hand. The optimum is reachable by design.
- A researcher still receives aggregate pass/fail feedback after each held-out evaluation, so repeated testing slowly leaks information about the held-out set.
- No arbitrary code is executed. An unrestricted-code sandbox would be a separate project.
