# Superseded evidence: GENESIS v0.2.0

| Field | Value |
|---|---|
| Engine / rules / evaluator | `0.2.0` / `phase-world-2` / `phase-evaluator-2` |
| Generated | 2026-10-14, commit `6145295` (baseline) |
| Contents | `comparison/`: 21 exports from protocol `paired-phase-2` plus `comparison.json`; `offline-demo.json`; `benchmark.json` |
| Superseded by | `evidence/v0.3.0/` |

## Why it is superseded

The audit in [docs/audit/AUDIT-v0.2.0.md](../../../docs/audit/AUDIT-v0.2.0.md) found two problems:

- **Controller inputs breached the stated boundary.** The world seed could be recovered from `controller_seed`, and per-case held-out failures reached agent memories.
- **Some claims built on this evidence were wrong.** It was said that every world reached 512 alloy (true for only 9 of 21) and that the retirement comparison was fair (the retirees' roles and labour differed).

## Status of the files

The files are preserved unchanged. All 21 hash chains verified when re-imported with the v0.2.0 code (commit `6145295`). The v0.3.0 engine refuses to import exports written by other versions. Runs from older versions that already sit in a database stay readable and replayable there, but they cannot be continued.
