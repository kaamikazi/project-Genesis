from __future__ import annotations

from copy import deepcopy
from typing import Any

from .invention import PhaseEvaluator, conversion, execute, validate
from .models import Action, AgentController, JSON, RESOURCES, canonical, digest
from . import workshop as ws
from .world import (ACTIVE_STAGES, NAMES, REACH, USABLE, LocalObservations, check_invariants, distance, humidity_at,
                    library_access, new_agent, phase_at)


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
    "deposit": {"settlement", "resource", "amount"}, "withdraw": {"settlement", "resource", "amount"},
    "submit_artifact": {"artifact"}, "offer_teaching": {"learner", "artifact"}, "accept_teaching": {"session"},
    "teach_step": {"session"}, "learn_step": {"session"}, "practice_step": {"session"}, "abandon_session": {"session"},
}
OPTIONAL_PARAMS = {"propose_artifact": {"sources"}}   # workshop composition names the other held artifacts it draws on
INSTRUCTION_WORK, PRACTICE_RUNS, OFFER_TICKS, STALL_TICKS = 3, 2, 6, 8
TEACH_COST, LEARN_COST, SUBMIT_COST = 2, 1, 2


def active_session(state: JSON, agent_id: str) -> JSON | None:
    for session in state.get("sessions", {}).values():
        if session["stage"] in ACTIVE_STAGES and agent_id in (session["teacher"], session["learner"]):
            return session
    return None


def held_components(state: JSON, agent: JSON) -> dict[str, JSON]:
    return {aid: state["artifacts"][aid]["content"]["program"] for aid in agent["known"]
            if aid in state["artifacts"] and state["artifacts"][aid].get("kind") == "component"}


def measures_of(state: JSON, agent: JSON) -> dict[str, int]:
    return {"phase": phase_at(state, agent), "humidity": humidity_at(state, agent),
            "ore": agent["inventory"]["ore"], "energy": agent["energy"]}


def baseline_cost_per_alloy(params: JSON, measures: dict[str, int]) -> float | None:
    decision, _ = ws.execute(ws.BASELINE, measures, {})
    out = ws.outcome(params, measures, decision)
    return round(out["cost"] / out["alloy"], 6) if out["feasible"] else None


