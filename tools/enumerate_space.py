"""Exhaustive evaluation of the controller's original-candidate grammar and every threshold program,
plus the lower bound that makes 24 energy optimal for this evaluation set.

Usage: python tools/enumerate_space.py evidence/v0.3.0/invention/search-space.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from genesis.invention import HELD_OUT, TRAIN, PhaseEvaluator, conversion


def main(out: Path) -> None:
    evaluator = PhaseEvaluator()
    rows = []
    # Every single-threshold program in the language (threshold 0..12, both orientations) plus both constants.
    programs = [({"op": "mode", "value": m}, f"constant mode {m}") for m in (0, 1)]
    programs += [({"op": "if_phase_lt", "threshold": t, "then": {"op": "mode", "value": d}, "else": {"op": "mode", "value": 1 - d}},
                  f"threshold {t}, then {d}") for t in range(13) for d in (0, 1)]
    for program, label in programs:
        e = evaluator.evaluate(program)
        rows.append({"program": label, "in_controller_grammar": program.get("threshold", -1) in range(2, 10),
                     "energy": e["energy"], "training_energy": e["training_energy"], "status": e["status"], "failures": e["failures"]})
    cases = len(TRAIN) + len(HELD_OUT)
    per_case_minimum = min(conversion(phase, mode)["energy"] for phase in range(12) for mode in (0, 1))
    report = {
        "evaluation_cases": {"training": list(TRAIN), "held_out": list(HELD_OUT)},
        "lower_bound": {"per_case_minimum_energy": per_case_minimum, "cases": cases, "bound": per_case_minimum * cases,
                        "argument": "every case costs at least the per-case minimum under conversion(); no program in the bounded "
                                    "language can go below cases x minimum on this evaluation set"},
        "best_found": min(r["energy"] for r in rows),
        "optimal_programs": [r["program"] for r in rows if r["energy"] == per_case_minimum * cases],
        "scope": "optimal only for these 12 phase cases, the fictional conversion rule, and energy as the objective",
        "verified_in_controller_grammar": sorted({r["program"] for r in rows if r["status"] == "verified" and r["in_controller_grammar"]}),
        "programs": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "programs"}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
