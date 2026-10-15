"""Post-hoc corrections to the v0.5.0 summaries, computed from the UNCHANGED v0.5.0 raw evidence.

Usage: python tools/corrections_v05.py OUT_DIR
Writes, without touching evidence/v0.5.0:
- counters.json: genesis-metrics-1 counters recomputed from every v0.5.0 export, beside the differently scoped counters
  the v0.5.0 summary and narrative reported, with each difference classified as intentional scope or defect;
- paired.json: every v0.5.0 paired comparison re-reported with expected/eligible/missing/denominator;
- further_improvement.json: the frozen v0.5 metric beside a creation-attributed version (post-hoc);
- CORRECTIONS.md: the readable summary.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from genesis.reducer import dictionary_metrics
from tools.summarize_m5b import markdown_table, paired

ROOT = Path(__file__).resolve().parent.parent
V05 = ROOT / "evidence" / "v0.5.0"
SEEDS = [201, 202, 203, 204, 205]


def load_worlds(folder: str):
    report = json.loads((V05 / folder / f"{folder}.json").read_text(encoding="utf-8"))
    sealed = json.loads((V05 / folder / "sealed-results.json").read_text(encoding="utf-8"))
    sealed_by = {(w["seed"], w["condition"]): w for w in sealed["worlds"] if w.get("status") == "scored"}
    for item in report["worlds"]:
        export = json.loads(gzip.decompress((V05 / folder / item["export"]["file"]).read_bytes()))
        yield item, export, sealed_by.get((item["seed"], item["condition"]))


def counters() -> dict:
    out = {}
    diag = json.loads((V05 / "diagnosis" / "search-diagnosis.json").read_text(encoding="utf-8"))
    for folder in ("policy", "teaching"):
        agg: dict[str, Counter] = defaultdict(Counter)
        v05_summary: dict[str, Counter] = defaultdict(Counter)
        for item, export, _ in load_worlds(folder):
            m = dictionary_metrics(export)
            c = item["condition"]
            for k, v in m.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    agg[c][k] += v
            s = item["summary"]
            v05_summary[c]["duplicate_behaviour_dev_results (v0.5 summary)"] += s["search"]["duplicate_behaviour_dev_results"]
            v05_summary[c]["cross_generation.admitted_revisions (v0.5 summary)"] += s["cross_generation"]["admitted_revisions"]
        for c in agg:
            d = diag[folder][c]
            alloc = d["allocation"]
            out[f"{folder}:{c}"] = {
                "genesis-metrics-1": dict(agg[c]),
                "v0.5 reported": {**dict(v05_summary[c]),
                                  "repeated evaluation results (v0.5 diagnosis)": d["repeated_evaluation_results"],
                                  "'untested proposals' (v0.5 narrative: proposals - own-candidate tests)": alloc["propose"] - alloc["own-candidate test"]},
                "classification": {
                    "duplicate_behaviour_dev_results vs search.repeated_decisions_world": "intentional scope difference: v0.5 counted own-candidate AND component tests at world scope; the dictionary counter excludes component tests",
                    "repeated evaluation results vs search.repeated_decisions_own": "intentional scope difference: the v0.5 diagnosis compared against every behaviour the agent had observed (own, held re-tests and component tests); the dictionary counter compares own-candidate tests only",
                    "'untested proposals' vs search.untested_proposals": "DEFECT in the v0.5 narrative: proposals minus own-candidate tests also subtracted nothing for component proposals, which are tested by component tests; the correct count is search.untested_proposals",
                    "cross_generation.admitted_revisions vs lineage.improvements_on_earlier_cohort_parent": "intentional: v0.5 counted admitted revisions with an earlier-cohort immediate parent including refactors; the dictionary counter excludes refactors",
                    "inherited-reference admissions (v0.5 post-hoc) vs lineage.improvements_on_earlier_cohort_reference": "same definition (admission reference created by an earlier cohort); both exclude refactors"}}
    return out


def paired_reports() -> dict:
    summary = json.loads((V05 / "summary.json").read_text(encoding="utf-8"))
    out = {}
    for exp, pairs in (("P", [("beam/preserved", "first-improvement/preserved"), ("beam/reset", "first-improvement/reset"),
                              ("beam/preserved", "beam-nocomponents/preserved"), ("first-improvement/preserved", "first-improvement/reset"),
                              ("beam/preserved", "beam/reset")]),
                       ("T", [("teaching-only", "none"), ("library", "none"), ("library", "teaching-only")])):
        rows = summary[exp]["rows"]

        def reason(r: dict, key: str = "") -> str:
            return "the final cohort created no admitted workflow (nothing frozen for it)"
        comps = []
        for a, b in pairs:
            for key in ("final_held_best_validation", "final_held_best_sealed", "final_cohort_best_validation", "final_cohort_best_sealed"):
                comps.append(paired(rows, a, b, key, SEEDS, missing_reason=reason))
        out[exp] = comps
    return out


def further_improvement() -> list:
    rows = []
    for folder in ("policy", "teaching"):
        for item, export, sealed in load_worlds(folder):
            state = export["state"]
            arts = [a for a in state["artifacts"].values() if a.get("task") == "workshop-1" and a.get("kind") == "workflow"]
            freezes = state["lifecycle"]["freezes"]
            ct = state["config"]["cohort_ticks"]
            for k in range(1, state["config"]["cohort_count"]):
                boundary = k * ct
                earlier = [a for a in arts if a.get("cohort", 0) < k and a["created_tick"] <= boundary and a["status"] in ("admitted", "superseded")
                           and (a.get("validation") or {}).get("score") is not None]
                ref = min(earlier, key=lambda a: (a["validation"]["score"], a["created_tick"], a["id"])) if earlier else None
                own = next((f["cohort_best"] for f in freezes if f["cohort"] == k and f.get("cohort_best")), None)
                frozen = next((x for x in item["summary"]["further_improvement"] if x["cohort"] == k), {})
                rows.append({"experiment": folder, "seed": item["seed"], "condition": item["condition"], "cohort": k,
                             "frozen_v05_metric": frozen.get("improved_beyond_previous_held"),
                             "creation_attributed_reference": ref and {"artifact": ref["id"][:12], "cohort": ref.get("cohort", 0), "validation": ref["validation"]["score"]},
                             "own_cohort_best": own and own["selection_score"],
                             "improved_creation_attributed": bool(own and ref and own["selection_score"] < ref["validation"]["score"]),
                             "status": "no admitted workflow by this cohort" if own is None else "compared"})
    return rows


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    c = counters()
    (out / "counters.json").write_text(json.dumps(c, indent=2), encoding="utf-8")
    p = paired_reports()
    (out / "paired.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
    f = further_improvement()
    (out / "further_improvement.json").write_text(json.dumps(f, indent=2), encoding="utf-8")
    md = ["# Corrections to v0.5.0 summaries (post-hoc; raw evidence unchanged)", "",
          "Generated by `tools/corrections_v05.py` from `evidence/v0.5.0` exports, which are not modified. These are labelled corrections and post-hoc analyses, not new experimental results.", "",
          "## Counters with different scopes", ""]
    md += ["| experiment:condition | v0.5 'untested proposals' (narrative) | untested_proposals (dictionary) | v0.5 repeated results (diagnosis) | repeated_decisions_own | v0.5 duplicate_behaviour (summary) | repeated_decisions_world | v0.5 cross-gen admitted (summary) | improvements_on_earlier_cohort_parent | improvements_on_earlier_cohort_reference |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for name, v in c.items():
        g, r = v["genesis-metrics-1"], v["v0.5 reported"]
        md.append(f"| {name} | {r[next(k for k in r if k.startswith(chr(39)))]} | {g.get('search.untested_proposals')} | {r['repeated evaluation results (v0.5 diagnosis)']} | {g.get('search.repeated_decisions_own')} | "
                  f"{r['duplicate_behaviour_dev_results (v0.5 summary)']} | {g.get('search.repeated_decisions_world')} | {r['cross_generation.admitted_revisions (v0.5 summary)']} | "
                  f"{g.get('lineage.improvements_on_earlier_cohort_parent')} | {g.get('lineage.improvements_on_earlier_cohort_reference')} |")
    md += ["", "Classification of each difference is in `counters.json` (`classification`). The only defect is the narrative's 'untested proposals' arithmetic.", "",
           "## Paired comparisons with denominators", ""]
    for exp, comps in p.items():
        md += [f"### {exp}", ""] + markdown_table(comps) + [""]
    trans = Counter((r["experiment"], r["condition"], r["improved_creation_attributed"]) for r in f)
    frozen = Counter((r["experiment"], r["condition"], r["frozen_v05_metric"]) for r in f)
    md += ["## Further improvement: frozen v0.5 metric vs creation-attributed (post-hoc)", "",
           "| experiment | condition | transitions | improved (frozen v0.5 metric) | improved (creation-attributed) |", "|---|---|---|---|---|"]
    for exp, cond in sorted({(r["experiment"], r["condition"]) for r in f}):
        n = sum(1 for r in f if r["experiment"] == exp and r["condition"] == cond)
        md.append(f"| {exp} | {cond} | {n} | {frozen[(exp, cond, True)]} | {trans[(exp, cond, True)]} |")
    (out / "CORRECTIONS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:40]))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