class Rules:
    def apply(self, state: JSON, action: Action) -> JSON:
        """Apply on a disposable state. Caller publishes this copy only on success."""
        require(action.agent in state["agents"], "unknown agent")
        a = state["agents"][action.agent]
        p, kind = action.params, action.kind
        require(a["status"] == "active", f'agent is not active ({a["status"]})')
        require(action.tick == state["tick"], "stale observation version")
        require(set(p) == PARAMS[kind] or set(p) == PARAMS[kind] | OPTIONAL_PARAMS.get(kind, {"-"}), "incorrect action parameters")
        if a.get("busy_until", 0) > state["tick"]:
            require(kind in ("wait", "consume"), f'agent is busy with a batch until tick {a["busy_until"]}')
        session = active_session(state, a["id"])
        if session and session["stage"] == "instruction":
            own_step = "teach_step" if session["teacher"] == a["id"] else "learn_step"
            require(kind in (own_step, "consume", "abandon_session", "wait"), f'agent is reserved by teaching session {session["id"]}')
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
                vocabulary = ("greeting", "request_food") + (("request_lesson",) if state["config"].get("teaching") else ())
                require(p["message"] in vocabulary, f"message must be one of {vocabulary}")
                spend_energy(a, 1)
                message = {"from": a["id"], "claim": p["message"], "tick": state["tick"], "source": action.id}
                target["messages"] = (target["messages"] + [message])[-8:]
                target["beliefs"] = (target["beliefs"] + [{**message, "confidence": "unverified", "revision": 1}])[-8:]
                result.update(target=target["id"], message=p["message"], epistemic_type="statement")
            if target["id"] in state["agents"]:
                target["relationships"][a["id"]] = target["relationships"].get(a["id"], 0) + 1
        elif kind in ("deposit", "withdraw"):
            settlement = state["settlements"].get(p["settlement"])
            require(settlement is not None, "unknown settlement")
            require(settlement["id"] == a["home"], "not a member of this settlement")
            require(distance(a, settlement) <= REACH, "settlement storage out of reach")
            r, n = resource(p["resource"]), integer(p["amount"], "amount")
            source, sink = (a["inventory"], settlement["inventory"]) if kind == "deposit" else (settlement["inventory"], a["inventory"])
            require(source[r] >= n, "insufficient inventory" if kind == "deposit" else "insufficient settlement stock")
            spend_energy(a, 1)
            source[r] -= n
            sink[r] += n
            settlement["flows"][kind][r] += n
            result.update(settlement=settlement["id"], resource=r, amount=n)
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
            require(state["config"]["invention"] == "open", "invention is frozen by the scenario")
            require(a["search_count"] < state["config"]["search_budget"], "search budget exhausted")
            if state["config"].get("task") == "workshop-1":
                return self._propose_workshop(state, a, action, result)
            require("sources" not in p, "sources are only used by workshop composition")
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
                                       "transmissions": [], "uses": [], "first_uses": {}, "adopters": [],
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
            # Per-kind access: test needs authorship, inspect needs library access, use needs the program in hand.
            if kind == "inspect_artifact":
                require(own or "library" in a["capabilities"] and artifact["home"] == a["home"], "artifact access denied")
            elif kind == "use_artifact":
                require(aid in a["known"], "artifact access denied")
            require("converter" in a["capabilities"], "converter capability required")
            if artifact.get("task") == "workshop-1" and kind != "inspect_artifact":
                return self._workshop_artifact(state, a, artifact, action, result)
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
                # The proposer learns only aggregate feedback; case-level evidence stays on the artifact.
                result.update(artifact=aid, **PhaseEvaluator.agent_feedback(evaluation), epistemic_type="verified_artifact" if artifact["status"] == "verified" else "observed_outcome")
            elif kind == "inspect_artifact":
                require(library_access(a, artifact, state["config"]) and aid not in a["known"], "artifact must be current, in your library and not already learned")
                require(distance(a, state["settlements"][a["home"]]) <= REACH, "settlement library out of reach")
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
                if a["id"] not in artifact["first_uses"]:
                    artifact["first_uses"][a["id"]] = evidence
                if not own and state["agents"][artifact["creator"]]["status"] != "active":
                    state["metrics"]["uses_after_creator_removal"] += 1
                first_independent = self._first_independent_use(state, a, aid, evidence)
                if first_independent:
                    result.update(first_independent_use=first_independent)
                reproduced = not own and evidence["energy"] < evidence["baseline_energy"] and a["id"] not in artifact["adopters"]
                if reproduced:
                    artifact["adopters"].append(a["id"])
                    state["metrics"]["adoptions"] += 1
                result.update(artifact=aid, evidence=evidence, independent_adoption=reproduced, epistemic_type="observed_outcome")
        elif kind == "produce":
            require("converter" in a["capabilities"], "converter capability required")
            if state["config"].get("task") == "workshop-1":
                result.update(self._workflow(state, a, ws.BASELINE, {}), procedure="baseline workflow")
            else:
                result.update(self._produce(state, a, phase_at(state, a), 0))
        elif kind == "submit_artifact":
            artifact = state["artifacts"].get(p["artifact"])
            require(artifact is not None and artifact.get("task") == "workshop-1", "submission applies to workshop artifacts only")
            return self._workshop_artifact(state, a, artifact, action, result)
        elif kind in ("offer_teaching", "accept_teaching", "teach_step", "learn_step", "practice_step", "abandon_session"):
            require(state["config"].get("teaching"), "teaching is not enabled in this scenario")
            self._teaching(state, a, action, result)
        return result

    # --- workshop-1 -----------------------------------------------------------------------------

    def _propose_workshop(self, state: JSON, a: JSON, action: Action, result: JSON) -> JSON:
        p = action.params
        program = p["program"]
        ws.validate(program)
        sources = p.get("sources") or []
        require(isinstance(sources, list) and len(sources) <= 3 and all(isinstance(x, str) for x in sources), "sources must be a short list of ids")
        require(p["parent"] is None or p["parent"] in a["known"], "parent artifact is not held")
        parent = state["artifacts"].get(p["parent"]) if p["parent"] else None
        require(parent is None or (parent.get("task") == "workshop-1" and parent["status"] in ("admitted",)), "only a current admitted workflow can be revised")
        require(all(x in a["known"] for x in sources), "composition sources must be held")
        require(all(c in a["known"] for c in ws.calls(program)), "called components must be held")
        spend_energy(a, 1)
        kind = ws.kind_of(program)
        content = {"program": program, "creator": a["id"], "parent": p["parent"], "sources": sorted(sources), "language": "workshop-1"}
        aid = digest(content)
        require(aid not in state["artifacts"], "duplicate immutable artifact")
        state["artifacts"][aid] = {
            "id": aid, "content": deepcopy(content), "task": "workshop-1", "kind": kind, "creator": a["id"], "cohort": a.get("cohort", 0),
            "parent": p["parent"], "sources": sorted(sources), "generation": parent["generation"] + 1 if parent else 0,
            "origin": "composition" if sources else "search-revision" if parent else "search-original",
            "superseded_by": None, "created_tick": state["tick"] + 1, "creation_event": action.id, "home": a["home"],
            "status": "component" if kind == "component" else "proposed", "capabilities": ["converter"],
            "inputs": "local phase and humidity, own ore and energy", "assumptions": "workshop-1 rules; hidden world parameters unknown to the creator",
            "claim": "may lower cost per alloy versus its parent" if parent else "may lower cost per alloy versus the baseline workflow",
            "development": None, "validation": None, "evaluation": None,
            "transmissions": [], "uses": [], "first_uses": {}, "adopters": [],
            "access": "settlement library" if state["config"]["sharing"] else "creator only"}
        if kind == "component":
            a["known"].append(aid)
        a["search_count"] += 1
        state["metrics"]["search_proposals"] += 1
        result.update(artifact=aid, origin=state["artifacts"][aid]["origin"], parent=p["parent"], sources=sorted(sources),
                      generation=state["artifacts"][aid]["generation"], cohort=a.get("cohort", 0), kind=kind, epistemic_type="attempted_invention")
        return result

    def _workshop_artifact(self, state: JSON, a: JSON, artifact: JSON, action: Action, result: JSON) -> JSON:
        kind, aid = action.kind, artifact["id"]
        params = ws.world_params(state["config"]["seed"])
        own = artifact["creator"] == a["id"]
        program = artifact["content"]["program"]
        evaluator = ws.WorkshopEvaluator()
        if kind == "test_artifact":
            # Development role: a permitted experiment on a workflow the agent proposed or holds.
            require(artifact["kind"] == "workflow", "only workflows can be tested")
            require((own and artifact["status"] == "proposed") or aid in a["known"], "test needs your own proposal or a workflow you hold")
            spend_energy(a, 3)
            dev = evaluator.development(program, params, held_components(state, a))
            if own and artifact["status"] == "proposed":
                artifact.update(status="dev-tested", development=dev)
            a["dev_notes"] = {**a.get("dev_notes", {}), aid: dev["score"], "baseline": dev["baseline_score"]}
            state["metrics"]["evaluation_cases"] += len(dev["cases"])
            result.update(artifact=aid, role="development", dev_score=dev["score"], baseline_dev_score=dev["baseline_score"],
                          cases=dev["cases"], status=artifact["status"], epistemic_type="observed_outcome")
        elif kind == "submit_artifact":
            # Validation role: admission decision only; the score stays on the artifact record (observer-only).
            require(own and artifact["status"] == "dev-tested", "only your own development-tested workflow can be submitted")
            parent = state["artifacts"].get(artifact["parent"]) if artifact["parent"] else None
            require(parent is None or parent["status"] == "admitted", "parent is no longer the current admitted workflow")
            spend_energy(a, SUBMIT_COST)
            held = held_components(state, a)
            val = evaluator.validation(program, params, held, parent["content"]["program"] if parent else None, held)
            artifact.update(status="admitted" if val["admitted"] else "not-admitted", validation=val)
            state["metrics"]["evaluation_cases"] += 24 * (2 if parent else 1)
            if val["admitted"]:
                a["known"].append(aid)
                if parent:
                    parent.update(status="superseded", superseded_by=aid)
                    state["metrics"]["revisions_verified"] += 1
                    result.update(supersedes=parent["id"])
            result.update(artifact=aid, role="validation", admitted=val["admitted"], status=artifact["status"],
                          feedback_policy="admitted/not admitted only", epistemic_type="verified_artifact" if val["admitted"] else "observed_outcome")
        else:  # use_artifact
            require(artifact["kind"] == "workflow" and artifact["status"] in ("admitted", "superseded") and aid in a["known"],
                    "artifact must be an admitted workflow you hold")
            out = self._workflow(state, a, program, held_components(state, a))
            evidence = {"agent": a["id"], "tick": state["tick"] + 1, "event": action.id, "measures": out["measures"],
                        "decision": out["decision"], "alloy": out["alloy"], "energy": out["energy"],
                        "cost_per_alloy": out["cost_per_alloy"], "baseline_cost_per_alloy": out["baseline_cost_per_alloy"]}
            artifact["uses"] = (artifact["uses"] + [evidence])[-64:]
            if aid not in a["used"]:
                a["used"].append(aid)
            if a["id"] not in artifact["first_uses"]:
                artifact["first_uses"][a["id"]] = evidence
            saving = out["baseline_cost_per_alloy"] is None or out["cost_per_alloy"] < out["baseline_cost_per_alloy"]
            reproduced = not own and saving and a["id"] not in artifact["adopters"]
            if reproduced:
                artifact["adopters"].append(a["id"])
                state["metrics"]["adoptions"] += 1
            first_independent = self._first_independent_use(state, a, aid, evidence)
            if first_independent:
                result.update(first_independent_use=first_independent)
            result.update(out, artifact=aid, evidence=evidence, saving=saving, independent_adoption=reproduced, epistemic_type="observed_outcome")
        return result

    def _workflow(self, state: JSON, a: JSON, program: JSON, held: dict[str, JSON]) -> JSON:
        params = ws.world_params(state["config"]["seed"])
        measures = measures_of(state, a)
        decision, steps = ws.execute(program, measures, held)
        out = ws.outcome(params, measures, decision)
        require(out["feasible"], out.get("reason", "infeasible batch"))
        require(a["inventory"]["food"] >= out["food"], "flux needs 1 food")
        spend_energy(a, out["energy"])
        a["inventory"]["ore"] -= out["ore"]
        a["inventory"]["food"] -= out["food"]
        a["inventory"]["alloy"] += out["alloy"]
        state["ledger"]["ore"]["sink"] += out["ore"]
        state["ledger"]["food"]["sink"] += out["food"]
        state["ledger"]["alloy"]["source"] += out["alloy"]
        state["metrics"]["produced"] += out["alloy"]
        state["metrics"]["production_energy"] += out["energy"]
        if state["lifecycle"]["removal"] is not None:
            state["metrics"]["produced_after_removal"] += out["alloy"]
            state["metrics"]["production_energy_after_removal"] += out["energy"]
        a["busy_until"] = state["tick"] + out["alloy"]      # a batch of b occupies the agent for b ticks in total
        return {"measures": measures, "decision": decision, "steps": steps, "ore": out["ore"], "alloy": out["alloy"],
                "energy": out["energy"], "food": out["food"], "ore_wasted": out["ore_wasted"], "busy_ticks": out["busy_ticks"],
                "cost": out["cost"], "cost_per_alloy": round(out["cost"] / out["alloy"], 6),
                "baseline_cost_per_alloy": baseline_cost_per_alloy(params, measures)}

    def _first_independent_use(self, state: JSON, a: JSON, aid: str, evidence: JSON) -> str | None:
        for session in state.get("sessions", {}).values():
            if session["learner"] == a["id"] and session["artifact"] == aid and session["stage"] == "acquired" and session["first_independent_use"] is None:
                session["first_independent_use"] = {k: evidence.get(k) for k in ("tick", "event", "cost_per_alloy", "baseline_cost_per_alloy", "energy", "baseline_energy")}
                return session["id"]
        return None

    # --- teaching sessions (teaching-1) -----------------------------------------------------------

    def _teaching(self, state: JSON, a: JSON, action: Action, result: JSON) -> None:
        p, kind, tick = action.params, action.kind, state["tick"]
        sessions = state["sessions"]
        if kind == "offer_teaching":
            learner = state["agents"].get(p["learner"])
            artifact = state["artifacts"].get(p["artifact"])
            require(learner is not None and learner["id"] != a["id"] and learner["status"] == "active", "learner must be another active agent")
            require(artifact is not None and p["artifact"] in a["known"], "teacher must already hold the artifact")
            require(artifact["status"] in USABLE + ("superseded", "component"), "only usable procedures can be taught")
            require(learner["home"] == a["home"], "teacher and learner must belong to the same settlement")
            require(distance(a, learner) <= REACH, "learner is out of reach")
            require(p["artifact"] not in learner["known"], "learner already holds this artifact")
            require(active_session(state, a["id"]) is None and active_session(state, learner["id"]) is None, "a participant is already in a session")
            spend_energy(a, 1)
            program = artifact["content"]["program"]
            sessions[action.id] = {
                "id": action.id, "contract": "teaching-1", "teacher": a["id"], "learner": learner["id"], "artifact": artifact["id"],
                "task": artifact.get("task", "phase-1"), "stage": "offered", "offered_tick": tick + 1, "expires": tick + 1 + OFFER_TICKS,
                "required_work": INSTRUCTION_WORK, "teacher_work": 0, "learner_work": 0, "practice_required": PRACTICE_RUNS,
                "practice": [], "prerequisites": ws.calls(program) if ws.is_workshop(program) else [],
                "costs": {"teacher_energy": 1, "learner_energy": 0, "teacher_ticks": 1, "learner_ticks": 0},
                "last_progress": tick + 1, "accepted_tick": None, "instruction_done_tick": None, "assessment": None,
                "acquired_tick": None, "ended_tick": None, "reason": None, "first_independent_use": None, "requirements":
                "co-located (<=1 tile) for every instruction step; same settlement; learner holds all prerequisites"}
            result.update(session=action.id, learner=learner["id"], teacher=a["id"], artifact=artifact["id"], stage="offered")
            return
        session = sessions.get(p["session"])
        require(session is not None, "unknown session")
        role = "teacher" if session["teacher"] == a["id"] else "learner" if session["learner"] == a["id"] else None
        require(role is not None, "not a participant in this session")
        other = state["agents"][session["learner"] if role == "teacher" else session["teacher"]]
        result.update(session=session["id"], role=role)
        if kind == "abandon_session":
            require(session["stage"] in ACTIVE_STAGES, "session already ended")
            self._end_session(state, session, "interrupted", f"abandoned by {a['id']}", tick + 1)
            result.update(stage=session["stage"], reason=session["reason"])
        elif kind == "accept_teaching":
            require(role == "learner" and session["stage"] == "offered", "only the learner can accept an open offer")
            require(tick < session["expires"], "offer expired")
            require(other["status"] == "active" and session["artifact"] in other["known"], "teacher no longer able to teach this")
            require(distance(a, other) <= 1, "participants must be co-located (<=1 tile) to begin")
            missing = [c for c in session["prerequisites"] if c not in a["known"]]
            session["accepted_tick"] = tick + 1
            if missing:
                # A real failure mode: the lesson cannot proceed without the components the program calls.
                self._end_session(state, session, "failed", f"missing prerequisite components: {[m[:8] for m in missing]}", tick + 1)
            else:
                session.update(stage="instruction", last_progress=tick + 1)
            result.update(stage=session["stage"], reason=session["reason"])
        elif kind in ("teach_step", "learn_step"):
            require(session["stage"] == "instruction", "session is not in instruction")
            require((kind == "teach_step") == (role == "teacher"), "wrong step for this role")
            require(distance(a, other) <= 1, "participants must be co-located (<=1 tile)")
            work_key = f"{role}_work"
            require(session[work_key] < session["required_work"], "this participant's instruction work is complete")
            cost = TEACH_COST if role == "teacher" else LEARN_COST
            spend_energy(a, cost)
            session[work_key] += 1
            session["costs"][f"{role}_energy"] += cost
            session["costs"][f"{role}_ticks"] += 1
            session["last_progress"] = tick + 1
            if session["teacher_work"] >= session["required_work"] and session["learner_work"] >= session["required_work"]:
                session.update(stage="practice", instruction_done_tick=tick + 1)
            result.update(stage=session["stage"], work=session[work_key], required=session["required_work"])
        else:  # practice_step
            require(role == "learner" and session["stage"] == "practice", "only the learner practises, after instruction")
            artifact = state["artifacts"][session["artifact"]]
            program = artifact["content"]["program"]
            energy_before = a["energy"]
            if artifact.get("task") == "workshop-1":
                out = self._workflow(state, a, program, held_components(state, a))
                passed = out["baseline_cost_per_alloy"] is None or out["cost_per_alloy"] <= out["baseline_cost_per_alloy"]
                record = {"tick": tick + 1, "event": action.id, "measures": out["measures"], "decision": out["decision"],
                          "cost_per_alloy": out["cost_per_alloy"], "baseline_cost_per_alloy": out["baseline_cost_per_alloy"], "passed": passed}
                result.update(out)
            else:
                phase = phase_at(state, a)
                mode, _ = execute(program, phase, a["capabilities"])
                out = self._produce(state, a, phase, mode)
                passed = out["energy"] <= conversion(phase, 0)["energy"]
                record = {"tick": tick + 1, "event": action.id, "phase": phase, "mode": mode, "energy": out["energy"],
                          "baseline_energy": conversion(phase, 0)["energy"], "passed": passed}
                result.update(out)
            session["practice"].append(record)
            session["costs"]["learner_energy"] += energy_before - a["energy"]
            session["costs"]["learner_ticks"] += 1
            session["last_progress"] = tick + 1
            result.update(practice=record)
            if len(session["practice"]) >= session["practice_required"]:
                ok = all(r["passed"] for r in session["practice"])
                session["assessment"] = {"tick": tick + 1, "passed": ok, "criterion":
                                         f"{session['practice_required']} feasible practice runs, each no costlier per alloy than the baseline under the same conditions"}
                if ok:
                    a["known"].append(artifact["id"])
                    a["seen"].append(artifact["id"])
                    path = {"from": session["teacher"], "to": a["id"], "tick": tick + 1, "via": "teaching session", "session": session["id"],
                            "event": action.id, "operational_definition": "acquired after passing the practice assessment"}
                    artifact["transmissions"].append(path)
                    session["acquired_tick"] = tick + 1
                    self._end_session(state, session, "acquired", None, tick + 1)
                else:
                    self._end_session(state, session, "failed", "practice outcome costlier than the baseline", tick + 1)
                result.update(assessment=session["assessment"], stage=session["stage"])

    @staticmethod
    def _end_session(state: JSON, session: JSON, stage: str, reason: str | None, tick: int) -> None:
        session.update(stage=stage, reason=reason, ended_tick=tick)

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
    """Lifecycle transition at the boundary where tick becomes `removal_tick` (after action resolution and fatigue).
    Retirees stop acting immediately; pending offers involving them expire in the same environment step.
    Physical holdings move to settlement storage (withdrawable by members). With succession, each retiree
    is replaced by a fresh agent with a new identity and only the declared inheritance package."""
    c, agents = state["config"], state["agents"]
    if c["removal"] == "none" or state["tick"] != c["removal_tick"] or state["lifecycle"]["removal"] is not None:
        return None
    creators = sorted({x["creator"] for x in state["artifacts"].values()
                       if x["status"] in ("verified", "admitted") and agents[x["creator"]]["status"] == "active"})
    chosen: list[str] = []
    if c["removal"] == "creators":
        chosen = list(creators)
    else:
        for cid in creators:
            pool = sorted(aid for aid, x in agents.items() if x["home"] == agents[cid]["home"]
                          and x["status"] == "active" and aid not in creators and aid not in chosen)
            if pool:
                chosen.append(pool[0])
    moved, successors = [], []
    for aid in chosen:
        a = agents[aid]
        settlement = state["settlements"][a["home"]]
        for r in RESOURCES:
            settlement["inventory"][r] += a["inventory"][r]
            settlement["flows"]["retirement"][r] += a["inventory"][r]
        moved.append({"agent": aid, "to": a["home"], "inventory": dict(a["inventory"])})
        a.update(inventory={r: 0 for r in RESOURCES}, status="retired", retired_tick=state["tick"])
    if c["succession"] == "fresh":
        for aid in chosen:
            old = agents[aid]
            index = len(agents)
            sid = f"a{index:02d}"
            home = state["settlements"][old["home"]]
            heir = new_agent(sid, NAMES[index % len(NAMES)], home, 0, state["tick"], c["successor_role"], c["successor_access"] == "library")
            package = []
            if c["successor_access"] == "direct":
                # Labelled debugging control: the current verified procedures of the settlement are handed over.
                package = sorted(x["id"] for x in state["artifacts"].values() if x["status"] in ("verified", "admitted") and x["home"] == home["id"])
                for art_id in package:
                    heir["known"].append(art_id)
                    state["artifacts"][art_id]["transmissions"].append(
                        {"from": state["artifacts"][art_id]["creator"], "to": sid, "tick": state["tick"], "via": "succession package (direct-transfer control)",
                         "event": f"succession:{aid}->{sid}", "operational_definition": "copied validated AST; competence requires measured use"})
            heir.update(predecessor=aid, inheritance={"policy": c["successor_access"], "package": package, "role": c["successor_role"],
                                                      "provenance": f"succession of {aid} at tick {state['tick']}",
                                                      "memories_inherited": 0, "skills_inherited": len(package)})
            old["successor"] = sid
            agents[sid] = heir
            successors.append({"predecessor": aid, "successor": sid, "name": heir["name"], "home": home["id"], "role": heir["role"],
                               "policy": c["successor_access"], "package": package, "inventory": dict(heir["inventory"])})
        state["lifecycle"]["successions"] += successors
    record = {"tick": state["tick"], "policy": c["removal"], "verified_creators": creators, "removed": chosen,
              "inventory_moved": moved, "successors": successors, "succession": c["succession"],
              "note": "scheduled lifecycle removal, not death; no verified creators existed"
              if not creators else "scheduled lifecycle removal, not death"}
    state["lifecycle"]["removal"] = record
    return {"tick": state["tick"], "type": "lifecycle_removal", **{k: v for k, v in record.items() if k != "tick"}}


