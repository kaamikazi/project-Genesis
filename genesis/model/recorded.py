"""Decision re-execution from recordings (replay mode B).

Three replay modes are kept distinct:
A. State replay (`Store.replay`): applies recorded deltas; no controller, network or provider is involved.
B. Decision re-execution (this module): rebuilds each model decision's observation from replayed state, rebuilds the
   prompt, recomputes the request identity, checks it against the ledger row (observation, prompt, schema and
   configuration hashes, version strings, receipt), re-parses the recorded response with the current parser and
   compares the resulting action with the committed one. No provider is contacted; nothing is charged.
C. New continuation or fork in `recorded` mode (runtime): strict matching on the decision position and hashes; a miss
   stops (or takes the declared fallback); never a "similar" response, never a silent live call.
A parser change that alters any re-parsed action is reported as a mismatch (the parser version is recorded per run).
"""
from __future__ import annotations

from ..models import JSON, digest
from ..world import LocalObservations
from . import ACTION_SCHEMA_VERSION, PARSER_VERSION, PROMPT_VERSION
from . import ledger as model_ledger
from .profile import config_hash
from .prompt import build_messages
from .schema import ParseError, parse_proposal, to_action


def reexecute(store, run_id: str) -> JSON:
    profile = store.model_profile(run_id)
    if profile is None:
        raise ValueError("run has no model profile")
    with store.connection() as db:
        rows = {r["decision_id"]: r for r in model_ledger.rows(db, run_id)}
    cfg_hash = config_hash(profile)
    checked = matched = 0
    mismatches: list[JSON] = []
    by_mode: dict[str, int] = {}
    receipts_seen: set[str] = set()
    export = store.export(run_id)
    for entry in export["ticks"]:
        record = entry["record"]
        model_decisions = [d for d in record["decisions"] if d.get("model")]
        if not model_decisions:
            continue
        state = store.replay(run_id, record["tick"] - 1)
        for d in model_decisions:
            mode, meta = d["controller"], d["model"]
            by_mode[mode] = by_mode.get(mode, 0) + 1
            if mode not in ("model-proposal", "model-intent-execution"):
                for did in meta.get("decision_ids", []):
                    if did not in rows:
                        mismatches.append({"tick": record["tick"], "agent": d["action"]["agent"], "problem": f"missing ledger row {did[:12]}"})
                continue
            checked += 1
            agent = d["action"]["agent"]
            obs = LocalObservations().build(state, agent)
            problems = []
            if digest(obs) != d["observation_hash"]:
                problems.append("observation hash differs from the committed decision")
            if mode == "model-intent-execution":
                origin = rows.get(meta.get("origin"))
                if origin is None or origin["receipt"] != meta.get("receipt"):
                    problems.append("intent origin receipt missing or mismatched")
                elif to_action(origin["parsed"], agent, state["tick"]).model_dump() != d["action"]:
                    problems.append("intent action differs from the origin proposal")
            else:
                error = None
                final = None
                for did in meta.get("decision_ids", []):
                    row = rows.get(did)
                    if row is None:
                        problems.append(f"missing ledger row {did[:12]}")
                        break
                    messages, _ = build_messages(obs, profile.adapter.max_input_bytes, repair_error=error if row["role"] == "repair" else None)
                    identity = model_ledger.decision_identity(run_id, agent, state["tick"], row["role"], row["attempt"], digest(obs),
                                                             PROMPT_VERSION, ACTION_SCHEMA_VERSION, cfg_hash)
                    if model_ledger.decision_id(identity) != did or row["identity"] != identity:
                        problems.append(f"{row['role']} identity does not recompute")
                    if digest(messages) != row["prompt_hash"]:
                        problems.append(f"{row['role']} prompt hash does not recompute")
                    if model_ledger.receipt(row) != row["receipt"]:
                        problems.append(f"{row['role']} receipt does not recompute")
                    if row["status"] != "consumed":
                        problems.append(f"{row['role']} row status is {row['status']}, expected consumed")
                    if (row.get("usage") or {}).get("content_error"):
                        # the provider returned no usable text (blocked, empty, truncated...): nothing to re-parse
                        final, error = None, row["parse_error"]
                        continue
                    try:
                        final = parse_proposal(row["response"], profile.adapter.max_output_bytes)
                        error = None
                    except ParseError as exc:
                        final, error = None, str(exc)[:300]
                    if (error or None) != (row["parse_error"] or None) and row["reexecutable"]:
                        problems.append(f"{row['role']} re-parse disagrees with the recorded parse result")
                if final is None:
                    problems.append("no usable proposal after re-parsing")
                elif to_action(final, agent, state["tick"]).model_dump() != d["action"]:
                    problems.append("re-parsed action differs from the committed action")
                if meta.get("receipt"):
                    receipts_seen.add(meta["receipt"])
            if problems:
                mismatches.append({"tick": record["tick"], "agent": agent, "mode": mode, "problems": problems})
            else:
                matched += 1
    consumed = [r for r in rows.values() if r["status"] == "consumed"]
    return {"mode": "decision re-execution from recordings (no provider contacted)", "run_id": run_id, "parser_version": PARSER_VERSION,
            "prompt_version": PROMPT_VERSION, "schema_version": ACTION_SCHEMA_VERSION, "config_hash": cfg_hash,
            "model_decisions_by_mode": by_mode, "checked": checked, "matched": matched, "mismatches": mismatches[:20],
            "mismatch_count": len(mismatches), "consumed_rows": len(consumed), "all_matched": not mismatches}
