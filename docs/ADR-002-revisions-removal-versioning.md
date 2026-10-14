# ADR 002: Verified revisions, lifecycle removal and a version boundary

Accepted 2026-10-14. Extends [ADR-001](ADR-001-foundation.md).

## Context

The v0.1 foundation stopped each researcher at its first verified candidate. It had no way to test whether knowledge survives its creator, and it exposed the world seed in observations, which would let a controller recompute every hidden phase. The observatory could not build because its stylesheet was missing.

## Decisions

1. **The observation boundary.** Controllers receive a per-agent `controller_seed` (`keyed(seed, "controller-stream", agent)`), never the world seed. A test guards this.
2. **Revisions.** A revision names a current verified parent. The evaluator re-executes both programs and requires strictly lower total energy, in addition to the original criteria. The parent then becomes `superseded`. The researcher searches a declared neighbourhood (threshold ±1, branch swap) until it reaches a local optimum or exhausts its budget. Rejections list every failed criterion. The evaluator version moves to `phase-evaluator-2`.
3. **Lifecycle removal.** This is a scenario-scheduled event at a documented point in the tick (after fatigue, before replenishment). `creators` retires verified-artifact creators. `matched` retires the same number of non-creators from the same settlements. Inventory moves to settlement storage, so conservation holds and the control accounts for lost labour and goods. It is described as retirement, never as death.
4. **The experiment design.** Seven conditions per seed: sharing, restricted, baseline, and a 2 × 2 of sharing × removal policy. Exports are gzipped.
5. **The version boundary.** The engine moves to `0.2.0` and the rules to `phase-world-2`. Runs written by other versions remain readable, replayable and exportable, but continuation is refused with an explicit message. The server resumes the newest compatible run.
6. **Compact deltas.** List changes that shift a bounded log are stored as `{drop, append}`. Plain-value deltas still decode. Storage schema stays at 1.
7. **The benchmark** separates committed-tick timing, engine-only timing and memory, because `tracemalloc` inflated the timings about threefold.

## Consequences

Runs now show cumulative improvement with traceable lineage, and a measurable retention effect that depends on the transmission path. Both are still products of designed mechanics. Pre-0.2 runs in existing databases are preserved read-only.
