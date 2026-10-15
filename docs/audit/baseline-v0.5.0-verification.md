# Baseline before M5b (v0.5.0)

Checked 2026-10-16 on `main` at `7ad0d69` (tag `v0.5.0`, runtime commit `3f7b0eb`), synchronised with `origin/main`.

| Check | Result |
|---|---|
| `python -m pytest -q` | 125 passed |
| `npm run build` | succeeded |

## Reproductions made before any repair

The minimal cases below ran against the unmodified v0.5.0 code. They are kept as `tools/bugfix_evidence_m5b.py`, which re-runs them against tag `v0.5.0` in a temporary worktree and against the current code.

1. **Stale-reference resubmission (beam).** A researcher holds a development-tested candidate. Another agent's admission supersedes that candidate's reference. The v0.5.0 beam policy then re-submitted the candidate on every tick, and every submission was rejected ("the nearest admitted ancestor is no longer current"): 6 of 6 ticks, and 10 of 10 in the stored probe.
2. **Stale parent (first-improvement).** In the same situation, the v0.5.0 reference policy chose the superseded workflow as its parent and proposed revisions of it, rejected on every tick (10 of 10).
3. **Dependency-blind library copy.** Copying a component-calling workflow from the library did not copy its component. Every later execution was rejected for a missing prerequisite (5 of 5). In the v0.5.0 evidence this produced 1,390 rejected `use_artifact` attempts in beam/preserved, and 356 to 903 in the other component-using conditions; beam-nocomponents had none.

## Counting error found in the v0.5.0 narrative

"45 untested proposals" (beam/preserved) was proposals minus own-candidate tests. It did not account for component proposals, which are tested by component tests. The correct count from events is 7, all within 5 ticks of the proposer's retirement. The corrected counters are in `evidence/v0.5.1/corrections-v0.5.0/`; the v0.5.0 evidence is unchanged.
