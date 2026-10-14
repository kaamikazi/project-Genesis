# Five-minute walkthrough

Start the server with `python -m genesis.cli serve` and open <http://127.0.0.1:8000>.

## 1. Watch actual actions (Observatory)

Press ▶. Inhabitants move on the atlas, and the tick counter advances, driven by the server clock and not by your browser. Click any inhabitant on the map, or use the inspector's name picker.

**Latest action** shows the committed outcome. Click it to see the raw event JSON, and for a rejection the exact rule that refused it (for example `insufficient energy`).

## 2. See an invention earn its place (Invention lab)

After about 10–30 ticks, the researchers (Ada in Hearth, Eno in Haven) have proposed and tested candidates.

- **Rejected** cards say why, for example `phase 5: 6 energy is worse than baseline 2`.
- Open a **verified** card. You'll see the immutable program, the evaluator's totals against the fixed-mode baseline, and all 12 cases with training and held-out phases kept apart.
- Further down is the **lineage**: each revision has to beat its parent, and superseded ancestors remain on record.

## 3. Trace knowledge moving (same dialog)

**Transmission & independent use** lists each recipient, such as *Eno → settlement library → Tao*. It shows the tick they learned the procedure and the tick their own production first reproduced the saving (2 vs 6 energy). An adoption is never counted without both.

## 4. Remove the inventors

Click **＋ New world**, choose *Retire procedure creators* at tick 40, and press ▶. At tick 40 the banner reports who retired and counts the procedure uses since. The **Inhabitants** page shows the creators as `retired`.

Repeat with *Retire matched non-creators (control)* and with sharing switched off to compare.

## 5. Compare conditions (Experiments)

This page reads `evidence/comparison/comparison.json`, which contains:

- energy per alloy, sharing vs restricted, for each seed
- energy after removal, creators vs matched, with and without sharing
- every attempt, including failures

Regenerate the report with `python -m genesis.cli compare`.

## 6. Pause, checkpoint, restart, replay (Archive)

1. Pause, then press ◫ to save a checkpoint.
2. Stop the server (Ctrl+C) and start it again. The same world comes back at the same tick.
3. In **Archive**, choose a tick and click **Inspect**. This replays recorded transitions read-only and never calls a controller.
4. Click **Fork displayed state** to branch a new run with recorded parent lineage.
5. Click **Export complete run** to download the manifest, every tick record, snapshots and a checksum.

## 7. What is designed, scripted, searched or model-controlled?

| Behaviour | Source |
|---|---|
| Survival, gathering and production | deterministic rules |
| Trades and gifts | scripted on a fixed tick schedule |
| Candidate programs and revisions | bounded search |
| Model-controlled behaviour | none; there are no model calls (shown in the sidebar and footer) |

Open **Field notes & rules** in the sidebar for the full rules.