# Copy strategy for action attempts. "scoped" copies only objects an action can mutate and shares the rest;
# "full" is the reference implementation. VERIFY_SHARED makes every attempt prove the input state was untouched.
COPY_STRATEGY = "scoped"
VERIFY_SHARED = False


def scoped_copy(state: JSON, action: Action) -> JSON:
    """A candidate state sharing every subtree the action cannot mutate (terrain, config, untouched agents,
    sites and artifacts). The touched set is a superset derived from parameters, independent of the action kind."""
    p = action.params

    def ref(key: str) -> str | None:
        value = p.get(key)
        return value if isinstance(value, str) else None

    offer = state["offers"].get(ref("offer") or "")
    session = state.get("sessions", {}).get(ref("session") or "")
    agent_ids = {action.agent, ref("target"), ref("learner"), offer["maker"] if offer else None,
                 session["teacher"] if session else None, session["learner"] if session else None}
    artifact = state["artifacts"].get(ref("artifact") or "")
    artifact_ids = {ref("artifact"), artifact["parent"] if artifact else None, session["artifact"] if session else None}
    candidate = dict(state)
    candidate["agents"] = {k: deepcopy(v) if k in agent_ids else v for k, v in state["agents"].items()}
    candidate["artifacts"] = {k: deepcopy(v) if k in artifact_ids else v for k, v in state["artifacts"].items()}
    candidate["sites"] = {k: deepcopy(v) if k == ref("site") else v for k, v in state["sites"].items()}
    candidate["artifacts"].update({k: deepcopy(state["artifacts"][k]) for k in (p.get("sources") or []) if isinstance(k, str) and k in state["artifacts"]})
    for key in ("settlements", "offers", "ledger", "metrics", "lifecycle", "sessions"):
        if key in state:
            candidate[key] = deepcopy(state[key])
    return candidate


