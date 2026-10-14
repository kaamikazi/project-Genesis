from __future__ import annotations

from . import workshop as ws
from .invention import candidate, revisions
from .models import Action, JSON, canonical, keyed
from .world import distance

USABLE_HELD = ("verified", "admitted", "superseded")


class SearchBudget:
    def available(self, agent: JSON, limit: int) -> bool:
        return agent["search_count"] < limit


class OfflineController:
    """A designed deterministic policy with a bounded candidate enumerator. No LLM.

    Its only randomness is `seed`, supplied at construction from the scenario's independent `controller_seed`.
    The seed is held behind the controller boundary; observations carry no seed-derived value. Every branch
    below is developer-supplied policy; the engine decides every outcome."""
    def __init__(self, seed: int = 7):
        self.seed = seed

    def propose(self, o: JSON) -> Action:
        a, tick = o["self"], o["tick"]

        def act(kind: str, **params) -> Action:
            return Action(id=f'{tick}:{a["id"]}', agent=a["id"], tick=tick, kind=kind, params=params)

        def step_towards(target: JSON) -> Action:
            tiles = [t for t in o["tiles"] if distance(a, t) == 1 and t["terrain"] != "water"]
            tiles.sort(key=lambda t: (distance(t, target), t["y"], t["x"]))
            return act("move", x=tiles[0]["x"], y=tiles[0]["y"]) if tiles else act("wait")

        def gather(r: str) -> Action:
            sites = sorted([s for s in o["sites"] if s["resource"] == r and s["stock"] > 0], key=lambda s: (distance(a, s), s["id"]))
            if not sites:
                return act("wait")
            target = sites[0]
            if distance(a, target) <= 1:
                return act("gather", site=target["id"])
            return step_towards(target)

        if a.get("busy_until", 0) > tick:
            return act("wait")                       # occupied by a multi-tick batch
        if a["energy"] <= 10 and a["inventory"]["food"]:
            return act("consume")
        reserved = next((x for x in o.get("sessions") or [] if x["stage"] == "instruction"), None)
        if reserved:
            # Reserved by an instruction stage: only the session step (or eating, above) is permitted.
            if reserved[f'{reserved["role"]}_work'] >= reserved["required_work"]:
                return act("wait")
            return act("teach_step" if reserved["role"] == "teacher" else "learn_step", session=reserved["id"])
        storage = o["home_storage"]

        def obtain(r: str, amount: int) -> Action:
            if storage and storage[r] >= 1:
                return act("withdraw", settlement=a["home"], resource=r, amount=min(amount, storage[r]))
            return gather(r)

        if a["inventory"]["food"] < 3:
            return obtain("food", 4)
        for offer in o["offers"]:
            if a["inventory"][offer["want"]] >= offer["want_amount"]:
                return act("accept_trade", offer=offer["id"])
        if o["rules"].get("teaching"):
            lesson = self._teaching(o, act, step_towards, obtain)
            if lesson:
                return lesson
        if o["rules"].get("task") == "workshop-1":
            return self._workshop(o, act, obtain)
        own = [v for v in o["artifacts"].values() if v["creator"] == a["id"]]
        pending = [v for v in own if v["status"] == "proposed"]
        if pending:
            return act("test_artifact", artifact=pending[0]["id"])
        known = [o["artifacts"][k] for k in a["known"] if k in o["artifacts"]]
        learnable = [v for v in o["artifacts"].values() if v["status"] == "verified" and v["id"] not in a["known"]]
        if learnable and not any(v["status"] == "verified" for v in known):
            # Learn an accessible verified procedure before searching from scratch (researchers then revise it).
            return act("inspect_artifact", artifact=learnable[0]["id"])
        if a["role"] == "researcher" and o["rules"]["invention_open"] and SearchBudget().available(a, o["rules"]["search_budget"]):
            best = sorted((v for v in known if v["status"] == "verified"), key=lambda v: -v["created_tick"])
            if not best:
                return act("propose_artifact", program=candidate(self.seed, a["id"], a["search_count"]), parent=None)
            # Local search from the best verified procedure it holds (its own or one learned from the library):
            # try each untried revision; stop at a local optimum.
            tried = {canonical(v["program"]) for v in own if v["parent"] == best[0]["id"]}
            options = [r for r in revisions(best[0]["program"]) if canonical(r) not in tried]
            options.sort(key=lambda r: keyed(self.seed, "controller-revision", a["id"], canonical(r)))
            if options:
                return act("propose_artifact", program=options[0], parent=best[0]["id"])
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

    # --- teaching -------------------------------------------------------------------------------

    def _teaching(self, o: JSON, act, step_towards, obtain) -> Action | None:
        """Respond to observed needs: learners without a usable procedure ask; holders answer recent requests."""
        a, tick = o["self"], o["tick"]
        neighbors = {n["id"]: n for n in o["neighbors"]}
        session = (o.get("sessions") or [None])[0]
        if session:
            partner = session["learner"] if session["role"] == "teacher" else session["teacher"]
            if session["stage"] == "offered":
                if session["role"] == "learner":
                    if partner in neighbors and distance(a, neighbors[partner]) > 1:
                        return step_towards(neighbors[partner])
                    return act("accept_teaching", session=session["id"])
                return act("wait")                   # the teacher stays put while its offer is open
            if session["stage"] == "instruction":
                return act("teach_step" if session["role"] == "teacher" else "learn_step", session=session["id"])
            if session["stage"] == "practice" and session["role"] == "learner":
                if a["inventory"]["ore"] < 4:
                    return obtain("ore", 8)
                if a["energy"] < 16 and a["inventory"]["food"]:
                    return act("consume")
                return act("practice_step", session=session["id"])
            return None
        held = [o["artifacts"][k] for k in a["known"] if k in o["artifacts"] and o["artifacts"][k]["status"] in USABLE_HELD + ("component",)]
        library = [v for v in o["artifacts"].values() if v["id"] not in a["known"] and v["status"] in ("verified", "admitted")]
        if not held and not library:
            asked = [m for m in a["memories"] if m.get("kind") == "send_message" and m.get("tick", 0) >= tick - 6]
            if o["neighbors"] and not asked:
                return act("send_message", target=o["neighbors"][0]["id"], message="request_lesson")
            return None
        requests = [m for m in a.get("messages", []) if m["claim"] == "request_lesson" and m["tick"] >= tick - 6 and m["from"] in neighbors]
        teachable = sorted((v for v in held if v.get("kind", "workflow") != "component"), key=lambda v: -v["created_tick"])
        if requests and teachable and a["energy"] >= 14:
            return act("offer_teaching", learner=requests[-1]["from"], artifact=teachable[0]["id"])
        return None

    # --- workshop-1 -----------------------------------------------------------------------------

    def _workshop(self, o: JSON, act, obtain) -> Action:
        a, tick = o["self"], o["tick"]
        arts = o["artifacts"]
        notes = a.get("dev_notes", {})
        own = sorted((v for v in arts.values() if v["creator"] == a["id"]), key=lambda v: v["created_tick"])
        held = [arts[k] for k in a["known"] if k in arts and arts[k].get("kind") == "workflow" and arts[k]["status"] in ("admitted", "superseded")]
        last = a.get("last_result") or {}
        if last.get("type") == "action_rejected" and last.get("kind") in ("use_artifact", "produce"):
            reason = last.get("reason", "")
            if "ore" in reason:
                return obtain("ore", 8)
            if "energy" in reason and a["inventory"]["food"]:
                return act("consume")
            if "food" in reason:
                return obtain("food", 4)
        pending = [v for v in own if v["status"] == "proposed" and v.get("kind") == "workflow"]
        if pending:
            return act("test_artifact", artifact=pending[0]["id"])
        current = min(held, key=lambda v: (notes.get(v["id"], float("inf")), -v["created_tick"])) if held else None
        current_dev = notes.get(current["id"]) if current else notes.get("baseline", float("inf"))
        latest = own[-1] if own else None
        if latest and latest["status"] == "dev-tested" and latest.get("dev_score") is not None and latest["dev_score"] < (current_dev if current_dev is not None else float("inf")):
            return act("submit_artifact", artifact=latest["id"])
        library = sorted((v for v in arts.values() if v["id"] not in a["known"] and v["status"] == "admitted" and v.get("kind") == "workflow"),
                         key=lambda v: -v["created_tick"])
        if library and not any(v["status"] == "admitted" for v in held):   # upgrade when the head was superseded
            return act("inspect_artifact", artifact=library[0]["id"])
        if a["role"] == "researcher" and o["rules"]["invention_open"] and SearchBudget().available(a, o["rules"]["search_budget"]) and a["energy"] >= 12:
            untested = [v for v in held if v["id"] not in notes]
            if untested:
                return act("test_artifact", artifact=untested[0]["id"])      # a development experiment on a held workflow
            base = current["program"] if current else ws.BASELINE
            others = [v for v in held if current is None or v["id"] != current["id"]]
            tried = {canonical(v["program"]) for v in own}
            options = [(label, prog) for label, prog in ws.neighbours(base, [v["program"] for v in others]) if canonical(prog) not in tried]
            options.sort(key=lambda lp: keyed(self.seed, "controller-search", a["id"], canonical(lp[1])))
            if options:
                label, program = options[0]
                sources = []
                if label.startswith("compose:"):
                    field = label.split(":")[1]
                    sources = [v["id"] for v in others if canonical(v["program"][field]) == canonical(program[field])][:1]
                params = {"program": program, "parent": current["id"] if current else None}
                if sources:
                    params["sources"] = sources
                return act("propose_artifact", **params)
        if tick % 43 == 17 and a["inventory"]["food"] >= 5 and o["neighbors"]:
            return act("transfer", target=o["neighbors"][0]["id"], resource="food", amount=1)
        if a["inventory"]["ore"] < (8 if held else 2):
            return obtain("ore", 8)                  # holders top up so the workflow can choose larger batches
        if held:
            best = min(held, key=lambda v: (notes.get(v["id"], float("inf")), v["status"] != "admitted", -v["created_tick"]))
            return act("use_artifact", artifact=best["id"])
        return act("produce")
