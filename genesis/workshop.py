"""Task family `workshop-1`: a multi-stage batch workflow with interacting decisions.

Bounded data interpreter only; nothing here is executed as host code. The sealed evaluation partition is NOT
defined here; see genesis/sealed.py, which the world, engine, controllers and storage never import.
"""
from __future__ import annotations

import math
from typing import Any

from .models import JSON, canonical, digest, keyed

TASK = "workshop-1"
EVALUATOR_VERSION = "workshop-evaluator-4"   # adds behaviour hashes and the in-host component protocol
FIELDS = {"batch": (1, 4), "heat": (0, 3), "mode": (0, 1), "flux": (0, 1)}
MEASURES = {"phase": (0, 11), "humidity": (0, 7), "ore": (0, 100), "energy": (0, 40)}
SPLIT_THRESHOLDS = {"phase": (4, 6, 8), "humidity": (2, 4, 6), "ore": (4, 6, 8), "energy": (12, 20, 28)}
MAX_NODES, MAX_DEPTH, MAX_BYTES, MAX_STEPS = 48, 6, 4096, 64
INFEASIBLE_PENALTY = 10
BASELINE: JSON = {"op": "workflow", "batch": {"op": "const", "value": 1}, "heat": {"op": "const", "value": 1},
                  "mode": {"op": "const", "value": 0}, "flux": {"op": "const", "value": 0}}
CASE_GRID = [(p, h, o, e) for p in range(12) for h in range(8) for o in (2, 4, 6, 8, 10) for e in (8, 14, 20, 28, 40)]
PARTITION_SEED = 20261014  # public task-version seed for development and validation partitions


class InvalidWorkflow(ValueError):
    pass


def kind_of(program: Any) -> str | None:
    return program.get("op") if isinstance(program, dict) and program.get("op") in ("workflow", "component") else None


def is_workshop(program: Any) -> bool:
    return kind_of(program) is not None


def calls(program: JSON) -> list[str]:
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("op") == "call":
                found.append(node.get("artifact"))
            for value in node.values():
                walk(value)
    walk(program)
    return sorted(set(found))


def validate(program: JSON) -> None:
    if len(canonical(program)) > MAX_BYTES:
        raise InvalidWorkflow(f"program exceeds {MAX_BYTES} bytes")
    count = 0

    def expr(node: Any, depth: int, field: str | None, allow_call: bool) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH or not isinstance(node, dict):
            raise InvalidWorkflow("expression exceeds node/depth limit or is malformed")
        op = node.get("op")
        if op == "const" and set(node) == {"op", "value"}:
            low, high = FIELDS[field] if field else (0, 100)
            if type(node["value"]) is not int or not low <= node["value"] <= high:
                raise InvalidWorkflow(f"constant outside {field} range {low}..{high}")
        elif op == "if_lt" and set(node) == {"op", "measure", "threshold", "then", "else"}:
            if node["measure"] not in MEASURES or type(node["threshold"]) is not int or not 0 <= node["threshold"] <= 101:
                raise InvalidWorkflow("unknown measure or threshold out of range")
            expr(node["then"], depth + 1, field, allow_call)
            expr(node["else"], depth + 1, field, allow_call)
        elif op == "call" and set(node) == {"op", "artifact"} and allow_call:
            if not isinstance(node["artifact"], str) or len(node["artifact"]) != 64:
                raise InvalidWorkflow("call needs a 64-hex artifact id")
        else:
            raise InvalidWorkflow("unknown operator or field")

    kind = kind_of(program)
    if kind == "workflow" and set(program) == {"op", *FIELDS}:
        for field in FIELDS:
            expr(program[field], 1, field, True)
    elif kind == "component" and set(program) == {"op", "field", "expr"} and program["field"] in FIELDS:
        expr(program["expr"], 1, program["field"], True)    # components may call components; closure limits apply
    else:
        raise InvalidWorkflow("program must be a workflow or component with exact fields")


def closure(program: JSON, resolve) -> list[str]:
    """Transitive dependency closure by hash, in dependency order. `resolve(id)` returns a program or None."""
    order: list[str] = []

    def visit(node_program: JSON, stack: tuple) -> None:
        for dep in calls(node_program):
            if dep in stack:
                raise InvalidWorkflow(f"cyclic component reference {dep[:8]}")
            target = resolve(dep)
            if target is None:
                raise InvalidWorkflow(f"missing prerequisite component {dep[:8]}")
            if kind_of(target) != "component":
                raise InvalidWorkflow("calls must name components")
            if dep not in order:
                visit(target, stack + (dep,))
                order.append(dep)
    visit(program, ())
    return order


