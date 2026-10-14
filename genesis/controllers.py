from __future__ import annotations

from .invention import candidate, revisions
from .models import Action, JSON, canonical, keyed
from .world import distance


class SearchBudget:
    def available(self, agent: JSON, limit: int) -> bool:
        return agent["search_count"] < limit


class OfflineController:
    """A designed deterministic policy with a bounded candidate enumerator. No LLM.

    Its only randomness is `seed`, supplied at construction from the scenario's independent `controller_seed`.
    The seed is held behind the controller boundary; observations carry no seed-derived value."""
    def __init__(self, seed: int = 7):
        self.seed = seed

    def propose(self, o: JSON) -> Action:
        a, tick = o["self"], o["tick"]

        def act(kind: str, **params) -> Action:
            return Action(id=f'{tick}:{a["id"]}', agent=a["id"], tick=tick, kind=kind, params=params)

        def gather(r: str) -> Action:
            sites = sorted([s for s in o["sites"] if s["resource"] == r and s["stock"] > 0], key=lambda s: (distance(a, s), s["id"]))
            if not sites:
                return act("wait")
            target = sites[0]
            if distance(a, target) <= 1:
                return act("gather", site=target["id"])
            tiles = [t for t in o["tiles"] if distance(a, t) == 1 and t["terrain"] != "water"]
            tiles.sort(key=lambda t: (distance(t, target), t["y"], t["x"]))
            if tiles:
                return act("move", x=tiles[0]["x"], y=tiles[0]["y"])
            return act("wait")

        if a["energy"] <= 10 and a["inventory"]["food"]:
            return act("consume")
        storage = o["home_storage"]
        if a["inventory"]["food"] < 3:
            if storage and storage["food"] > 0:
                return act("withdraw", settlement=a["home"], resource="food", amount=min(4, storage["food"]))
            return gather("food")
        for offer in o["offers"]:
            if a["inventory"][offer["want"]] >= offer["want_amount"]:
                return act("accept_trade", offer=offer["id"])
        own = [v for v in o["artifacts"].values() if v["creator"] == a["id"]]
        pending = [v for v in own if v["status"] == "proposed"]
        if pending:
            return act("test_artifact", artifact=pending[0]["id"])
        if a["role"] == "researcher" and o["rules"]["invention_open"] and SearchBudget().available(a, o["rules"]["search_budget"]):
            best = sorted((v for v in own if v["status"] == "verified"), key=lambda v: -v["created_tick"])
            if not best:
                return act("propose_artifact", program=candidate(self.seed, a["id"], a["search_count"]), parent=None)
            # Local search: try each untried revision of the current best; stop at a local optimum.
            tried = {canonical(v["program"]) for v in own if v["parent"] == best[0]["id"]}
            options = [r for r in revisions(best[0]["program"]) if canonical(r) not in tried]
            options.sort(key=lambda r: keyed(self.seed, "controller-revision", a["id"], canonical(r)))
            if options:
                return act("propose_artifact", program=options[0], parent=best[0]["id"])
        known = [o["artifacts"][k] for k in a["known"] if k in o["artifacts"]]
        learnable = [v for v in o["artifacts"].values() if v["status"] == "verified" and v["id"] not in a["known"]]
        if learnable and not any(v["status"] == "verified" for v in known):
            return act("inspect_artifact", artifact=learnable[0]["id"])
        # Small, explicitly scripted exchange policy; all effects still pass engine validation.
        if tick % 31 == 9 and a["inventory"]["alloy"] >= 2 and o["neighbors"]:
            return act("offer_trade", target=o["neighbors"][0]["id"], give="alloy", give_amount=1, want="food", want_amount=1)
        if tick % 43 == 17 and a["inventory"]["food"] >= 5 and o["neighbors"]:
            return act("transfer", target=o["neighbors"][0]["id"], resource="food", amount=1)
        if a["inventory"]["ore"] < 2:
            if storage and storage["ore"] >= 2:
                return act("withdraw", settlement=a["home"], resource="ore", amount=min(8, storage["ore"]))
            return gather("ore")
        usable = sorted((v for v in known if v["status"] in ("verified", "superseded")), key=lambda v: (v["status"] != "verified", -v["created_tick"]))
        if usable:
            return act("use_artifact", artifact=usable[0]["id"])
        return act("produce")
