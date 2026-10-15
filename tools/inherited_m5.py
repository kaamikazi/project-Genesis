"""Post-close analysis of inherited-parent improvements in v0.5.0 experiments P and T.

Usage: python tools/inherited_m5.py EVIDENCE_DIR OUT.json

1. Every submission whose admission reference (nearest admitted ancestor) was created by an earlier cohort: was it
   admitted (it beat that inherited reference on the 24 validation cases), and how do the child and its reference
   compare on the sealed-2 cases?
   POST-HOC: the frozen protocol scores only frozen artifacts with sealed-2. These extra sealed scores are a
   diagnostic computed after every run closed; nothing feeds back into any run, and no setting was changed.
2. Further improvement, corrected (POST-HOC): the frozen metric compares cohort k's own best with the best workflow
   cohort k-1's members held at their freeze. With library access during the overlap, seniors can hold workflows
   created by their juniors, so that reference can include cohort k's own work. The corrected reference is the best
   (validation) workflow created by any cohort < k among all earlier freeze picks (created, accessible or held best):
   the best earlier-generation work known to exist, whether or not cohort k could access it.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from genesis.sealed import SealedEvaluator


def main(evidence: Path, out: Path) -> None:
    sealed = SealedEvaluator(evidence / "protected" / "sealed-2-manifest.json")
    result = {"post_hoc": True, "sealed_version": sealed.manifest["version"], "experiments": {}}
    for folder in ("policy", "teaching"):
        report = json.loads((evidence / folder / f"{folder}.json").read_text(encoding="utf-8"))
        rows, further = [], []
        for item in report["worlds"]:
            if item["status"] != "completed":
                continue
            export = json.loads(gzip.decompress((evidence / folder / item["export"]["file"]).read_bytes()))
            state, seed = export["state"], item["seed"]
            arts = state["artifacts"]
            comps = {k: a["content"]["program"] for k, a in arts.items() if a.get("kind") == "component"}
            score = lambda aid: sealed.score(seed, arts[aid]["content"]["program"], comps)["score"]  # noqa: E731
            for entry in export["ticks"]:
                for e in entry["record"]["events"]:
                    if e.get("type") != "action_accepted" or e["kind"] != "submit_artifact":
                        continue
                    r = e["result"]
                    ref, child = r.get("reference"), r["artifact"]
                    if not ref or arts[child].get("kind") != "workflow":
                        continue
                    if arts[ref].get("cohort", 0) >= arts[child].get("cohort", 0):
                        continue
                    val = arts[child].get("validation") or {}
                    rows.append({"seed": seed, "condition": item["condition"], "tick": e["tick"], "child": child[:12], "reference": ref[:12],
                                 "child_cohort": arts[child].get("cohort", 0), "reference_cohort": arts[ref].get("cohort", 0),
                                 "admitted": bool(r.get("admitted")), "admission_path": r.get("admission_path", "improvement" if r.get("admitted") else None),
                                 "child_validation": val.get("score"), "reference_validation": val.get("parent_score"),
                                 "child_sealed": score(child), "reference_sealed": score(ref)})
            # corrected further improvement
            freezes = state["lifecycle"]["freezes"]
            for i, cur in enumerate(freezes[1:], start=1):
                k = cur["cohort"]
                if cur["reason"] != "run closed" and k == freezes[i - 1]["cohort"]:
                    continue
                earlier = [p for f in freezes[:i] for p in (f.get("cohort_best"), f.get("accessible_best"), f.get("held_best")) if p and p["cohort"] < k]
                ref = min(earlier, key=lambda p: (p["selection_score"], p["artifact"])) if earlier else None
                own = cur.get("cohort_best")
                further.append({"seed": seed, "condition": item["condition"], "cohort": k,
                                "reference": ref and {"artifact": ref["artifact"][:12], "cohort": ref["cohort"], "validation": ref["selection_score"], "sealed": score(ref["artifact"])},
                                "own": own and {"artifact": own["artifact"][:12], "validation": own["selection_score"], "sealed": score(own["artifact"])},
                                "improved_on_validation": bool(own and ref and own["selection_score"] < ref["selection_score"]),
                                "improved_on_sealed": bool(own and ref and score(own["artifact"]) < score(ref["artifact"]))})
        admitted = [r for r in rows if r["admitted"] and r["admission_path"] == "improvement"]
        by_cond = {}
        for cond in report["conditions"]:
            a = [r for r in admitted if r["condition"] == cond]
            f = [x for x in further if x["condition"] == cond]
            by_cond[cond] = {"submissions_against_inherited_reference": sum(1 for r in rows if r["condition"] == cond),
                             "admitted_improvements": len(a), "refactor_admissions": sum(1 for r in rows if r["condition"] == cond and r["admission_path"] == "refactor"),
                             "admitted_and_better_on_sealed": sum(1 for r in a if r["child_sealed"] is not None and r["reference_sealed"] is not None and r["child_sealed"] < r["reference_sealed"]),
                             "admitted_but_worse_or_equal_on_sealed": sum(1 for r in a if r["child_sealed"] is not None and r["reference_sealed"] is not None and r["child_sealed"] >= r["reference_sealed"]),
                             "further_improvement_corrected": {"transitions": len(f), "own_best_beat_earlier_cohorts_on_validation": sum(x["improved_on_validation"] for x in f),
                                                               "and_on_sealed": sum(x["improved_on_validation"] and x["improved_on_sealed"] for x in f),
                                                               "on_sealed_only": sum(x["improved_on_sealed"] for x in f)}}
        result["experiments"][folder] = {"by_condition": by_cond, "submissions": rows, "further_improvement_corrected": further}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for folder, v in result["experiments"].items():
        for cond, s in v["by_condition"].items():
            print(folder, cond.ljust(28), s)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
