# Evidence v0.6.2 (live Gemini smoke runs)

Two bounded live runs on 2026-10-17 against `gemini-3.5-flash-lite` (Gemini Developer API, `generateContent` v1beta) on the owner's project. Before each run the owner confirmed in chat that the project is on the free tier with billing disabled, the model is available and the quota suffices, and authorized the run.

**Publication follows the owner's choice: summary and hashes only.** These files contain counts, statuses, finish reasons, chosen action kinds and parameter *names*, parse-error classes, token usage, latency, reconciliation and re-execution results, and SHA-256 hashes of each exact prompt and response. They contain no prompt text, model response text, explanations, parameter values, keys or headers. The full transcripts stay in the owner's local, git-ignored `data/gemini-smoke-1.sqlite` and `data/gemini-smoke-2.sqlite`.

| File | Run |
|---|---|
| `live-smoke-1-wire1.json` | Run 1: engine 0.6.1, wire schema 1, profile `dd272d6b…`. 10 requests, all `STOP`. Every parameterised action came back with empty `params`, a schema defect fixed in v0.6.2. |
| `live-smoke-2-wire2.json` | Run 2: engine 0.6.2 (runtime commit `e81c873`), wire schema 2, profile `94f396ee…`. 8 requests, all parsed on the first attempt; 8 accepted and 4 engine-rejected model actions; 0 fallbacks. |

Both runs: one model-backed inhabitant (a01), seed 101, `workshop-1`, 40 ticks; at most 10 requests, 200,000 input and 10,240 generated tokens, 20 s per request, 15 s pacing, 900 s deadline. There were no quota events, no reservation overshoots and no uncertain outcomes. Ledger and world metrics reconcile, and decision re-execution matched every model decision without network access.

Forty ticks are an engineering test, not evidence of intelligent behaviour.

Regenerate a summary from a local run database with:

```
python tools/summarize_live_smoke.py data/gemini-smoke-2.sqlite OUT.json --label "..."
```