def selection_score(artifact: JSON) -> float | None:
    """Freeze selection uses validation evidence only (workshop) or the legacy evaluation energy (phase-1)."""
    if artifact.get("task") == "workshop-1":
        return (artifact.get("validation") or {}).get("score") if artifact["status"] in ("admitted", "superseded") else None
    return (artifact.get("evaluation") or {}).get("energy") if artifact["status"] in ("verified", "superseded") else None


def freeze(state: JSON, cohort: int, reason: str) -> JSON:
    """Immutable selection record by artifact hash, made before any sealed evaluation exists."""
    config = state["config"]

    def best(pool):
        scored = [(selection_score(x), x["created_tick"], x["id"], x) for x in pool if selection_score(x) is not None]
        if not scored:
            return None
        score, _, _, x = min(scored, key=lambda t: t[:3])
        return {"artifact": x["id"], "selection_score": score, "creator": x["creator"], "cohort": x.get("cohort", 0),
                "generation": x["generation"], "origin": x.get("origin"), "status_at_freeze": x["status"],
                "dev_score": (x.get("development") or {}).get("score")}
    artifacts = list(state["artifacts"].values())
    created = [x for x in artifacts if x.get("cohort", 0) == cohort]
    accessible = [x for x in artifacts if x.get("cohort", 0) == cohort or (config.get("cross_cohort_access", True) and x.get("cohort", 0) < cohort)]
    record = {"tick": state["tick"], "cohort": cohort, "reason": reason,
              "rule": "lowest validation score among admitted or superseded workflows (legacy: lowest evaluation energy); ties by creation tick then id; no sealed input",
              "cohort_best": best(created), "accessible_best": best(accessible)}
    state["lifecycle"]["freezes"].append(record)
    return record


