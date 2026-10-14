from __future__ import annotations

from copy import deepcopy

from .models import JSON, RESOURCES, Scenario, keyed

NAMES = ["Ada", "Ivo", "Sora", "Neri", "Eno", "Mira", "Tao", "Lumi", "Oren", "Kaia", "Rin", "Fenn", "Ari", "Nova", "Sol",
         "Juno", "Remy", "Asa", "Bea", "Elio", "Wren", "Iris", "Cato", "Lark", "Moss", "Pia", "Quill", "Rhea", "Sage", "Teo",
         "Uma", "Vale", "Wynn", "Xan", "Yara", "Zed", "Alba", "Bram", "Cleo", "Dov"]
OBSERVATION_RADIUS = 4
REACH = 2  # trade, transfer, message, library and storage reach


def distance(a: JSON, b: JSON) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def phase_at(state: JSON, agent: JSON) -> int:
    return keyed(state["config"]["seed"], "environment-phase", state["tick"], agent["x"], agent["y"]) % 12


def humidity_at(state: JSON, agent: JSON) -> int:
    return keyed(state["config"]["seed"], "environment-humidity", state["tick"], agent["x"], agent["y"]) % 8


USABLE = ("verified", "admitted")          # current library heads; holders may also keep using "superseded"


def library_access(agent: JSON, artifact: JSON, config: JSON | None = None) -> bool:
    """Knowledge access is a capability, independent of physical storage access. With cohorts and
    cross_cohort_access off, the library hides artifacts created by earlier cohorts."""
    if config is not None and not config.get("cross_cohort_access", True) and artifact.get("cohort", 0) != agent.get("cohort", 0):
        return False
    return "library" in agent["capabilities"] and artifact["home"] == agent["home"] and artifact["status"] in USABLE


def new_agent(aid: str, name: str, home: JSON, y_offset: int, tick: int, role: str, library: bool) -> JSON:
    return {"id": aid, "name": name, "home": home["id"], "x": home["x"], "y": home["y"] + y_offset,
            "created_tick": tick, "status": "active", "energy": 30,
            "capabilities": ["converter", "library"] if library else ["converter"],
            "inventory": {r: 0 for r in RESOURCES}, "known": [], "seen": [], "used": [], "role": role,
            "goals": ["maintain energy", "produce alloy", "evaluate procedures" if role == "researcher" else "learn accessible procedures"],
            "plan": "deterministic policy", "search_count": 0, "memories": [], "beliefs": [],
            "relationships": {}, "messages": [], "last_result": None,
            "predecessor": None, "successor": None, "inheritance": None, "retired_tick": None,
            "cohort": 0, "busy_until": 0, "dev_notes": {}}


