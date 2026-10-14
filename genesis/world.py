from __future__ import annotations

from copy import deepcopy

from .models import JSON, RESOURCES, Scenario, keyed

NAMES = ["Ada", "Ivo", "Sora", "Neri", "Eno", "Mira", "Tao", "Lumi", "Oren", "Kaia", "Rin", "Fenn", "Ari", "Nova", "Sol", "Juno", "Remy", "Asa", "Bea", "Elio"]


def distance(a: JSON, b: JSON) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def phase_at(state: JSON, agent: JSON) -> int:
    return keyed(state["config"]["seed"], "environment-phase", state["tick"], agent["x"], agent["y"]) % 12


def controller_seed(state: JSON, agent_id: str) -> int:
    return keyed(state["config"]["seed"], "controller-stream", agent_id) % 2**31


def new_world(config: Scenario) -> JSON:
    c = config.model_dump()
    w, h = c["width"], c["height"]
    settlements = {"hearth": {"id": "hearth", "name": "Hearth", "x": w // 4, "y": h // 2,
                              "inventory": {r: 0 for r in RESOURCES}},
                   "haven": {"id": "haven", "name": "Haven", "x": 3 * w // 4, "y": h // 2,
                             "inventory": {r: 0 for r in RESOURCES}}}
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
                          "stock": 120 if resource == "food" else 240, "capacity": 120 if resource == "food" else 240}
    agents = {}
    split = (c["population"] + 1) // 2
    for i in range(c["population"]):
        home = "hearth" if i < split else "haven"
        sid = f"a{i:02d}"
        s = settlements[home]
        agents[sid] = {"id": sid, "name": NAMES[i], "home": home, "x": s["x"], "y": s["y"] + (i % split) % 3,
                       "created_tick": 0, "status": "active", "energy": 30, "capabilities": ["converter"],
                       "inventory": {"food": 8, "ore": 8, "alloy": 0}, "known": [], "seen": [], "used": [],
                       "role": "researcher" if i in (0, split) and c["controller"] == "search" else "producer",
                       "goals": ["maintain energy", "produce alloy", "evaluate procedures" if i in (0, split) else "learn accessible procedures"],
                       "plan": "deterministic policy", "search_count": 0, "memories": [], "beliefs": [],
                       "relationships": {}, "messages": [], "last_result": None}
    state = {"tick": 0, "config": c, "terrain": terrain, "settlements": settlements, "sites": sites,
             "agents": agents, "artifacts": {}, "offers": {}, "ledger": {r: {"source": 0, "sink": 0} for r in RESOURCES},
             "metrics": {"accepted": 0, "rejected": 0, "produced": 0, "production_energy": 0,
                         "search_proposals": 0, "revisions_verified": 0, "evaluation_cases": 0, "adoptions": 0, "transfers": 0,
                         "controller_failures": 0, "model_calls": 0, "tokens": 0, "cost_usd": 0,
                         "produced_after_removal": 0, "production_energy_after_removal": 0,
                         "uses_after_creator_removal": 0, "learned_after_creator_removal": 0},
             "lifecycle": {"removal": None}}
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
    for r, amount in totals(state).items():
        if amount != state["initial_totals"][r] + state["ledger"][r]["source"] - state["ledger"][r]["sink"]:
            raise ValueError(f"resource conservation failure: {r}")


class LocalMemory:
    def retrieve(self, state: JSON, agent_id: str, limit: int = 8) -> list[JSON]:
        return deepcopy(state["agents"][agent_id]["memories"][-min(16, max(0, limit)):]) if limit else []


class LocalObservations:
    def build(self, state: JSON, agent_id: str) -> JSON:
        a = state["agents"][agent_id]
        nearby = [b for b in state["agents"].values() if b["id"] != agent_id and distance(a, b) <= 2 and b["status"] == "active"]
        accessible = {}
        for aid, artifact in state["artifacts"].items():
            own = artifact["creator"] == agent_id
            public = state["config"]["sharing"] and artifact["home"] == a["home"] and artifact["status"] == "verified"
            if own or aid in a["known"] or public:
                accessible[aid] = {k: deepcopy(artifact[k]) for k in ("id", "creator", "status", "created_tick", "parent", "generation")}
                if own or aid in a["known"]:
                    accessible[aid]["program"] = deepcopy(artifact["content"]["program"])
                # Held-out case-level evidence stays in the observer interface, not controller inputs.
        return {"tick": state["tick"], "self": deepcopy(a), "phase": phase_at(state, a),
                # A per-agent controller stream, never the world seed: the seed would let a controller
                # recompute terrain and every location's hidden phase.
                "controller_seed": controller_seed(state, agent_id), "search_budget": state["config"]["search_budget"],
                "sites": deepcopy([s for s in state["sites"].values() if distance(a, s) <= 4]),
                "tiles": [{"x": x, "y": y, "terrain": tile} for y, row in enumerate(state["terrain"]) for x, tile in enumerate(row) if abs(x-a["x"]) + abs(y-a["y"]) <= 4],
                "neighbors": [{k: b[k] for k in ("id", "name", "x", "y")} for b in nearby],
                "offers": deepcopy([o for o in state["offers"].values() if o["target"] == agent_id and o["expires"] > state["tick"]]),
                "artifacts": accessible, "memory": LocalMemory().retrieve(state, agent_id)}