def check_closure_limits(program: JSON, resolve) -> JSON:
    """Inline the closure and apply the global node and depth limits: splitting a program across artifacts
    grants no extra allowance."""
    nodes = 0
    deepest = 0

    def walk(node: JSON, depth: int, field: str, stack: tuple) -> None:
        nonlocal nodes, deepest
        if node["op"] == "call":
            if node["artifact"] in stack:
                raise InvalidWorkflow("cyclic component reference")
            target = resolve(node["artifact"])
            if target is None:
                raise InvalidWorkflow(f"missing prerequisite component {node['artifact'][:8]}")
            if target.get("field") != field:
                raise InvalidWorkflow("component field mismatch (incompatible interface)")
            walk(target["expr"], depth, field, stack + (node["artifact"],))   # the call node is replaced by the callee
            return
        nodes += 1
        deepest = max(deepest, depth)
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise InvalidWorkflow("inlined closure exceeds node/depth limit")
        if node["op"] == "if_lt":
            walk(node["then"], depth + 1, field, stack)
            walk(node["else"], depth + 1, field, stack)

    if kind_of(program) == "workflow":
        for field in FIELDS:
            walk(program[field], 1, field, ())
    else:
        walk(program["expr"], 1, program["field"], ())
    return {"inlined_nodes": nodes, "inlined_depth": deepest}


def execute(program: JSON, measures: dict[str, int], held: dict[str, JSON]) -> tuple[dict[str, int], int]:
    """Evaluate a workflow to a decision. `held` maps artifact id -> program for components the executor holds.
    The step limit is shared across the whole call tree; cycles are rejected."""
    validate(program)
    if kind_of(program) != "workflow":
        raise InvalidWorkflow("only workflows execute")
    steps = 0

    def evaluate(node: JSON, field: str, stack: tuple) -> int:
        nonlocal steps
        steps += 1
        if steps > MAX_STEPS:
            raise InvalidWorkflow("execution step limit")
        op = node["op"]
        if op == "const":
            return node["value"]
        if op == "if_lt":
            return evaluate(node["then"] if measures[node["measure"]] < node["threshold"] else node["else"], field, stack)
        if node["artifact"] in stack:
            raise InvalidWorkflow("cyclic component reference")
        component = held.get(node["artifact"])
        if component is None:
            raise InvalidWorkflow(f"missing prerequisite component {node['artifact'][:8]}")
        if component.get("field") != field:
            raise InvalidWorkflow("component field mismatch")
        return evaluate(component["expr"], field, stack + (node["artifact"],))

    decision = {}
    for field, (low, high) in FIELDS.items():
        value = evaluate(program[field], field, ())
        if not low <= value <= high:
            raise InvalidWorkflow(f"{field} outside range")
        decision[field] = value
    return decision, steps


def substitute(host: JSON, component_id: str, component: JSON) -> JSON:
    """The host workflow with the component's field replaced by a call to it."""
    return {**host, component["field"]: {"op": "call", "artifact": component_id}}


def behavior_hash(program: JSON, cases: list, held: dict[str, JSON]) -> str:
    """Decisions on the given cases; equal hashes mean behaviourally identical on those cases."""
    out = []
    for phase, humidity, ore, energy in cases:
        decision, _ = execute(program, {"phase": phase, "humidity": humidity, "ore": ore, "energy": energy}, held)
        out.append([decision[f] for f in FIELDS])
    return digest(out)


def hidden_params(config: JSON) -> JSON:
    """Hidden mechanics of a world: from the declared combination (streams-1) or derived from the seed (legacy)."""
    if config.get("seed_scheme", "legacy") == "streams-1":
        split, offset, flux = config["hidden_combo"]
        return {"split": split, "offset": offset, "flux_threshold": flux}
    return world_params(config["seed"])


FAMILY = [(s, o, f) for s in range(4, 9) for o in range(3) for f in range(4, 7)]     # all 45 workshop-1 parameterisations