def new_world(config: Scenario) -> JSON:
    c = config.model_dump()
    w, h = c["width"], c["height"]

    def settlement(sid: str, name: str, x: int) -> JSON:
        # Unlimited capacity; members (agents whose home it is) may deposit and withdraw.
        return {"id": sid, "name": name, "x": x, "y": h // 2, "inventory": {r: 0 for r in RESOURCES},
                "capacity": None, "access": "members",
                "flows": {kind: {r: 0 for r in RESOURCES} for kind in ("deposit", "withdraw", "retirement")}}

    settlements = {"hearth": settlement("hearth", "Hearth", w // 4), "haven": settlement("haven", "Haven", 3 * w // 4)}
    terrain = []
    for y in range(h):
        row = []
        for x in range(w):
            n = keyed(c["seed"], "world-terrain", x, y) % 100
            edge = min(x, y, w - 1 - x, h - 1 - y)
            tile = "water" if edge == 0 or (edge == 1 and n < 45) else "forest" if n < 26 else "hill" if n > 91 else "grass"
            if any(abs(x - s["x"]) <= 3 and abs(y - s["y"]) <= 3 for s in settlements.values()) or y == h // 2:
                if edge > 0:
                    tile = "grass"
            row.append(tile)
        terrain.append(row)
    sites = {}
    for s in settlements.values():
        for resource, dx, dy in (("food", -1, 0), ("ore", 1, 0), ("food", 0, 2), ("ore", 0, -2)):
            sid = f'{s["id"]}-{resource}-{dx}-{dy}'
            sites[sid] = {"id": sid, "resource": resource, "x": s["x"] + dx, "y": s["y"] + dy,
                          "stock": 120 if resource == "food" else c["ore_per_site"], "capacity": 120 if resource == "food" else c["ore_per_site"]}
    agents = {}
    split = (c["population"] + 1) // 2
    for i in range(c["population"]):
        home = settlements["hearth" if i < split else "haven"]
        role = "researcher" if i in (0, split) and c["controller"] == "search" else "producer"
        agent = new_agent(f"a{i:02d}", NAMES[i], home, (i % split) % 3, 0, role, c["sharing"])
        agent["inventory"] = {"food": 8, "ore": 8, "alloy": 0}
        agents[agent["id"]] = agent
    state = {"tick": 0, "config": c, "terrain": terrain, "settlements": settlements, "sites": sites,
             "agents": agents, "artifacts": {}, "offers": {}, "ledger": {r: {"source": 0, "sink": 0} for r in RESOURCES},
             "metrics": {"accepted": 0, "rejected": 0, "produced": 0, "production_energy": 0,
                         "search_proposals": 0, "revisions_verified": 0, "evaluation_cases": 0, "adoptions": 0, "transfers": 0,
                         "controller_failures": 0, "model_calls": 0, "tokens": 0, "cost_usd": 0,
                         "produced_after_removal": 0, "production_energy_after_removal": 0,
                         "uses_after_creator_removal": 0, "learned_after_creator_removal": 0},
             "lifecycle": {"removal": None, "successions": [], "cohort": 0, "transitions": [], "freezes": []},
             "sessions": {}}
    state["initial_totals"] = totals(state)
    return state


def totals(state: JSON) -> JSON:
    result = {r: 0 for r in RESOURCES}
    for owner in [*state["agents"].values(), *state["settlements"].values()]:
        for r in RESOURCES:
            result[r] += owner["inventory"][r]
    for site in state["sites"].values():
        result[site["resource"]] += site["stock"]
    return result


def check_invariants(state: JSON) -> None:
    for owner in [*state["agents"].values(), *state["settlements"].values()]:
        if any(type(v) is not int or v < 0 for v in owner["inventory"].values()):
            raise ValueError("negative/noninteger inventory")
    for site in state["sites"].values():
        if not 0 <= site["stock"] <= site["capacity"]:
            raise ValueError("site stock outside capacity")
    for agent in state["agents"].values():
        if not 0 <= agent["energy"] <= 40 or state["terrain"][agent["y"]][agent["x"]] == "water":
            raise ValueError("invalid energy or position")
        if agent["status"] == "retired" and any(agent["inventory"].values()):
            raise ValueError("retired agent still holds inventory")
    for r, amount in totals(state).items():
        if amount != state["initial_totals"][r] + state["ledger"][r]["source"] - state["ledger"][r]["sink"]:
            raise ValueError(f"resource conservation failure: {r}")


class LocalMemory:
    def retrieve(self, state: JSON, agent_id: str, limit: int = 8) -> list[JSON]:
        return deepcopy(state["agents"][agent_id]["memories"][-min(16, max(0, limit)):]) if limit else []


def session_view(session: JSON, agent_id: str) -> JSON:
    """A participant's own view of a session: no program, no counterpart's private state."""
    keys = ("id", "teacher", "learner", "artifact", "stage", "teacher_work", "learner_work", "required_work",
            "practice_required", "expires", "reason")
    view = {k: session.get(k) for k in keys}
    view["role"] = "teacher" if session["teacher"] == agent_id else "learner"
    view["practice_done"] = len(session["practice"])
    return view


ACTIVE_STAGES = ("offered", "instruction", "practice")


class LocalObservations:
    """Builds controller input from an explicit allow-list. It never receives or reuses the observer payload,
    and contains no seed, configuration, ledger, global metric, evaluation record or hidden world parameter."""

    def build(self, state: JSON, agent_id: str) -> JSON:
        a = state["agents"][agent_id]
        config = state["config"]
        nearby = [b for b in state["agents"].values() if b["id"] != agent_id and distance(a, b) <= REACH and b["status"] == "active"]
        accessible = {}
        for aid, artifact in state["artifacts"].items():
            own = artifact["creator"] == agent_id
            if own or aid in a["known"] or library_access(a, artifact, config):
                accessible[aid] = {k: deepcopy(artifact.get(k)) for k in ("id", "creator", "status", "created_tick", "parent", "generation")}
                if config.get("task") == "workshop-1":
                    accessible[aid]["kind"] = artifact.get("kind", "phase-program")
                if own or aid in a["known"]:
                    accessible[aid]["program"] = deepcopy(artifact["content"]["program"])
                if own and artifact.get("development"):
                    accessible[aid]["dev_score"] = artifact["development"]["score"]   # the proposer's own development result
        home = state["settlements"][a["home"]]
        r = OBSERVATION_RADIUS
        terrain = state["terrain"]
        tiles = [{"x": x, "y": y, "terrain": terrain[y][x]}
                 for y in range(max(0, a["y"] - r), min(len(terrain), a["y"] + r + 1))
                 for x in range(max(0, a["x"] - r), min(len(terrain[0]), a["x"] + r + 1))
                 if abs(x - a["x"]) + abs(y - a["y"]) <= r]
        sessions = state.get("sessions", {})
        mine = [session_view(x, agent_id) for x in sessions.values() if agent_id in (x["teacher"], x["learner"]) and x["stage"] in ACTIVE_STAGES]
        observation = {"tick": state["tick"], "self": deepcopy(a), "phase": phase_at(state, a),
                       "rules": {"invention_open": config["invention"] == "open", "search_budget": config["search_budget"],
                                 "task": config.get("task", "phase-1"), "teaching": config.get("teaching", False)},
                       "home_storage": dict(home["inventory"]) if distance(a, home) <= REACH else None,
                       "sites": deepcopy([s for s in state["sites"].values() if distance(a, s) <= r]),
                       "tiles": tiles,
                       "neighbors": [{k: b[k] for k in ("id", "name", "x", "y")} for b in nearby],
                       "offers": deepcopy([o for o in state["offers"].values() if o["target"] == agent_id and o["expires"] > state["tick"]]),
                       "artifacts": accessible, "memory": LocalMemory().retrieve(state, agent_id)}
        if config.get("task") == "workshop-1" or config.get("teaching"):
            observation["humidity"] = humidity_at(state, a)
            observation["sessions"] = mine
        return observation
