"""Sanitized public summary of a live smoke run (owner's choice, 2026-10-17: "summary + hashes only").

Usage: python tools/summarize_live_smoke.py DB_PATH OUT_JSON [--label TEXT]

Included: the launcher report (counts, statuses, finish reasons, usage, latency, reconciliation, re-execution) and, per
request, tick, role, status, finish reason, returned model, the action kind and parameter *names* the model chose, the
parse error class, usage and latency, plus SHA-256 hashes of the exact prompt and response so the local transcripts can
be verified later. Excluded: prompt text, response text, explanations, parameter values, keys, headers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genesis.storage import Store  # noqa: E402
from tools.gemini_smoke import report  # noqa: E402


def sha(text: str | None) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def summarize(db: Path, label: str) -> dict:
    store = Store(db)
    run_id = store.list_runs()[0]["id"]
    rep = report(store, run_id, 0.0, None)
    rep.pop("wall_seconds", None)
    launcher = json.loads(db.with_suffix(".report.json").read_text(encoding="utf-8"))
    rep["wall_seconds"] = launcher.get("wall_seconds")
    rep["stopped_early"] = launcher.get("stopped_early")
    with store.connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM model_calls WHERE run_id=? ORDER BY seq", (run_id,))]
    requests = []
    for r in rows:
        usage = json.loads(r["usage"]) if r["usage"] else {}
        rec = json.loads(r["reconciled"]) if r["reconciled"] else {}
        parsed = json.loads(r["parsed"]) if r["parsed"] else None
        requests.append({"tick": r["tick"], "role": r["role"], "status": r["status"], "finish_reason": usage.get("finish_reason"),
                         "returned_model": r["returned_model"], "action_kind": parsed["kind"] if parsed else None,
                         "param_names": sorted(parsed["params"]) if parsed else None,
                         "parse_error": (r["parse_error"] or "")[:120] or None, "blocked_reason": (r["fallback"] or "")[:120] or None,
                         "input_tokens": rec.get("input_tokens"), "output_tokens": rec.get("output_tokens"), "thinking_tokens": rec.get("thinking_tokens"),
                         "usage_basis": (rec.get("basis") or "")[:12] or None, "latency_ms": r["latency_ms"],
                         "prompt_sha256": sha(r["prompt"]), "response_sha256": sha(r["response"]), "receipt": r["receipt"]})
    export = store.export(run_id)
    return {"label": label, "publication": "summary + hashes only (owner's choice); prompts, responses and keys are not included",
            "engine_version_of_run": export["manifest"]["engine_version"] if "engine_version" in export.get("manifest", {}) else None,
            "model_profile_hash": export["manifest"].get("model_profile_hash"), "model_config_hash": export["manifest"].get("model_config_hash"),
            "final_state_hash": export["ticks"][-1]["record"]["state_hash"] if export["ticks"] else None,
            "report": rep, "requests": requests}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("out")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    out = summarize(Path(a.db), a.label)
    blob = json.dumps(out, indent=2)
    for forbidden in ("GEMINI_API_KEY=", "x-goog-api-key:"):
        assert forbidden not in blob
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(blob, encoding="utf-8")
    print(f"wrote {a.out} ({len(blob)} bytes)")


if __name__ == "__main__":
    main()
