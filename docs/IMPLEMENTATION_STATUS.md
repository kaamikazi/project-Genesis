# Implementation status, v0.5.2 / M5c (2026-10-16)

Engine `0.5.2` · rules `phase-world-5.2` · evaluators `phase-evaluator-3` (legacy), `workshop-evaluator-4`, `workshop-sealed-4` · reducer `genesis.reducer/3` · metrics `genesis-metrics-1`.

- **Evidence:** [`evidence/v0.5.2/`](../evidence/v0.5.2/README.md); tables in [SUMMARY.md](../evidence/v0.5.2/SUMMARY.md)
- **Decisions:** [ADR-007](ADR-007-paired-worlds-admission.md)
- **Next milestone:** [M6 handoff](M6_HANDOFF.md)
- **Previous status:** [v0.5.1](history/IMPLEMENTATION_STATUS-v0.5.1.md), [v0.5.0](history/IMPLEMENTATION_STATUS-v0.5.0.md), [v0.4.0](history/IMPLEMENTATION_STATUS-v0.4.0.md). All earlier releases and their evidence are unchanged.

## Verification

| Check | Result |
|---|---|
| Baseline before any change (tag v0.5.1) | 148 passed, build OK |
| `python -m pytest -q` | **165 passed**: 16 new v0.5.2 tests and 1 new copy-on-write scenario (streams, panels, selection panel, a leave-one-out flag, fuzzed) |
| `npm run build` (with `tsc --noEmit`) | Succeeded |
| `python tools/generate_evidence_m5c.py` | All 11 steps exited 0, from runtime commit `e38dc6b`, clean at start and end |
| Interrupted first attempt | The first run was killed during calibration when the session ended, before any preflight or freeze. It is kept as `calibration-interrupted-attempt-1/` (2 of 24 worlds done) and was restarted from scratch. |
| Restart with streams and panels | 8 of 8 checks pass |
| Parity | Every condition in every block started from the same physical world, hidden parameters and controller stream (12 of 12 blocks, both studies) |

## What was built

| Capability | Where |
|---|---|
| Versioned random streams (`seed_scheme: streams-1`): hidden combination, terrain/environment and controller seeds are separate sources, and the label seed is not a randomness source. `legacy` reproduces every earlier world. | `genesis/models.py`, `world.py`, `workshop.py`; `test_streams_*`, `test_legacy_*` |
| Paired world manifest: stratified draw without replacement, 3 calibration + 12 evaluation blocks, streams keyed by block | `tools/world_manifest_m5c.py`; `test_manifest_*` |
| Preflight: distinct combinations, no calibration reuse, distinct streams, matched initial worlds, disjoint partitions, resource horizon, runtime/storage budget, disk | `test_preflight_catches_*` |
| Shared final-selection panel: bounded, counted, observer-side; the same rule in every condition | `engine.freeze`; `test_final_selection_*` |
| Admission panels: activation per cohort, caps, child and reference on identical cases | `test_panels_activate_*` |
| Leave-one-out allocation flags; submit-time stale safety is never disabled | `alloc_disable`; `test_leave_one_out_*` |
| Sealed-4: disjoint from everything earlier, including panels and the selection panel; scores streams worlds from their declared combination | `genesis/sealed.py`; `test_sealed4_*` |
| No leakage: agents never see combinations, seeds or selection scores | `test_observations_never_carry_*` |
| Observer: manifest, preflight, pair counts, missing cases, panel identity and query counts, evidence size | `frontend/src/Milestone5.tsx` |

## Study design (frozen before evaluation)

- **12 evaluation blocks**, each a distinct hidden combination from the 45-member workshop-1 family.
  - All five `split` values are covered. Offset and `flux_threshold` are not balanced: 6 of 12 have flux 4.
  - Each block has its own terrain and controller streams, shared by every condition in that block.
  - There is one controller realisation per combination, so controller and environment variation are partly confounded.
- **Settings:** 8 agents, 3 cohorts × 60 ticks, no overlap, preserved knowledge, 48 search credits, panel cap 12.
- **Final pick in every condition:** the best of the cohort's newest 16 or fewer admitted workflows, scored on the shared selection panel. **Primary endpoint:** its sealed-4 score.
- **Paired rule (descriptive):** at least 75% of expected worlds must be eligible pairs, and one side must be lower in at least 75% of them.

## Primary result: admission policy under preserved knowledge

Expected 12, completed 12, eligible 12 (12 distinct combinations) in every comparison; no world missing. Lower is better.

