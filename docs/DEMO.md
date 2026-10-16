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

## 3c. Watch search, components and a generational handoff (v0.5)

1. Click **＋ New world** and choose **workshop-1**.
2. Tick **Enable teaching sessions**, **Scheduled cohorts (3 × 60 ticks)** and **v0.5 search and mentorship**. The last option turns on beam search with components, 48 shared search credits, dependency-aware lessons and a 30-tick overlap.
3. Untick **Allow verified procedure sharing** if you want lessons to be the only route between generations. Then press ▶.

What you'll see:

- **Search.** For each researcher: credits spent out of 48, own attempts by status, and the frontier of best development scores. Below that are the latest attempts (operator, parent, restarts) and the reasons searching stopped in the last 40 ticks (budget, energy, no candidate).
- **Components.** This panel appears once a component exists. It shows components (extractions vs revisions, with dashed arcs from a revision to its parent) and the workflows that call them, including refactor admissions. A call names a hash, so a revision never changes the workflows that call the old version.
- **Generations.** A timeline of overlapping cohorts with arrival and retirement transitions; cross-generation lessons with their dependency closure, what was taught in the package, what the learner already knew, and the outcome; and knowledge paths across cohorts.
- **Frozen workflows.** Each freeze's created, accessible and held best, with validation and development scores and the closure by hash.

The same chain, scripted and labelled as a demonstration, can be reproduced exactly:

```
python -c "from genesis.demo5 import component_chain, summary; print(summary(component_chain(101)))"
```

It extracts a component, admits it inside its host, refactors the workflow to call it, teaches the workflow and its dependency to the successor during the overlap, retires the teacher on schedule, executes the inherited workflow, admits a revision, and rewires the workflow to it. Its actions are submitted overrides checked by the ordinary rules. It is not experimental evidence.

## 3d. Watch the v0.5.1 repairs and mentorship

Create a **workshop-1** world with cohorts, teaching and **v0.5 search and mentorship** ticked, as in 3c.

- **Search panel.** Attempts now show `withdraw-stale` when a candidate's reference was replaced by someone else's newer workflow. v0.5.0 resubmitted such candidates forever. Under `beam-alloc` (API scenario field `search_policy`), the panel also shows `reserve` stops and how many candidates the exact-novelty rule skipped.
- **Transport bar.** It shows the target and the achieved ticks per second. The selected speed is a target; with 40 active agents during an overlap, the engine achieves fewer.
- **Teaching (`teaching_policy: package-scheduled`).** Juniors keep asking seniors for lessons, and seniors don't start lessons they can't finish before retiring. Dependency lessons appear in the Generations panel with their package.

## 3e. Watch a model-controller pipeline with a fixture (v0.6)

Tick **Fixture model inhabitant (a01)** when creating a world. a01's decisions then go through the full model path: scheduler, budget reservation, durable ledger, prompt from the restricted observation, response, strict parsing, engine validation. The responses come from a scripted fixture policy, **not a model**.

- **Model panel.** For each model agent: the latest decision mode (*model proposal*, *model intent execution*, *offline policy*, *fallback*), the scheduler's reason, the action and whether the engine accepted it, and the ledger receipt.
- **Budgets.** Committed, pending, uncertain and historical usage, and what remains. Cost reads "unpriced": no price exists for a fixture.
- **Requests.** Every ledger row with its status, usage basis and parse result. *Inspect* shows the sanitized prompt and the response that was used.
- **Pause model scheduling** stops new requests; a01 continues under its offline policy, labelled as such.
- Provider latency is wall-clock time, shown separately from simulation speed.

## 4. The controlled experiment (Experiments)

This page reads `evidence/v0.5.1/` for M5b (repairs, corrected comparisons, allocation and mentorship experiments, achieved speed; `python tools/generate_evidence_m5b.py`), `evidence/v0.5.0/` for Milestone 5 (Experiments P and T, sealed-2 results, the demonstration, search CPU and restart checks; regenerate with `python tools/generate_evidence_m5.py`), `evidence/v0.4.0/` for Milestone 4 (Experiments A and B, sealed results) and `evidence/v0.3.0/` for the historical Milestone 3 reports. Regenerate with `python tools/generate_evidence_m4.py` (v0.4) or `python tools/generate_evidence.py` (v0.3).

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
| Candidate programs and revisions | Bounded search: first-improvement (v0.4 reference) or beam (v0.5) |
| Component chain in `genesis/demo5.py` | Scripted demonstration (labelled), validated by the ordinary rules |
| Retirement and succession | Scheduled by the scenario |
| Model-backed inhabitants (v0.6) | Implemented; demonstrated only with scripted fixtures and mocked transport. No live model has controlled any inhabitant. |
