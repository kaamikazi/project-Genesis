"""Audit of the v0.2.0 claims against raw evidence (run from the repo root with the v0.2.0 code).

Usage: python tools/audit_v0_2.py evidence/superseded/v0.2.0 docs/audit/audit-v0.2.0.json
Reads exports directly; does not call genesis.experiments.metrics.
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from genesis.models import digest, keyed


def load(path: Path) -> dict:
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def accepted(export: dict):
    for entry in export["ticks"]:
        for e in entry["record"]["events"]:
            if e.get("type") == "action_accepted":
                yield e


def main(root: Path, out: Path) -> None:
    comparison = json.loads((root / "comparison" / "comparison.json").read_text(encoding="utf-8"))
    result: dict = {"source": str(root), "worlds": []}
    for attempt in comparison["attempts"]:
        export = load(root / "comparison" / attempt["export"])
        initial, final = export["initial"], export["state"]
        produced = sum(e["result"]["alloy"] for e in accepted(export) if e["kind"] in ("produce", "use_artifact"))
        ore_initial = sum(s["stock"] for s in initial["sites"].values() if s["resource"] == "ore") + sum(a["inventory"]["ore"] for a in initial["agents"].values())
        sites_ore = sum(s["stock"] for s in final["sites"].values() if s["resource"] == "ore")
        active_ore = sum(a["inventory"]["ore"] for a in final["agents"].values() if a["status"] == "active")
        storage_ore = sum(s["inventory"]["ore"] for s in final["settlements"].values())
        removal = final.get("lifecycle", {}).get("removal")
        removal_tick = removal["tick"] if removal else None
        by_agent_before = Counter()
        if removal:
            for e in accepted(export):
                if e["kind"] in ("produce", "use_artifact") and e["tick"] <= removal_tick:
                    by_agent_before[e["agent"]] += 1
        removed = removal["removed"] if removal else []
        roles = {aid: initial["agents"][aid]["role"] for aid in removed}
        result["worlds"].append({
            "seed": attempt["seed"], "condition": attempt["condition"], "reported_produced": attempt["metrics"]["produced"],
            "event_produced": produced, "theoretical_max_alloy": ore_initial // 2, "ore_initial": ore_initial,
            "final_ore_on_sites": sites_ore, "final_ore_active_agents": active_ore,
            "final_ore_in_settlement_storage_without_withdraw_action": storage_ore,
            "removed": removed, "removed_roles": roles,
            "production_actions_before_removal_by_removed": {a: by_agent_before[a] for a in removed},
            "removal_inventory_moved": removal["inventory_moved"] if removal else [],
        })
    # Seed leakage: v0.2.0 observations carried controller_seed = keyed(seed, "controller-stream", agent) % 2**31.
    leak = []
    for seed in (11, 42, 77):
        observed = keyed(seed, "controller-stream", "a00") % 2**31
        recovered = next(s for s in range(0, 200_000) if keyed(s, "controller-stream", "a00") % 2**31 == observed)
        leak.append({"world_seed": seed, "observed_controller_seed": observed, "recovered_seed": recovered, "candidates_tried": recovered + 1})
    result["seed_recovery"] = leak
    # Held-out leakage: test results (including held-out phase-specific failures) entered agent memories.
    demo = load(root / "comparison" / "42-sharing.json.gz")
    heldout = {0, 2, 3, 5, 6, 8, 9, 11}
    leaks = []
    for e in accepted(demo):
        if e["kind"] == "test_artifact":
            for f in e["result"].get("failures", []):
                if f.startswith("phase ") and int(f.split()[1].rstrip(":")) in heldout:
                    leaks.append({"tick": e["tick"], "agent": e["agent"], "failure": f})
    result["held_out_case_feedback_in_agent_memory"] = {"count": len(leaks), "examples": leaks[:5],
                                                         "channel": "test_artifact result -> agent.memories -> observation.memory"}
    # Replay verification: re-import every export (import re-walks the whole hash chain).
    from genesis.storage import Store
    verified = []
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "audit.sqlite")
        for attempt in comparison["attempts"]:
            export = load(root / "comparison" / attempt["export"])
            try:
                rid = store.import_run(export)
                ok = digest(store.load(rid)) == attempt["metrics"]["state_hash"]
                verified.append({"export": attempt["export"], "chain_verified": True, "final_hash_matches_report": ok})
            except Exception as exc:  # noqa: BLE001 - audit records every failure
                verified.append({"export": attempt["export"], "chain_verified": False, "error": str(exc)})
    result["replay_verification"] = verified
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "worlds"}, indent=1)[:3000])
    for w in result["worlds"]:
        print(w["seed"], w["condition"].ljust(27), w["reported_produced"], w["event_produced"], "max", w["theoretical_max_alloy"],
              "storage_ore", w["final_ore_in_settlement_storage_without_withdraw_action"], "sites", w["final_ore_on_sites"],
              "active", w["final_ore_active_agents"], w["removed_roles"], w["production_actions_before_removal_by_removed"])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