def cohort_lifecycle(state: JSON) -> list[JSON]:
    """Scheduled cohorts: at every cohort boundary, freeze, retire all active agents and create a fresh cohort
    with the same homes and roles. A final freeze is recorded when the run reaches max_ticks."""
    c, events, tick = state["config"], [], state["tick"]
    cohorts = c.get("lifecycle") == "cohorts"
    current = state["lifecycle"].get("cohort", 0)
    if cohorts and tick % c["cohort_ticks"] == 0 and 0 < tick < c["cohort_ticks"] * c["cohort_count"] and tick // c["cohort_ticks"] == current + 1:
        events.append({"tick": tick, "type": "freeze", **freeze(state, current, "cohort boundary")})
        agents = state["agents"]
        retiring = sorted(aid for aid, a in agents.items() if a["status"] == "active")
        moved, successors = [], []
        for aid in retiring:
            a = agents[aid]
            settlement = state["settlements"][a["home"]]
            for r in RESOURCES:
                settlement["inventory"][r] += a["inventory"][r]
                settlement["flows"]["retirement"][r] += a["inventory"][r]
            moved.append({"agent": aid, "to": a["home"], "inventory": dict(a["inventory"])})
            a.update(inventory={r: 0 for r in RESOURCES}, status="retired", retired_tick=tick)
        for offset, aid in enumerate(retiring):
            old = agents[aid]
            index = len(agents)
            sid = f"a{index:02d}"
            heir = new_agent(sid, NAMES[index % len(NAMES)], state["settlements"][old["home"]], offset % 3, tick, old["role"], c["sharing"])
            heir.update(cohort=current + 1, predecessor=aid,
                        inheritance={"policy": "cohort: library of earlier cohorts " + ("visible" if c.get("cross_cohort_access", True) else "hidden"),
                                     "package": [], "role": old["role"], "provenance": f"cohort {current + 1} replaces {aid} at tick {tick}",
                                     "memories_inherited": 0, "skills_inherited": 0})
            old["successor"] = sid
            agents[sid] = heir
            successors.append({"predecessor": aid, "successor": sid, "name": heir["name"], "home": heir["home"], "role": heir["role"],
                               "policy": "cohort", "package": [], "inventory": dict(heir["inventory"])})
        state["lifecycle"]["cohort"] = current + 1
        record = {"tick": tick, "cohort": current + 1, "retired": retiring, "inventory_moved": moved, "successors": successors}
        state["lifecycle"]["transitions"].append(record)
        state["lifecycle"]["successions"] += successors
        events.append({"type": "cohort_transition", **record})
    if tick == c["max_ticks"] and (cohorts or c.get("task") == "workshop-1"):
        events.append({"tick": tick, "type": "freeze", **freeze(state, state["lifecycle"].get("cohort", 0), "run closed")})
    return events


