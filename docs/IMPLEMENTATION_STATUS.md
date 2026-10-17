# Implementation status, v0.6.2 / M6b smoke (2026-10-17)

Engine `0.6.2` · rules `phase-world-5.2` (unchanged) · prompt `genesis-prompt-1` · action schema `genesis-action-schema-1` · parser `genesis-parser-1` · adapters `ollama-chat-1`, `gemini-generatecontent-1` · Gemini wire schema `genesis-gemini-wire-2`.

- **Evidence:** [`evidence/v0.6.2/`](../evidence/v0.6.2/README.md) (live smoke runs, summary and hashes only), [`evidence/v0.6.1/`](../evidence/v0.6.1/README.md) (mock verification)
- **Decisions:** [ADR-009](ADR-009-gemini-adapter.md) (Gemini, with the wire-2 addendum), [ADR-008](ADR-008-model-controller-boundary.md)
- **Setup:** [GEMINI_SETUP](GEMINI_SETUP.md), [LIVE_RUN_CHECKLIST](LIVE_RUN_CHECKLIST.md)
- **Previous status:** [v0.6.1](history/IMPLEMENTATION_STATUS-v0.6.1.md), [v0.6.0](history/IMPLEMENTATION_STATUS-v0.6.0.md), [v0.5.2](history/IMPLEMENTATION_STATUS-v0.5.2.md) and earlier in [history](history/)

## Four separate claims

| Claim | Status |
|---|---|
| **Integration implemented** | Yes (v0.6.0 boundary, v0.6.1 Gemini adapter, v0.6.2 wire schema 2) |
| **Mock verified** | Yes: the 44 Gemini tests (38 from v0.6.1 + 6 new) pass, including a constrained-decoding mock that reproduces the live defect offline. The full 248-test suite was about 65% through with no failures when the session stopped; rerun before tagging v0.6.2. |
| **Live transport exercised** | **Yes**, on 2026-10-17: two bounded smoke runs against `gemini-3.5-flash-lite` on the owner's free-tier project, 18 requests in total. Each run was authorized in chat after the owner confirmed the free tier with billing disabled, model availability and quota. |
| **Live agent behaviour demonstrated** | **Only as an engineering smoke test.** One inhabitant over 40 ticks, 8 model deliberations in run 2. This shows the path works with a real model, not that the model plays well. |

## Live smoke runs (seed 101, `workshop-1`, one model-backed inhabitant a01, 40 ticks)

| | Run 1 (engine 0.6.1, wire-1) | Run 2 (engine 0.6.2, wire-2, commit `e81c873`) |
|---|---|---|
| Requests sent | 10 (ceiling reached; 9 later requests blocked) | 8 (no ceiling reached) |
| Finish reasons | 10 × `STOP` | 8 × `STOP` |
| Parsed on first attempt | 1 of 6 primaries (the parameter-free `produce`) | 8 of 8 |
| Repairs | 4 sent, all failed the same way; a 5th blocked by the request ceiling | 0 |
| Decisions of a01 | 1 proposal · 13 fallbacks · 26 offline | 8 proposals · 4 standing-choice executions · 28 offline · 0 fallbacks |
| Engine verdicts on model actions | 1 accepted | 8 accepted, 4 rejected (insufficient ore or energy for a batch) |
| Committed tokens (input / output) | 47,698 / 870 | 39,731 / 398 |
| Thinking tokens | not reported (no `thoughtsTokenCount` at `MINIMAL`) | not reported |
| Median / max latency | 1.56 s / 2.40 s | 1.92 s / 2.50 s |
| Quota events, overshoots, uncertain outcomes | 0 / 0 / 0 | 0 / 0 / 0 |
| Ledger ↔ world-metrics reconciliation | yes | yes |
| Decision re-execution (no network) | 1 of 1 | 12 of 12 |

**What run 1 found.** Wire schema 1 declared `params` as an object without properties. Under constrained decoding Gemini could not emit any parameter key: every `gather`, `use_artifact` and so on came back as `"params": {}`, sometimes after hundreds of whitespace tokens. The strict parser rejected each one, one repair was spent per decision, and the agent fell back to the offline policy. This was a GENESIS defect, not model behaviour.

**What changed.** Wire schema 2 gives each action kind its own `anyOf` branch with typed, required parameters. A constrained mock now reproduces run 1's failure offline (`tests/test_v062.py`), and live dispatch refuses wire-1. `propose_artifact` is excluded from the wire schema because its free-form program cannot be expressed in the documented subset; a01 is not a researcher.

**What run 2 shows.** Every response was valid on the first attempt, including `test_artifact` and `use_artifact` with real artifact ids. Four of twelve model actions were legal in form but failed world preconditions and were rejected by the engine like any other controller's. The model kept choosing a workflow it could not afford at that moment, which is a behavioural observation from 12 actions, not a finding.

## Verification

| Check | Result |
|---|---|
| `python -m pytest -q` | **Not yet complete**: the full run was interrupted at ~65% with no failures; `tests/test_v061.py` and `tests/test_v062.py` (44) passed. Rerun before tagging v0.6.2. |
| `npm run build` | Succeeded |
| Key handling | The key was supplied in chat by the owner and passed only as a process environment variable. It appears in no committed file, run database row, report or evidence file (checked). |
| Publication | Owner's choice: summary and hashes only. Prompts, responses, explanations and parameter values stay in the local, git-ignored `data/` databases; `evidence/v0.6.2/` holds SHA-256 hashes of each prompt and response so they can be verified later. |

## Known limitations

- Two short runs with one inhabitant: no behavioural conclusions.
- Thinking at `MINIMAL` reported no thought tokens in either run, so whether `maxOutputTokens` bounds thinking on `generateContent` remains untested. The overshoot halt stays in place.
- `propose_artifact` cannot be produced under wire-2's constrained decoding.
- The key was pasted into a chat transcript; the owner should delete or regenerate it in AI Studio.
