# Experiment protocol (`paired-phase-2`)

## Questions

1. **Sharing:** Does access to other agents' verified procedures change collective production efficiency under these mechanics?
2. **Retention:** When procedure creators leave, does their knowledge keep working? Is that different from losing the same number of ordinary workers?

These are exploratory checks of a designed mechanism. They are not tests of a general hypothesis about artificial societies.

## Conditions (per seed)

| Condition | `sharing` | `controller` | `removal` |
|---|---|---|---|
| `sharing` | on | search | none |
| `restricted` | off | search | none |
| `baseline` | on | baseline (no researchers) | none |
| `sharing-remove-creators` | on | search | creators |
| `sharing-remove-matched` | on | search | matched |
| `restricted-remove-creators` | off | search | creators |
| `restricted-remove-matched` | off | search | matched |

Within a seed, every condition uses the same terrain, sites, phase field, population, rules, evaluator, search budget, run length and removal tick. `test_experiment_configuration_parity` checks this. The trajectories are **not** identical, because agents act differently and so stand in different places.

## What the sharing intervention changes, and what it does not

**Changes:** whether an agent may `inspect_artifact` a verified procedure created by someone else in its settlement's library.

**Unchanged:**

- trade and transfers
- the two-word message vocabulary, which cannot carry a procedure
- the absence of other agents' action histories from observations
- each researcher's own search

The restricted condition was audited in a test: no artifacts are visible, `inspect_artifact` is rejected, and no transmissions or adoptions occur. So the intervention is restricted to procedure sharing and is not a bundled change.

## Removal design

At `removal_tick` (half the run by default):

- **creators:** active creators of currently verified artifacts retire.
- **matched:** the same number of non-creators from the same settlements retire.

All retirees' inventories move to settlement storage. "Creators minus matched" therefore estimates the cost of losing the *knowledge holders* beyond the cost of losing *any* workers. Comparing that difference with and without sharing shows whether the library preserves the procedure.

## Metrics (per world)

`produced`, `production_energy`, `energy_per_alloy`, `produced_after_removal`, `energy_per_alloy_after_removal`, `uses_after_creator_removal`, `learned_after_creator_removal`, `adoptions` (distinct non-creator agents with a measured saving, per artifact), `verified_artifacts`, `rejected_artifacts`, `revisions_verified`, `search_proposals`, `evaluation_cases`, `accepted`/`rejected` actions, `controller_failures`, `active_population`, `inventory_range` (unequal holdings), `transfers`, `model_calls`, `tokens`, `cost_usd` (all 0), wall time, and the final state hash.

## Reporting rules

- Every planned attempt is written to `comparison.json` **before** it runs, then updated with `completed` or `failed` and the failure reason. Nothing is dropped.
- Every completed world is replayed from its records and must match its final state hash. A mismatch counts as a failure.
- The full export of every world is saved next to the report as `{seed}-{condition}.json.gz`, so any number can be traced to its events.
- **One world is one experimental unit.** Twenty agents in one world are not twenty samples.
- The controllers are deterministic, so seeds vary only the environment. Three seeds are a smoke test. Choosing a sample size for a real study would need variance estimates and, once LLM controllers exist, controller stochasticity.

## Interpretation limits

The outcome follows largely from the design. The optimal procedure saves energy, and sharing lets producers use it, so a lower energy cost per alloy under sharing is expected. The point of the run is to show that the software measures and exposes this honestly, including:

- **Total alloy is identical across search conditions.** Finite ore caps output at 512, so the effect is on cost, not volume.
- Researchers in the restricted condition still improve their own production through search.
- Removing creators under restriction loses the procedure entirely, while under sharing the library keeps it in use.

Making stronger claims would need unfamiliar worlds, stochastic controllers, held-out mechanics, and pre-registered thresholds.

## How to run it

```bash
python -m genesis.cli compare --seeds 11 42 77 --ticks 160
```

Output goes to `evidence/comparison/`, and the observatory's **Experiments** page reads it.