def session_upkeep(state: JSON) -> list[JSON]:
    """Offers expire; sessions interrupt when a participant is no longer active or progress stalls."""
    events, tick = [], state["tick"]
    for session in state.get("sessions", {}).values():
        if session["stage"] not in ACTIVE_STAGES:
            continue
        stage = reason = None
        absent = [x for x in (session["teacher"], session["learner"]) if state["agents"][x]["status"] != "active"]
        if session["stage"] == "offered" and tick >= session["expires"]:
            stage, reason = "expired", "offer not accepted in time"
        elif absent:
            stage, reason = "interrupted", ", ".join(f'{x} {state["agents"][x]["status"]}' for x in absent)
        elif session["stage"] != "offered" and tick - session["last_progress"] > STALL_TICKS:
            stage, reason = "interrupted", f"stalled: no progress for more than {STALL_TICKS} ticks"
        if stage:
            Rules._end_session(state, session, stage, reason, tick)
            events.append({"tick": tick, "type": "session_ended", "session": session["id"], "stage": stage, "reason": reason,
                           "teacher": session["teacher"], "learner": session["learner"], "artifact": session["artifact"]})
    return events


def attempt(state: JSON, action: Action) -> tuple[JSON, JSON]:
    candidate = scoped_copy(state, action) if COPY_STRATEGY == "scoped" else deepcopy(state)
    guard = digest(state) if VERIFY_SHARED else None
    try:
        return _attempt(state, candidate, action)
    finally:
        if guard is not None and digest(state) != guard:
            raise AssertionError(f"attempt mutated shared state for action {action.kind}")


