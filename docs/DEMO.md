# Walkthrough

Start the server with `python -m genesis.cli serve` and open <http://127.0.0.1:8000>.

## 1. Watch actual actions (Observatory)

Press ▶. The server's clock drives the world, and your browser only watches. Click an inhabitant on the map, or pick one in the inspector.

**Latest action** shows the committed outcome. Click it to see the raw event, including `energy_charged`, and, for a rejection, the exact rule that refused it.

## 2. See an invention earn its place (Invention lab)

Within about 20 ticks, Ada (Hearth) and Eno (Haven) have tested candidates.

- **Rejected** cards give the evaluator's reason.
- A **verified** card opens the immutable program, all 12 cases (training and held-out), and the lineage, where each revision beat its parent on the same cases.
- The event for a test shows only what the agent itself learned: training totals and partition pass/fail. Held-out case detail stays on the procedure record.

## 3. Watch inheritance: creators leave, successors take over

1. Click **＋ New world**.
2. Choose *Retire procedure creators* at tick 30, tick *Replace retirees with fresh successors*, and keep *Settlement library access*.
3. Press ▶ and select the 10 ticks per second speed.

At tick 30:

- The **lifecycle banner** names the retirees and their successors (for example Oren and Kaia) and shows the post-removal window.
- The **Inhabitants** page shows the retirees last, linked to their successors.
- The inspector says "history archived, not inherited".
- **Settlement storage** shows the retirees' goods arriving (`From retirees`) and members withdrawing them.
- **Why this counts as retention** walks through six links for each successor: creator, retirement, access policy, learning event, own execution, and measured saving against the fixed-mode baseline. Each link shows its event.

Now repeat with *No library access*. The chain stops at the access policy and is marked incomplete, and the successor keeps producing in fixed mode at higher cost.

## 3b. Watch a lesson (v0.4)

1. Click **＋ New world**.
2. Choose **workshop-1**.
3. Retire procedure creators at tick 40, with fresh successors and **No library access**.
4. Tick **Enable teaching sessions**, then press ▶.

What you'll see:

- **The request.** A successor with nothing to use sends `request_lesson`, and a holder offers a lesson.
- **Teaching sessions.** The table shows each stage, both participants' instruction work (3 each), the practice runs, the costs per role, and why any lesson failed. For example, *practice outcome costlier than the baseline*.
- **Evidence trail.** Each learner's trail runs: ancestor created → teaching began → practised → acquisition criterion → independent use → descendant revision → evaluator decision. The first missing or failed step is shown, and steps that cannot apply (invention frozen) are marked n/a.
- **Procedure evidence.** For workshop artifacts, the development role (per-case table), the validation role (an admission bit, labelled adaptive) and a note that sealed scores exist only after a run closes are shown separately.

For cohorts, tick **Scheduled cohorts (3 × 60 ticks)** instead. **Generation history** then lists each freeze, the cohort best and the accessible best by validation score, and the lineage across cohorts.

## 4. The controlled experiment (Experiments)

This page reads `evidence/v0.4.0/` for Milestone 4 (Experiments A and B, sealed results) and `evidence/v0.3.0/` for the historical Milestone 3 reports. Regenerate with `python tools/generate_evidence_m4.py` (v0.4) or `python tools/generate_evidence.py` (v0.3).

- **Inheritance diagnostic.** For each seed, three continuations forked from one checkpoint, with a parity badge showing that the physical state was identical at the boundary. For every successor it shows the library acquisition tick, the first saving, uses, energy per alloy, settlement totals and the ore left. Aggregates show the mean of ratios and the pooled ratio separately.
- **Live continuation.** Successor researchers with invention open: who learned, who re-derived the procedure by search, and the total charged energy per alloy.
- **Twenty-agent replication.** Expand it to see the same protocol at 20 agents.
- **Whole-run comparison.** Descriptive only. Output, efficiency and total cost are separate columns, and unavailable ratios are labelled, never drawn as zero.

## 5. Pause, checkpoint, restart, replay (Archive)

1. Pause, then press ◫ to checkpoint.
2. Stop the server and start it again. The same world returns at the same tick with the same hash (`evidence/v0.3.0/verification/restart.json` records this check).
3. In **Archive**, choose a tick and click **Inspect**. This replays recorded transitions read-only, including retirements, successors and storage.
4. Click **Fork** to create a labelled continuation, or **Export** to download a full, checksummed run.

## 6. Check any number yourself

```bash
python -m genesis.cli reduce evidence/v0.3.0/inheritance/42-successor-library.json.gz
```

The reducer recomputes everything from events and reports whether its reconstruction matches the final state.

## What is designed, scripted, searched or model-controlled?

| Behaviour | Source |
|---|---|
| Survival, gathering, storage use and production | Deterministic rules |
| Trades and gifts | Scripted on a fixed tick schedule |
| Candidate programs and revisions | Bounded search |
| Retirement and succession | Scheduled by the scenario |
| Model-controlled behaviour | None; no model calls are made |
