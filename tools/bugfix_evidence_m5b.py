"""Before/after evidence for the three defects repaired in v0.5.1, on minimal reproductions.

Usage: python tools/bugfix_evidence_m5b.py OUT.json
Runs the same probe against tag v0.5.0 (temporary git worktree) and against the current checkout. The probe uses
only APIs present in both versions. Each scenario reports the actions the controller chose for 10 ticks and how many
were rejected.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROBE = r'''
import json, sys
from copy import deepcopy
from genesis.controllers import OfflineController
from genesis.engine import attempt
from genesis.models import Action, Scenario
from genesis.world import LocalObservations, new_world
import genesis
WF = {"op": "workflow", "batch": {"op": "if_lt", "measure": "ore", "threshold": 6, "then": {"op": "const", "value": 1}, "else": {"op": "const", "value": 2}},
      "heat": {"op": "if_lt", "measure": "humidity", "threshold": 3, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "mode": {"op": "if_lt", "measure": "phase", "threshold": 6, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}},
      "flux": {"op": "if_lt", "measure": "humidity", "threshold": 5, "then": {"op": "const", "value": 0}, "else": {"op": "const", "value": 1}}}

def ok(s, kind, agent, **p):
    after, out = attempt(s, Action(id=f"p-{s['tick']}-{agent}-{kind}-{len(s['artifacts'])}", agent=agent, tick=s["tick"], kind=kind, params=p))
    assert out["accepted"], out
    after = deepcopy(after); after["tick"] += 1
    return after, out["result"]

def stale(policy):
    s = new_world(Scenario(seed=101, task="workshop-1", ore_per_site=900, budget_unit="credits", search_budget=48, search_policy=policy, max_ticks=300))
    s, r = ok(s, "propose_artifact", "a00", program=WF, parent=None); ref = r["artifact"]
    s, _ = ok(s, "test_artifact", "a00", artifact=ref)
    s["artifacts"][ref]["status"] = "admitted"; s["agents"]["a00"]["known"].append(ref)
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "flux": {"op": "const", "value": 0}}, parent=ref); pending = r["artifact"]
    s, _ = ok(s, "test_artifact", "a00", artifact=pending)
    s["artifacts"][pending]["development"]["score"] = 1.0
    s["artifacts"][pending]["created_tick"] = s["tick"]
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "flux": {"op": "const", "value": 1}}, parent=ref); head = r["artifact"]
    s["artifacts"][head].update(status="admitted", creator="a01"); s["artifacts"][ref].update(status="superseded", superseded_by=head)
    return s

def drive(s, agent, ticks=10):
    c = OfflineController(s["config"]["controller_seed"]); rows = []
    for _ in range(ticks):
        a = c.propose(LocalObservations().build(s, agent))
        nxt, out = attempt(s, a)
        rows.append({"kind": a.kind, "accepted": out["accepted"], "reason": (out.get("reason") or "")[:70]})
        s = deepcopy(nxt); s["tick"] += 1
    return {"actions": rows, "rejected": sum(not r["accepted"] for r in rows)}

def library():
    s = new_world(Scenario(seed=101, task="workshop-1", ore_per_site=900, max_ticks=300))
    comp = {"op": "component", "field": "heat", "expr": WF["heat"]}
    s, r = ok(s, "propose_artifact", "a00", program=comp, parent=None); cid = r["artifact"]
    s["artifacts"][cid]["status"] = "admitted"; s["agents"]["a00"]["known"].append(cid)
    s, r = ok(s, "propose_artifact", "a00", program={**WF, "heat": {"op": "call", "artifact": cid}}, parent=None); wid = r["artifact"]
    s["artifacts"][wid]["status"] = "admitted"; s["agents"]["a00"]["known"].append(wid)
    s["agents"]["a01"].update(x=s["settlements"]["hearth"]["x"], y=s["settlements"]["hearth"]["y"], energy=40)
    s["agents"]["a01"]["inventory"]["ore"] += 30; s["initial_totals"]["ore"] += 30
    s, r = ok(s, "inspect_artifact", "a01", artifact=wid)
    rows = []
    for _ in range(5):
        a = Action(id=f"use-{s['tick']}", agent="a01", tick=s["tick"], kind="use_artifact", params={"artifact": wid})
        nxt, out = attempt(s, a)
        rows.append({"accepted": out["accepted"], "reason": (out.get("reason") or "")[:70]})
        s = deepcopy(nxt); s["tick"] += 1; s["agents"]["a01"]["busy_until"] = 0; s["agents"]["a01"]["energy"] = 40
    return {"component_copied_with_workflow": cid in s["agents"]["a01"]["known"], "uses": rows, "rejected": sum(not r["accepted"] for r in rows)}

print(json.dumps({"engine": genesis.ENGINE_VERSION,
                  "stale_submission_beam": drive(stale("beam"), "a00"),
                  "stale_parent_first_improvement": drive(stale("first-improvement"), "a00"),
                  "library_copy_without_dependency": library()}))
'''


def run_probe(tree: Path) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(PROBE)
        script = f.name
    try:
        proc = subprocess.run([sys.executable, script], cwd=tree, env={**os.environ, "PYTHONPATH": str(tree)}, capture_output=True, text=True)
        if proc.returncode:
            return {"error": proc.stderr[-1500:]}
        return json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(script)


def main(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old = Path(tmp) / "v050"
        subprocess.run(["git", "worktree", "add", "--detach", str(old), "v0.5.0"], cwd=ROOT, check=True, capture_output=True)
        try:
            before = run_probe(old)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=ROOT, capture_output=True)
    after = run_probe(ROOT)
    result = {"before_v0.5.0": before, "after_current": after,
              "summary": {k: {"rejected_before": (before.get(k) or {}).get("rejected"), "rejected_after": (after.get(k) or {}).get("rejected")}
                          for k in ("stale_submission_beam", "stale_parent_first_improvement", "library_copy_without_dependency")}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
