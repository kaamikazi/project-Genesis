from __future__ import annotations

from copy import deepcopy
from typing import Any

from .invention import PhaseEvaluator, conversion, execute, validate
from .models import Action, AgentController, JSON, RESOURCES, canonical, digest
from .world import LocalObservations, check_invariants, distance, phase_at


class Rejected(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Rejected(reason)


def integer(value: Any, name: str, low: int = 1, high: int = 100) -> int:
    require(type(value) is int and low <= value <= high, f"{name} must be an integer in {low}..{high}")
    return value


def spend_energy(agent: JSON, amount: int) -> None:
    require(agent["energy"] >= amount, "insufficient energy")
    agent["energy"] -= amount


def resource(value: Any) -> str:
    require(value in RESOURCES, "unknown resource")
    return value


PARAMS = {
    "wait": set(), "move": {"x", "y"}, "gather": {"site"}, "consume": set(),
    "transfer": {"target", "resource", "amount"},
    "offer_trade": {"target", "give", "give_amount", "want", "want_amount"},
    "accept_trade": {"offer"}, "send_message": {"target", "message"},
    "inspect_artifact": {"artifact"}, "propose_artifact": {"program", "parent"},
    "test_artifact": {"artifact"}, "use_artifact": {"artifact"}, "produce": set(),
}


class Rules:
    def apply(self, state: JSON, action: Action) -> JSON:
        """Apply on a disposable state. Caller publishes this copy only on success."""
        require(action.agent in state["agents"], "unknown agent")
        a = state["agents"][action.agent]
        p, kind = action.params, action.kind
        require(a["status"] == "active", "inactive agent")
        require(action.tick == state["tick"], "stale observation version")
        require(set(p) == PARAMS[kind], "incorrect action parameters")
        result: JSON = {"action": kind, "agent": a["id"]}
        if kind == "wait":
            return result
        if kind == "move":
            x = integer(p["x"], "x", 0, state["config"]["width"] - 1)
            y = integer(p["y"], "y", 0, state["config"]["height"] - 1)
            require(abs(x-a["x"]) + abs(y-a["y"]) == 1, "movement must be one adjacent tile")
            tile = state["terrain"][y][x]
            require(tile != "water", "water is not traversable")
            cost = 2 if tile in ("hill", "forest") else 1
            spend_energy(a, cost)
            result.update({"from": [a["x"], a["y"]], "to": [x, y], "energy": cost})
            a.update(x=x, y=y)
        elif kind == "gather":
            require(p["site"] in state["sites"], "unknown resource site")
            site = state["sites"][p["site"]]
            require(distance(a, site) <= 1, "site is out of reach")
            amount = min(4, site["stock"])
            require(amount > 0, "site depleted / contention")
            spend_energy(a, 1)
            site["stock"] -= amount
            a["inventory"][site["resource"]] += amount
            result.update(site=site["id"], resource=site["resource"], amount=amount)
        elif kind == "consume":
            require(a["inventory"]["food"] > 0, "no food to consume")
            a["inventory"]["food"] -= 1
            state["ledger"]["food"]["sink"] += 1
            gain = min(20, 40-a["energy"])
            a["energy"] += gain
            result.update(resource="food", amount=1, energy_restored=gain)
        elif kind in ("transfer", "offer_trade", "send_message"):
            target = state["agents"].get(p["target"]) or state["settlements"].get(p["target"])
            require(target is not None and target["id"] != a["id"], "invalid recipient")
            require(target.get("status", "active") == "active", "recipient is not active")
            require(distance(a, target) <= 2, "recipient is out of reach")
            if kind == "transfer":
                r, n = resource(p["resource"]), integer(p["amount"], "amount")
                require(a["inventory"][r] >= n, "insufficient inventory")
                spend_energy(a, 1)
                a["inventory"][r] -= n
                target["inventory"][r] += n
                state["metrics"]["transfers"] += 1
                result.update(target=target["id"], resource=r, amount=n)
            elif kind == "offer_trade":
                require(target["id"] in state["agents"] and target["status"] == "active", "trade needs an active agent")
                give, want = resource(p["give"]), resource(p["want"])
                gn, wn = integer(p["give_amount"], "give_amount"), integer(p["want_amount"], "want_amount")
                require(give != want and a["inventory"][give] >= gn, "invalid or unfunded offer")
                require(not any(o["maker"] == a["id"] for o in state["offers"].values()), "one pending offer per agent")
                spend_energy(a, 1)
                state["offers"][action.id] = {"id": action.id, "maker": a["id"], "target": target["id"],
                                             "give": give, "give_amount": gn, "want": want, "want_amount": wn,
                                             "expires": state["tick"] + 6}
                result.update(offer=action.id, target=target["id"])
            else:
                require(target["id"] in state["agents"], "message needs an agent")
                # Same finite channel in both experimental conditions; no procedure-bearing free text.
                require(p["message"] in ("greeting", "request_food"), "only greeting/request_food messages allowed")
                spend_energy(a, 1)
                message = {"from": a["id"], "claim": p["message"], "tick": state["tick"], "source": action.id}
                target["messages"] = (target["messages"] + [message])[-8:]
                target["beliefs"] = (target["beliefs"] + [{**message, "confidence": "unverified", "revision": 1}])[-8:]
                result.update(target=target["id"], message=p["message"], epistemic_type="statement")
            if target["id"] in state["agents"]:
                target["relationships"][a["id"]] = target["relationships"].get(a["id"], 0) + 1
        elif kind == "accept_trade":
            offer = state["offers"].get(p["offer"])
            require(offer is not None and offer["target"] == a["id"], "offer unavailable")
            maker = state["agents"][offer["maker"]]
            require(offer["expires"] > state["tick"] and maker["status"] == "active", "offer expired/inactive")
            require(distance(a, maker) <= 2, "trading partner moved away")
            give, want, gn, wn = offer["give"], offer["want"], offer["give_amount"], offer["want_amount"]
            require(maker["inventory"][give] >= gn and a["inventory"][want] >= wn, "trade no longer funded")
            spend_energy(a, 1)
            maker["inventory"][give] -= gn
            a["inventory"][give] += gn
            a["inventory"][want] -= wn
            maker["inventory"][want] += wn
            del state["offers"][offer["id"]]
            result.update(offer=offer["id"], maker=maker["id"], give=give, give_amount=gn, want=want, want_amount=wn)
        elif kind == "propose_artifact":
            require(a["search_count"] < state["config"]["search_budget"], "search budget exhausted")
            validate(p["program"])
            require(p["parent"] is None or p["parent"] in a["known"], "parent artifact is not learned")
            parent = state["artifacts"].get(p["parent"]) if p["parent"] else None
            require(parent is None or parent["status"] == "verified", "only a current verified artifact can be revised")
            spend_energy(a, 1)
            content = {"program": p["program"], "creator": a["id"], "parent": p["parent"], "language": 1}
            aid = digest(content)
            require(aid not in state["artifacts"], "duplicate immutable artifact")
            state["artifacts"][aid] = {"id": aid, "content": deepcopy(content), "creator": a["id"],
                                       "parent": p["parent"], "generation": parent["generation"] + 1 if parent else 0,
                                       "superseded_by": None, "created_tick": state["tick"] + 1,
                                       "creation_event": action.id, "home": a["home"], "status": "proposed",
                                       "capabilities": ["converter"], "inputs": {"ore": 2},
                                       "claim": "revision may use less energy than its parent" if parent else "candidate may reduce conversion energy",
                                       "evaluation": None,
                                       "transmissions": [], "uses": [], "adopters": [],
                                       "access": "settlement library" if state["config"]["sharing"] else "creator only"}
            a["search_count"] += 1
            state["metrics"]["search_proposals"] += 1
            result.update(artifact=aid, epistemic_type="attempted_invention")
        elif kind in ("inspect_artifact", "test_artifact", "use_artifact"):
            artifact = state["artifacts"].get(p["artifact"])
            require(artifact is not None, "artifact unavailable")
            require(digest(artifact["content"]) == artifact["id"], "artifact content hash mismatch")
            aid = artifact["id"]
            own = artifact["creator"] == a["id"]
            require(own or (state["config"]["sharing"] and artifact["home"] == a["home"]), "artifact access denied")
            require("converter" in a["capabilities"], "converter capability required")
            if kind == "test_artifact":
                require(own and artifact["status"] == "proposed", "only creator can test an untested proposal")
                spend_energy(a, 3)
                parent = state["artifacts"][artifact["parent"]] if artifact["parent"] else None
                evaluation = PhaseEvaluator().evaluate(artifact["content"]["program"], parent["content"]["program"] if parent else None)
                if parent and parent["status"] != "verified" and evaluation["status"] == "verified":
                    evaluation.update(status="rejected", failures=[f'parent already superseded by {parent["superseded_by"]}'])
                artifact.update(status=evaluation["status"], evaluation=evaluation)
                state["metrics"]["evaluation_cases"] += evaluation["case_count"]
                if evaluation["status"] == "verified":
                    a["known"].append(aid)
                    if parent:
                        parent.update(status="superseded", superseded_by=aid)
                        state["metrics"]["revisions_verified"] += 1
                        result.update(supersedes=parent["id"])
                result.update(artifact=aid, status=artifact["status"], energy=evaluation["energy"], baseline_energy=evaluation["baseline_energy"], failures=evaluation["failures"], epistemic_type="verified_artifact" if artifact["status"] == "verified" else "observed_outcome")
            elif kind == "inspect_artifact":
                require(artifact["status"] == "verified" and aid not in a["known"], "artifact must be verified and not already learned")
                require(distance(a, state["settlements"][a["home"]]) <= 2, "settlement library out of reach")
                spend_energy(a, 2)
                a["seen"].append(aid)
                a["known"].append(aid)
                path = {"from": artifact["creator"], "to": a["id"], "tick": state["tick"] + 1,
                        "via": "settlement library", "event": action.id, "operational_definition": "copied validated AST; competence requires measured use"}
                artifact["transmissions"].append(path)
                if state["agents"][artifact["creator"]]["status"] != "active":
                    state["metrics"]["learned_after_creator_removal"] += 1
                result.update(artifact=aid, transmission=path, epistemic_type="knowledge_transfer")
            else:
                require(artifact["status"] in ("verified", "superseded") and aid in a["known"], "artifact must be verified and learned")
                phase = phase_at(state, a)
                mode, steps = execute(artifact["content"]["program"], phase, a["capabilities"])
                result.update(self._produce(state, a, phase, mode))
                evidence = {"agent": a["id"], "tick": state["tick"] + 1, "event": action.id,
                            "phase": phase, "mode": mode, "energy": result["energy"],
                            "baseline_energy": conversion(phase, 0)["energy"], "steps": steps}
                artifact["uses"] = (artifact["uses"] + [evidence])[-64:]
                if aid not in a["used"]:
                    a["used"].append(aid)
                if not own and state["agents"][artifact["creator"]]["status"] != "active":
                    state["metrics"]["uses_after_creator_removal"] += 1
                reproduced = not own and evidence["energy"] < evidence["baseline_energy"] and a["id"] not in artifact["adopters"]
                if reproduced:
                    artifact["adopters"].append(a["id"])
                    state["metrics"]["adoptions"] += 1
                result.update(artifact=aid, evidence=evidence, independent_adoption=reproduced, epistemic_type="observed_outcome")
        elif kind == "produce":
            require("converter" in a["capabilities"], "converter capability required")
            result.update(self._produce(state, a, phase_at(state, a), 0))
        return result

    def _produce(self, state: JSON, a: JSON, phase: int, mode: int) -> JSON:
        outcome = conversion(phase, mode)
        require(a["inventory"]["ore"] >= outcome["ore"], "production requires 2 ore")
        spend_energy(a, outcome["energy"])
        a["inventory"]["ore"] -= outcome["ore"]
        a["inventory"]["alloy"] += outcome["alloy"]
        state["ledger"]["ore"]["sink"] += outcome["ore"]
        state["ledger"]["alloy"]["source"] += outcome["alloy"]
        state["metrics"]["produced"] += 1
        state["metrics"]["production_energy"] += outcome["energy"]
        if state["lifecycle"]["removal"] is not None:
            state["metrics"]["produced_after_removal"] += 1
            state["metrics"]["production_energy_after_removal"] += outcome["energy"]
        return {"phase": phase, "mode": mode, **outcome}


def scheduled_removal(state: JSON) -> JSON | None:
    """Scenario-scheduled retirement at the start of `removal_tick`. Inventory goes to settlement
    storage so the comparison isolates the lost worker and their knowledge, not lost resources."""
    c, agents = state["config"], state["agents"]
    if c["removal"] == "none" or state["tick"] != c["removal_tick"] or state["lifecycle"]["removal"] is not None:
        return None
    creators = sorted({x["creator"] for x in state["artifacts"].values()
                       if x["status"] == "verified" and agents[x["creator"]]["status"] == "active"})
    chosen: list[str] = []
    if c["removal"] == "creators":
        chosen = list(creators)
    else:
        for cid in creators:
            pool = sorted(aid for aid, x in agents.items() if x["home"] == agents[cid]["home"]
                          and x["status"] == "active" and aid not in creators and aid not in chosen)
            if pool:
                chosen.append(pool[0])
    moved = []
    for aid in chosen:
        a = agents[aid]
        store = state["settlements"][a["home"]]["inventory"]
        for r in RESOURCES:
            store[r] += a["inventory"][r]
        moved.append({"agent": aid, "to": a["home"], "inventory": dict(a["inventory"])})
        a["inventory"] = {r: 0 for r in RESOURCES}
        a["status"] = "retired"
    record = {"tick": state["tick"], "policy": c["removal"], "verified_creators": creators, "removed": chosen,
              "inventory_moved": moved, "note": "scheduled lifecycle removal, not death; no verified creators existed"
              if not creators else "scheduled lifecycle removal, not death"}
    state["lifecycle"]["removal"] = record
    return {"tick": state["tick"], "type": "lifecycle_removal", **{k: v for k, v in record.items() if k != "tick"}}


def attempt(state: JSON, action: Action) -> tuple[JSON, JSON]:
    candidate = deepcopy(state)
    try:
        result = Rules().apply(candidate, action)
        check_invariants(candidate)
        return candidate, {"accepted": True, "result": result}
    except (Rejected, ValueError, KeyError, TypeError, RecursionError) as exc:
        return state, {"accepted": False, "reason": str(exc)[:240]}


def advance(state: JSON, controller: AgentController, overrides: dict[str, Action] | None = None, prior_ids: set[str] | None = None) -> tuple[JSON, list[JSON], list[JSON]]:
    require(state["tick"] < state["config"]["max_ticks"], "maximum ticks reached")
    observations = LocalObservations()
    proposals: list[Action] = []
    decisions: list[JSON] = []
    events: list[JSON] = []
    overrides = overrides or {}
    require(all(key in state["agents"] and action.agent == key for key, action in overrides.items()), "invalid override identity")
    next_state = deepcopy(state)
    for aid, agent in sorted(state["agents"].items()):
        if agent["status"] != "active":
            continue
        obs = observations.build(state, aid)
        try:
            action = overrides[aid] if aid in overrides else controller.propose(obs)
            action = Action.model_validate(action.model_dump())
            require(action.agent == aid, "controller identity mismatch")
            mode = "submitted" if aid in overrides else "bounded-search" if agent["role"] == "researcher" else "deterministic-baseline"
        except Exception as exc:
            # An exception is an audited failure; fallback is never labeled a successful decision.
            events.append({"tick": state["tick"]+1, "type": "controller_failure", "agent": aid, "reason": str(exc)[:240]})
            next_state["metrics"]["controller_failures"] += 1
            action = Action(id=f'{state["tick"]}:{aid}:fallback', agent=aid, tick=state["tick"], kind="wait")
            mode = "explicit-failure-fallback"
        proposals.append(action)
        decisions.append({"action": action.model_dump(), "observation_hash": digest(obs), "controller": mode})
    if proposals:
        offset = state["tick"] % len(proposals)
        proposals = proposals[offset:] + proposals[:offset]
    seen = set(prior_ids or ())
    for action in proposals:
        if action.id in seen:
            outcome = {"accepted": False, "reason": "duplicate action id"}
        else:
            next_state, outcome = attempt(next_state, action)
        seen.add(action.id)
        event = {"id": action.id, "tick": state["tick"] + 1, "agent": action.agent,
                 "type": "action_accepted" if outcome["accepted"] else "action_rejected",
                 "kind": action.kind, **outcome}
        events.append(event)
        next_state["metrics"]["accepted" if outcome["accepted"] else "rejected"] += 1
        a = next_state["agents"][action.agent]
        a["last_result"] = event
        a["memories"] = (a["memories"] + [event])[-16:]
    next_state["tick"] += 1
    for aid, a in next_state["agents"].items():
        if a["status"] == "active":
            a["energy"] = max(0, a["energy"]-1)
            if a["energy"] == 0 and a["inventory"]["food"] == 0:
                a["status"] = "inactive"
                events.append({"tick": next_state["tick"], "type": "agent_inactive", "agent": aid, "reason": "exhausted without food; inventory retained"})
    removal = scheduled_removal(next_state)
    if removal:
        events.append(removal)
    replenished = []
    for sid, site in next_state["sites"].items():
        if site["resource"] == "food":
            n = min(2, site["capacity"]-site["stock"])
            site["stock"] += n
            next_state["ledger"]["food"]["source"] += n
            if n:
                replenished.append({"site": sid, "amount": n})
    expired = []
    for oid, offer in list(next_state["offers"].items()):
        maker = next_state["agents"][offer["maker"]]
        target = next_state["agents"][offer["target"]]
        if offer["expires"] <= next_state["tick"] or maker["inventory"][offer["give"]] < offer["give_amount"] or maker["status"] != "active" or target["status"] != "active" or distance(maker, target) > 2:
            expired.append(oid)
            del next_state["offers"][oid]
    events.append({"tick": next_state["tick"], "type": "environment", "food_sources": replenished,
                   "fatigue_per_active_agent": 1, "expired_offers": expired})
    check_invariants(next_state)
    return next_state, events, decisions
