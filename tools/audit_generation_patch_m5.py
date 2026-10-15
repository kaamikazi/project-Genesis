"""Audit: did the mid-pipeline edit to genesis/storage.py and genesis/api.py change any v0.5.0 experiment world?

Usage: python tools/audit_generation_patch_m5.py CLEAN_CHECKOUT EVIDENCE_DIR OUT.json
CLEAN_CHECKOUT is a worktree at the runtime commit recorded in runs.json (before the edit). Every completed world in
policy/ and teaching/ is re-run there from its stored configuration; the initial hash, every tick-record hash and the
final state digest are compared with the stored export. Run this with CLEAN_CHECKOUT first on sys.path.
"""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main(clean: Path, evidence: Path, out: Path) -> None:
    sys.path.insert(0, str(clean))
    import genesis  # noqa: F401  (must resolve to the clean checkout)
    from genesis.models import Scenario, digest
    from genesis.storage import Store
    assert Path(genesis.__file__).resolve().is_relative_to(clean.resolve()), genesis.__file__
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=clean, capture_output=True, text=True).stdout.strip()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "audit.sqlite")
        for folder, name in (("policy", "policy"), ("teaching", "teaching")):
            report = json.loads((evidence / folder / f"{name}.json").read_text(encoding="utf-8"))
            for item in report["worlds"]:
                if item["status"] != "completed":
                    rows.append({"experiment": name, "seed": item["seed"], "condition": item["condition"], "status": item["status"], "compared": False})
                    continue
                stored = json.loads(gzip.decompress((evidence / folder / item["export"]["file"]).read_bytes()))
                start = time.perf_counter()
                rid = store.create(Scenario.model_validate(item["config"]))
                for _ in range(item["config"]["max_ticks"]):
                    store.step(rid)
                fresh = store.export(rid)
                rows.append({"experiment": name, "seed": item["seed"], "condition": item["condition"],
                             "initial_hash_equal": fresh["manifest"]["initial_hash"] == stored["manifest"]["initial_hash"],
                             "record_hashes_equal": [t["record_hash"] for t in fresh["ticks"]] == [t["record_hash"] for t in stored["ticks"]],
                             "final_state_equal": digest(fresh["state"]) == digest(stored["state"]),
                             "ticks": len(fresh["ticks"]), "seconds": round(time.perf_counter() - start, 1)})
                print(rows[-1], flush=True)
    compared = [r for r in rows if r.get("compared", True)]
    identical = all(r["initial_hash_equal"] and r["record_hashes_equal"] and r["final_state_equal"] for r in compared)
    result = {"clean_checkout_commit": commit, "worlds_compared": len(compared), "all_identical": identical, "rows": rows,
              "conclusion": "the edit did not change any experiment world" if identical else "AT LEAST ONE WORLD DIFFERS: regenerate affected evidence"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["conclusion"])
    if not identical:
        sys.exit(1)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