def _attempt(state: JSON, candidate: JSON, action: Action) -> tuple[JSON, JSON]:
    try:
        before = state["agents"][action.agent]["energy"] if action.agent in state["agents"] else 0
        result = Rules().apply(candidate, action)
        check_invariants(candidate)
        # Energy charged by this action (consumption restores energy and is reported separately).
        result["energy_charged"] = before - candidate["agents"][action.agent]["energy"] + result.get("energy_restored", 0)
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
    for aid, action in sorted(overrides.items()):
        if state["agents"][aid]["status"] != "active":
            # Submissions for retired or inactive agents are rejected explicitly, never silently dropped.
            events.append({"id": action.id, "tick": state["tick"] + 1, "agent": aid, "type": "action_rejected", "kind": action.kind,
                           "accepted": False, "reason": f'agent is not active ({state["agents"][aid]["status"]})'})
            decisions.append({"action": action.model_dump(), "observation_hash": None, "controller": "submitted"})
            next_state["metrics"]["rejected"] += 1
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
    fatigue = {}
    for aid, a in next_state["agents"].items():
        if a["status"] == "active":
            if a["energy"]:
                fatigue[aid] = 1
            a["energy"] = max(0, a["energy"]-1)
            if a["energy"] == 0 and a["inventory"]["food"] == 0:
                a["status"] = "inactive"
                events.append({"tick": next_state["tick"], "type": "agent_inactive", "agent": aid, "reason": "exhausted without food; inventory retained"})
    removal = scheduled_removal(next_state)
    if removal:
        events.append(removal)
    events.extend(cohort_lifecycle(next_state))
    events.extend(session_upkeep(next_state))
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
                   "fatigue": fatigue, "expired_offers": expired})
    check_invariants(next_state)
    return next_state, events, decisions
