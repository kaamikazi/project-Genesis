"""Bounded data interpreter; never eval/exec host code. No access to world state."""
from __future__ import annotations

from . import EVALUATOR_VERSION
from .models import JSON, canonical, keyed

TRAIN = (1, 4, 7, 10)
HELD_OUT = (0, 2, 3, 5, 6, 8, 9, 11)


class InvalidProgram(ValueError):
    pass


def validate(program: JSON) -> None:
    if len(canonical(program)) > 2048:
        raise InvalidProgram("AST exceeds 2048 bytes")
    count = 0

    def visit(node: JSON, depth: int) -> None:
        nonlocal count
        count += 1
        if count > 15 or depth > 4 or not isinstance(node, dict):
            raise InvalidProgram("AST exceeds node/depth limit")
        if node.get("op") == "mode" and set(node) == {"op", "value"}:
            if type(node["value"]) is not int or node["value"] not in (0, 1):
                raise InvalidProgram("mode must be 0 or 1")
        elif node.get("op") == "if_phase_lt" and set(node) == {"op", "threshold", "then", "else"}:
            if type(node["threshold"]) is not int or not 0 <= node["threshold"] <= 12:
                raise InvalidProgram("threshold outside 0..12")
            visit(node["then"], depth + 1)
            visit(node["else"], depth + 1)
        else:
            raise InvalidProgram("unknown operator, measurement, or field")

    visit(program, 0)


def execute(program: JSON, phase: int, capabilities: list[str], max_steps: int = 8) -> tuple[int, int]:
    validate(program)
    if "converter" not in capabilities:
        raise InvalidProgram("converter capability required")
    if type(phase) is not int or not 0 <= phase <= 11:
        raise InvalidProgram("phase outside scope")
    node = program
    for steps in range(1, max_steps + 1):
        if node["op"] == "mode":
            return node["value"], steps
        node = node["then"] if phase < node["threshold"] else node["else"]
    raise InvalidProgram("execution step limit")


def conversion(phase: int, mode: int) -> JSON:
    # Fictional mechanic, publicly documented; controllers do not receive this function.
    return {"ore": 2, "alloy": 1, "energy": 2 if mode == (0 if phase < 6 else 1) else 6}


def _run_cases(program: JSON) -> list[JSON]:
    rows = []
    for group, phases in (("training", TRAIN), ("held_out", HELD_OUT)):
        for phase in phases:
            mode, steps = execute(program, phase, ["converter"])
            actual = conversion(phase, mode)
            rows.append({"group": group, "phase": phase, "mode": mode, "steps": steps,
                         "ore": actual["ore"], "alloy": actual["alloy"],
                         "energy": actual["energy"], "baseline_energy": conversion(phase, 0)["energy"]})
    return rows


class PhaseEvaluator:
    """Independent of the creator: re-executes the program (and any parent) on fixed cases."""
    def evaluate(self, program: JSON, parent: JSON | None = None) -> JSON:
        validate(program)
        rows = _run_cases(program)
        failures = [f'phase {r["phase"]}: {r["energy"]} energy is worse than baseline {r["baseline_energy"]}'
                    for r in rows if r["energy"] > r["baseline_energy"]]
        for group in ("training", "held_out"):
            subset = [r for r in rows if r["group"] == group]
            used, base = sum(r["energy"] for r in subset), sum(r["baseline_energy"] for r in subset)
            if 4 * used > 3 * base:
                failures.append(f"{group.replace('_', '-')} saving {round(100 * (base - used) / base)}% is below 25%")
        energy = sum(r["energy"] for r in rows)
        result: JSON = {"version": EVALUATOR_VERSION,
                        "scope": "phase 0..11; 2 ore -> 1 alloy; energy only; no cross-world generalization",
                        "criterion": ">=25% savings in each partition; no case worse than fixed mode 0",
                        "baseline": "fixed-mode-0", "cases": rows, "case_count": len(rows), "energy": energy,
                        "baseline_energy": sum(r["baseline_energy"] for r in rows)}
        if parent is not None:
            # A revision must strictly beat its parent, recomputed here rather than read from storage.
            parent_energy = sum(r["energy"] for r in _run_cases(parent))
            result.update(parent_energy=parent_energy, criterion=result["criterion"] + "; strictly less total energy than parent")
            result["case_count"] += len(rows)
            if energy >= parent_energy:
                failures.append(f"no improvement over parent ({energy} vs {parent_energy} energy)")
        result.update(status="rejected" if failures else "verified", failures=failures)
        return result


def candidate(seed: int, agent_id: str, index: int) -> JSON:
    """Finite search grammar: eight thresholds × two orientations; order keyed per agent."""
    space = [(threshold, direction) for threshold in range(2, 10) for direction in (0, 1)]
    space.sort(key=lambda pair: keyed(seed, "controller-search", agent_id, *pair))
    threshold, direction = space[index]
    return {"op": "if_phase_lt", "threshold": threshold,
            "then": {"op": "mode", "value": direction},
            "else": {"op": "mode", "value": 1 - direction}}


def revisions(program: JSON) -> list[JSON]:
    """Declared revision neighbourhood: shift the threshold by one, or swap the branches."""
    if program.get("op") != "if_phase_lt":
        return []
    result = []
    for threshold in (program["threshold"] - 1, program["threshold"] + 1):
        if 0 <= threshold <= 12:
            result.append({**program, "threshold": threshold})
    result.append({**program, "then": program["else"], "else": program["then"]})
    return result