| Contrast (sealed-4, final pick) | A lower / B lower / ties | Median A−B | Mean A / B | Verdict |
|---|---|---|---|---|
| first-improvement: panels vs fixed | 6 / 5 / 1 | −0.04 | 8.93 / 9.01 | no consistent difference |
| beam: panels vs fixed | 5 / 7 / 0 | +0.33 | 9.51 / 9.54 | no consistent difference |
| fixed: beam vs first-improvement | 4 / 8 / 0 | +0.92 | 9.54 / 9.01 | no consistent difference |
| panels: beam vs first-improvement | 2 / 10 / 0 | +1.01 | 9.51 / 8.93 | **first-improvement lower in 10 of 12** (sign test p = 0.039, descriptive) |

**Cohort-specific admission panels did not change what got frozen in this task family.**

- **Final picks:** neither search policy's picks became consistently better or worse on fresh sealed cases.
- **Panel use:** researchers used a mean of about 5 submissions per panel. The cap of 12 was reached in 1 of 71 (first-improvement) and 4 of 63 (beam) researcher-panels.
- **Generalisation gaps:** a pick's sealed score sits 0.6–1.0 above its development score in every condition. Sealed vs selection-panel gaps are within ±0.12. No condition shows a larger adaptive-overfitting gap.
- **Production:** beam used more energy per alloy under panels than under fixed admission in 10 of 12 worlds (5.79 vs 5.53). first-improvement showed no consistent difference (5.24 vs 5.41).
- **Search policy:** first-improvement again did at least as well as repaired beam. The difference is consistent only under panels.

## Secondary result: allocation leave-one-out (fixed admission, preserved)

This study ran within budget: preflight estimated 50.6 minutes and 87 MB for both studies, against a declared 150 minutes and 120 MB. The beam/fixed control worlds are shared with the primary study (12 of 12, identical frozen configuration) and were not re-run.

| Contrast (sealed-4, final pick) | A lower / B lower / ties | Mean A / B | Verdict |
|---|---|---|---|
| bundle vs plain beam | 7 / 4 / 1 | 9.22 / 9.54 | no consistent difference |
| bundle without stale-frontier guard vs bundle | 2 / 2 / 8 | 9.02 / 9.22 | no consistent difference |
| bundle without reserve guard vs bundle | 0 / 0 / **12** | 9.22 / 9.22 | identical picks in every world |
| bundle without novelty guard vs bundle | 4 / 7 / 1 | 9.51 / 9.22 | no consistent difference |

**M5b's finding that the bundle was harmful did not reproduce here.** M5b had 4 distinct worlds and selected by admission score; M5c has 12 distinct worlds and uses the shared selection panel. Neither study is large, and they disagree.

Each leave-one-out contrast is conditional on the other guards:
- **Reserve guard:** it triggered about 8 times per world but never changed a final pick. It acts near the end of lifetimes, after most picks are settled.
- **Stale-frontier guard:** it withdrew about 29 candidates per world. Removing it left the final pick unchanged in 8 of 12 worlds.
- **Novelty guard:** it changed behaviour most; repeated development decisions were 21 with it and 29 without. Without it, several worlds reproduced plain beam's picks exactly. Its effect on sealed scores was not consistent.

No guard is identified as responsible for anything.

## Costs, performance and evidence size

- **Runtime:** calibration 11.0 minutes (24 worlds); primary 21.9 minutes (48 worlds); ablation 21.4 minutes (48 new worlds plus 12 shared). Selection-panel accounting: 4,728 case evaluations across the 48 primary worlds, never truncated.
- **Achieved server speed** (target 10 ticks/s, durability unchanged):

  | Base agents | Overlap peak active | Ticks/s | Max lag |
  |---|---|---|---|
  | 8 | — | 9.8 | — |
  | 8 | 16 | 7.1 | — |
  | 20 | — | 9.4 | — |
  | 20 | 40 | 4.4 | 1.1 s |

  M5b measured 3.0–9.9 on the same hardware under varying load; treat these as machine-dependent.
- **Evidence size:** 86.5 MB. M5b added 131 MB. Calibration stores no exports; reducer outputs are compressed; the shared control is not duplicated. Exports remain the main cost (about 0.44 MB per world); a storage policy proposal is in the roadmap.

## Limitations and uncertainty

- **Coverage:** 12 of 45 combinations of one finite task family, unbalanced on `flux_threshold`. No open-world generalisation.
- **Confounding:** one controller realisation per combination.
- **Independence:** agents, artifacts and transitions within a world are not replicates.
- **Scope of the panel result:** it holds under preserved knowledge with these settings only. No reset conditions were run.
- **Selection panel:** it is selection-used and fixed across all studies; its own adaptivity across future milestones should be watched.
- **LLM controller:** not implemented. See the [M6 handoff](M6_HANDOFF.md).