def world_params(seed: int) -> JSON:
    """Hidden per-world mechanics. Never placed in observations."""
    return {"split": 4 + keyed(seed, "workshop-params", "split") % 5,
            "offset": keyed(seed, "workshop-params", "offset") % 3,
            "flux_threshold": 4 + keyed(seed, "workshop-params", "flux") % 3}


def outcome(params: JSON, measures: dict[str, int], decision: dict[str, int]) -> JSON:
    """Batch of b alloy. Wrong heat or missing flux in humid air wastes extra ore; the mode and heat set energy."""
    b, h, m, x = decision["batch"], decision["heat"], decision["mode"], decision["flux"]
    optimal = min(3, (measures["humidity"] + params["offset"]) // 3)
    wasted = math.ceil(b * abs(h - optimal) / 2) + (1 if measures["humidity"] >= params["flux_threshold"] and not x else 0)
    ore = 2 * b + wasted
    if measures["ore"] < ore:
        return {"feasible": False, "reason": f"insufficient ore for batch (needs {ore})", "decision": decision}
    unit = 2 if (m == 0) == (measures["phase"] < params["split"]) else 5
    energy = 3 + b * unit + 2 * h
    if measures["energy"] < energy:
        return {"feasible": False, "reason": f"insufficient energy for batch (needs {energy})", "decision": decision}
    return {"feasible": True, "decision": decision, "ore": ore, "alloy": b, "energy": energy, "food": x,
            "ore_wasted": wasted, "busy_ticks": b - 1, "cost": energy + 4 * wasted + 3 * x}


def partition(name: str, size: int, exclude: set | None = None, seed: int = PARTITION_SEED) -> list[tuple[int, int, int, int]]:
    pool = [c for c in CASE_GRID if not exclude or c not in exclude]
    pool.sort(key=lambda c: keyed(seed, f"workshop-1-{name}", *c))
    return pool[:size]


DEV_CASES = partition("dev", 24)
VALIDATION_CASES = partition("validation", 24, set(DEV_CASES))
PANEL_COUNT = 10


def panel_cases(k: int) -> list[tuple[int, int, int, int]]:
    """Precommitted admission panel for cohort k (validation_policy cohort-panels): 24 cases disjoint from development,
    validation and every other panel. Committed in code before any run; agents never observe case lists."""
    taken = set(DEV_CASES) | set(VALIDATION_CASES)
    for j in range(PANEL_COUNT):
        cases = partition(f"panel-{j}", 24, taken)
        if j == k:
            return cases
        taken |= set(cases)
    raise ValueError(f"no panel {k} (only {PANEL_COUNT} panels are committed)")


def all_panel_cases() -> set:
    return {c for k in range(PANEL_COUNT) for c in panel_cases(k)}


def selection_cases() -> list[tuple[int, int, int, int]]:
    """v0.5.2 shared final-selection panel: 24 cases disjoint from development, validation and every admission panel.
    Used only observer-side to choose frozen champions; no agent receives these scores."""
    return partition("selection-0", 24, set(DEV_CASES) | set(VALIDATION_CASES) | all_panel_cases())


def score_cases(program: JSON, params: JSON, cases: list, held: dict[str, JSON]) -> JSON:
    rows, cost, alloy = [], 0, 0
    for phase, humidity, ore, energy in cases:
        measures = {"phase": phase, "humidity": humidity, "ore": ore, "energy": energy}
        decision, _ = execute(program, measures, held)
        result = outcome(params, measures, decision)
        case_cost = result["cost"] if result["feasible"] else INFEASIBLE_PENALTY
        case_alloy = result["alloy"] if result["feasible"] else 0
        cost, alloy = cost + case_cost, alloy + case_alloy
        rows.append({"phase": phase, "humidity": humidity, "ore": ore, "energy": energy, "feasible": result["feasible"],
                     "cost": case_cost, "alloy": case_alloy, **({} if result["feasible"] else {"reason": result["reason"]})})
    return {"cases": rows, "cost": cost, "alloy": alloy, "score": round(cost / alloy, 6) if alloy else None}


class WorkshopEvaluator:
    """Development and validation roles. Neither has access to sealed cases."""
    version = EVALUATOR_VERSION

    def development(self, program: JSON, params: JSON, held: dict[str, JSON]) -> JSON:
        own = score_cases(program, params, DEV_CASES, held)
        base = score_cases(BASELINE, params, DEV_CASES, {})
        return {"role": "development", "version": self.version, "partition": "dev-24", "score": own["score"],
                "baseline_score": base["score"], "cases": own["cases"], "objective": OBJECTIVE,
                "behavior_hash": behavior_hash(program, DEV_CASES, held)}

    def validation(self, program: JSON, params: JSON, held: dict[str, JSON], parent: JSON | None, parent_held: dict[str, JSON],
                   cases: list | None = None, partition_name: str = "validation-24") -> JSON:
        """Admission. Child, baseline and reference are all scored on the SAME current cases (never on stored scores)."""
        cases = VALIDATION_CASES if cases is None else cases
        own = score_cases(program, params, cases, held)
        base = score_cases(BASELINE, params, cases, {})
        reference = score_cases(parent, params, cases, parent_held)["score"] if parent else None
        if own["score"] is None:
            admitted, criterion = False, "no alloy on validation cases"
        elif parent is not None:
            admitted, criterion = reference is not None and own["score"] < reference, "validation score strictly below parent's on the same 24 cases"
        else:
            admitted, criterion = base["score"] is not None and own["score"] < 0.95 * base["score"], "validation score at least 5% below baseline"
        return {"role": "validation", "version": self.version, "partition": partition_name, "score": own["score"],
                "baseline_score": base["score"], "parent_score": reference, "admitted": admitted, "criterion": criterion,
                "feedback_policy": "the proposer learns only admitted/not admitted (one bit per submission)"}


OBJECTIVE = "pooled (energy + 4 x ore wasted + 3 x food) / alloy over the case set; infeasible case = cost 10, alloy 0; lower is better"


def _paths(node: Any, path: tuple = ()) -> list[tuple]:
    out = [path]
    if isinstance(node, dict) and node.get("op") == "if_lt":
        out += _paths(node["then"], path + ("then",)) + _paths(node["else"], path + ("else",))
    return out


def _get(node: JSON, path: tuple) -> JSON:
    for key in path:
        node = node[key]
    return node


def _set(tree: JSON, path: tuple, value: JSON) -> JSON:
    if not path:
        return value
    copy = dict(tree)
    copy[path[0]] = _set(tree[path[0]], path[1:], value)
    return copy


def neighbours(program: JSON, others: list[JSON] = ()) -> list[tuple[str, JSON]]:
    """Declared search neighbourhood: field recombination from other held workflows (composition), constant +-1,
    threshold shift +-1, and splitting a constant leaf on one measure at a fixed threshold."""
    out: list[tuple[str, JSON]] = []
    for other in others:
        if kind_of(other) == "workflow":
            for field in FIELDS:
                if canonical(other[field]) != canonical(program[field]):
                    out.append((f"compose:{field}", {**program, field: other[field]}))
    for field, (low, high) in FIELDS.items():
        for path in _paths(program[field]):
            node = _get(program[field], path)
            if node["op"] == "const":
                for v in (node["value"] - 1, node["value"] + 1):
                    if low <= v <= high:
                        out.append((f"const:{field}", {**program, field: _set(program[field], path, {"op": "const", "value": v})}))
                if len(path) < 3:
                    for measure, thresholds in SPLIT_THRESHOLDS.items():
                        for t in thresholds:
                            for v in (node["value"] - 1, node["value"] + 1):
                                if low <= v <= high:
                                    for then, other_branch in ((node["value"], v), (v, node["value"])):
                                        split = {"op": "if_lt", "measure": measure, "threshold": t,
                                                 "then": {"op": "const", "value": then}, "else": {"op": "const", "value": other_branch}}
                                        out.append((f"split:{field}:{measure}", {**program, field: _set(program[field], path, split)}))
            elif node["op"] == "if_lt":
                lo, hi = MEASURES[node["measure"]]
                for t in (node["threshold"] - 1, node["threshold"] + 1):
                    if lo <= t <= hi + 1:
                        out.append((f"threshold:{field}:{node['measure']}", {**program, field: _set(program[field], path, {**node, "threshold": t})}))
    seen, unique = set(), []
    for label, candidate in out:
        key = canonical(candidate)
        if key not in seen and key != canonical(program):
            try:
                validate(candidate)
            except InvalidWorkflow:
                continue
            seen.add(key)
            unique.append((label, candidate))
    return unique


def program_id(program: JSON) -> str:
    return digest(program)


def component_operators(host: JSON, held_components: dict[str, JSON]) -> list[tuple[str, JSON, JSON]]:
    """Declared component operators. Each item is (label, program, extra) where extra names the parent or host.
    - extract:<field>      a component equal to a non-constant host field (refactoring, not discovery)
    - call:<field>         the host with a field replaced by a call to a held admitted component (reuse/composition)
    - mutate-component     a neighbouring expression of a held component (behaviourally different revision)"""
    out: list[tuple[str, JSON, JSON]] = []
    for field in FIELDS:
        expr = host[field]
        if expr["op"] == "if_lt":
            out.append((f"extract:{field}", {"op": "component", "field": field, "expr": expr}, {"kind": "component", "host_field": field}))
    for cid, comp in sorted(held_components.items()):
        if canonical(host[comp["field"]]) != canonical({"op": "call", "artifact": cid}):
            out.append((f"call:{comp['field']}", {**host, comp["field"]: {"op": "call", "artifact": cid}}, {"kind": "workflow", "component": cid}))
        wrapper = {"op": "workflow", **{f: ({"op": "const", "value": FIELDS[f][0]} if f != comp["field"] else comp["expr"]) for f in FIELDS}}
        for label, neighbour in neighbours(wrapper):
            if label.split(":")[1] == comp["field"] and not label.startswith("compose"):
                candidate = {"op": "component", "field": comp["field"], "expr": neighbour[comp["field"]]}
                try:
                    validate(candidate)
                except InvalidWorkflow:
                    continue
                out.append(("mutate-component", candidate, {"kind": "component", "parent": cid}))
    return out



def _thresholds(node: JSON, held: dict[str, JSON], out: dict[str, set], stack: tuple = ()) -> None:
    if node["op"] == "if_lt":
        out.setdefault(node["measure"], set()).add(node["threshold"])
        _thresholds(node["then"], held, out, stack)
        _thresholds(node["else"], held, out, stack)
    elif node["op"] == "call" and node["artifact"] in held and node["artifact"] not in stack:
        _thresholds(held[node["artifact"]]["expr"], held, out, stack + (node["artifact"],))


def _field_value(node: JSON, measures: dict[str, int], held: dict[str, JSON], stack: tuple = ()) -> int:
    if node["op"] == "const":
        return node["value"]
    if node["op"] == "if_lt":
        return _field_value(node["then"] if measures[node["measure"]] < node["threshold"] else node["else"], measures, held, stack)
    if node["artifact"] in stack or node["artifact"] not in held:
        raise InvalidWorkflow("unresolvable call in equivalence check")
    return _field_value(held[node["artifact"]]["expr"], measures, held, stack + (node["artifact"],))


def field_equivalent(a: JSON, b: JSON, held: dict[str, JSON]) -> tuple[bool, int]:
    """Exact equivalence of two field expressions over EVERY integer input. Expressions compare measures only through
    `measure < threshold`, so each expression is constant on the cells cut by the union of both expressions'
    thresholds; one point per cell (min threshold - 1, then each threshold) decides equality. Returns (equal,
    point_evaluations) so callers can account the work. Uses no task cases, outcomes or hidden parameters."""
    if canonical(a) == canonical(b):
        return True, 0
    cuts: dict[str, set] = {}
    _thresholds(a, held, cuts)
    _thresholds(b, held, cuts)
    names = sorted(cuts)
    axes = [[min(cuts[m]) - 1] + sorted(cuts[m]) for m in names]
    points = [{}]
    for name, values in zip(names, axes):
        points = [{**pt, name: v} for pt in points for v in values]
    work = 0
    for pt in points:
        work += 2
        if _field_value(a, pt, held) != _field_value(b, pt, held):
            return False, work
    return True, work


def decision_equivalent(a: JSON, b: JSON, held: dict[str, JSON]) -> bool:
    """True when two workflows make the same decision for every possible input (exact, not sampled)."""
    return decision_equivalence(a, b, held)[0]


def decision_equivalence(a: JSON, b: JSON, held: dict[str, JSON]) -> tuple[bool, int]:
    work = 0
    for field in FIELDS:
        same, w = field_equivalent(a[field], b[field], held)
        work += w
        if not same:
            return False, work
    return True, work
