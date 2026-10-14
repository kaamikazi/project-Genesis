from __future__ import annotations

from . import workshop as ws
from .invention import candidate, revisions
from .models import Action, JSON, canonical, keyed
from .world import distance


USABLE_HELD = ("verified", "admitted", "superseded")
BEAM_WIDTH, STALL_RESTART, SUBMIT_MARGIN, CANDIDATE_CAP, MIN_TRIALS = 4, 4, 0.03, 200, 6


class SearchBudget:
    def available(self, agent: JSON, limit: int, unit: str = "proposals") -> bool:
        if unit == "credits":            # a proposal needs a credit for itself and one for its development test
            return limit - agent.get("search_spent", 0) >= 2
        return agent["search_count"] < limit

    @staticmethod
    def remaining(agent: JSON, limit: int, unit: str = "proposals") -> int:
        return limit - (agent.get("search_spent", 0) if unit == "credits" else agent["search_count"])


class OfflineController:
    """A designed deterministic policy with a bounded candidate enumerator. No LLM.

    Its only randomness is `seed`, supplied at construction from the scenario's independent `controller_seed`.
    The seed is held behind the controller boundary; observations carry no seed-derived value. Every branch
    below is developer-supplied policy; the engine decides every outcome."""
    def __init__(self, seed: int = 7):
        self.seed = seed
        self.diagnostic: JSON | None = None   # per-decision search record, stored with the decision (tick record only)

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
                target = o["neighbors"][tick % len(o["neighbors"])] if o["rules"].get("teaching_policy") == "package" else o["neighbors"][0]   # v0.5 rotates requests
                return act("send_message", target=target["id"], message="request_lesson")
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
        policy = o["rules"].get("search_policy", "first-improvement")
        unit = o["rules"].get("budget_unit", "proposals")
        if policy != "first-improvement":
            return self._beam(o, act, obtain, own, held, notes, unit, components=policy == "beam")
        pending = [v for v in own if v["status"] == "proposed" and v.get("kind") == "workflow"]
        if pending:
            self.diagnostic = {"policy": policy, "step": "test", "artifact": pending[0]["id"][:12]}
            return act("test_artifact", artifact=pending[0]["id"])
        current = min(held, key=lambda v: (notes.get(v["id"], float("inf")), -v["created_tick"])) if held else None
        current_dev = notes.get(current["id"]) if current else notes.get("baseline", float("inf"))
        latest = own[-1] if own else None
        if latest and latest["status"] == "dev-tested" and latest.get("dev_score") is not None and latest["dev_score"] < (current_dev if current_dev is not None else float("inf")):
            self.diagnostic = {"policy": policy, "step": "submit", "artifact": latest["id"][:12]}
            return act("submit_artifact", artifact=latest["id"])
        library = sorted((v for v in arts.values() if v["id"] not in a["known"] and v["status"] == "admitted" and v.get("kind") == "workflow"),
                         key=lambda v: -v["created_tick"])
        if library and not any(v["status"] == "admitted" for v in held):   # upgrade when the head was superseded
            return act("inspect_artifact", artifact=library[0]["id"])
        if a["role"] == "researcher" and o["rules"]["invention_open"]:
            reason = None if SearchBudget().available(a, o["rules"]["search_budget"], unit) else "budget-exhausted"
            reason = reason or (None if a["energy"] >= 12 else "energy")
            if reason:
                self.diagnostic = {"policy": policy, "step": "stop", "stop": reason,
                                   "budget_remaining": SearchBudget.remaining(a, o["rules"]["search_budget"], unit)}
        if a["role"] == "researcher" and o["rules"]["invention_open"] and SearchBudget().available(a, o["rules"]["search_budget"], unit) and a["energy"] >= 12:
            untested = [v for v in held if v["id"] not in notes]
            if untested:
                self.diagnostic = {"policy": policy, "step": "retest-held", "artifact": untested[0]["id"][:12]}
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
                params = {"program": program, "parent": current["id"] if current else None, "operator": label}
                if sources:
                    params["sources"] = sources
                self.diagnostic = {"policy": policy, "step": "propose", "operator": label, "parent": (current["id"][:12] if current else "baseline"),
                                   "candidates": len(options), "budget_remaining": SearchBudget.remaining(a, o["rules"]["search_budget"], unit)}
                return act("propose_artifact", **params)
            self.diagnostic = {"policy": policy, "step": "stop", "stop": "no-candidate",
                               "budget_remaining": SearchBudget.remaining(a, o["rules"]["search_budget"], unit)}
        if tick % 43 == 17 and a["inventory"]["food"] >= 5 and o["neighbors"]:
            return act("transfer", target=o["neighbors"][0]["id"], resource="food", amount=1)
        if a["inventory"]["ore"] < (8 if held else 2):
            return obtain("ore", 8)                  # holders top up so the workflow can choose larger batches
        if held:
            best = min(held, key=lambda v: (notes.get(v["id"], float("inf")), v["status"] != "admitted", -v["created_tick"]))
            return act("use_artifact", artifact=best["id"])
        return act("produce")


    # --- beam search (v0.5) ---------------------------------------------------------------------

    def _beam(self, o: JSON, act, obtain, own: list, held: list, notes: JSON, unit: str, components: bool) -> Action:
        """Bounded beam search over the declared neighbourhood, using only permitted evidence: the agent's own
        development results, its private history, held artifacts and held components."""
        a, arts = o["self"], o["artifacts"]
        policy = "beam" if components else "beam-nocomponents"
        budget = o["rules"]["search_budget"]
        remaining = SearchBudget.remaining(a, budget, unit)

        def finish(action: Action, **diag) -> Action:
            self.diagnostic = {"policy": policy, "budget_remaining": remaining, **diag}
            return action

        own_wf = [v for v in own if v.get("kind") == "workflow"]
        own_comp = [v for v in own if v.get("kind") == "component"]
        held_comps = {k: arts[k] for k in a["known"] if k in arts and arts[k].get("kind") == "component" and arts[k]["status"] == "admitted"}
        admitted_held = [v for v in held if v["status"] == "admitted"]
        champion = min(admitted_held, key=lambda v: (notes.get(v["id"], float("inf")), -v["created_tick"])) if admitted_held else None
        champion_dev = notes.get(champion["id"], float("inf")) if champion else notes.get("baseline", float("inf"))
        researcher = a["role"] == "researcher" and o["rules"]["invention_open"]
        can_search = researcher and a["energy"] >= 12
        if researcher and can_search and remaining >= 1:
            pending = [v for v in own_wf if v["status"] == "proposed"]
            if pending:
                return finish(act("test_artifact", artifact=pending[0]["id"]), step="test")
            pending_c = [v for v in own_comp if v["status"] == "proposed"]
            if pending_c and champion:
                return finish(act("test_artifact", artifact=pending_c[0]["id"], host=champion["id"]), step="test-component")
            ready = sorted((v for v in own_wf if v["status"] == "dev-tested" and v.get("dev_score") is not None), key=lambda v: (v["dev_score"], v["created_tick"]))
            if ready and ready[0]["dev_score"] < champion_dev * (1 - SUBMIT_MARGIN):
                return finish(act("submit_artifact", artifact=ready[0]["id"]), step="submit", dev=ready[0]["dev_score"], champion_dev=champion_dev)
            refactors = [v for v in ready if components and champion and v["parent"] == champion["id"]
                         and str(v.get("operator", "")).startswith("call:") and v["dev_score"] <= champion_dev]
            if refactors:   # equal development behaviour: offer it under the declared refactor admission path
                return finish(act("submit_artifact", artifact=refactors[0]["id"]), step="submit-refactor", dev=refactors[0]["dev_score"], champion_dev=champion_dev)
            ready_c = [v for v in own_comp if v["status"] == "dev-tested" and v.get("dev_host") in a["known"]
                       and v.get("dev_score") is not None and v.get("host_dev_score") is not None
                       and (v["dev_score"] < v["host_dev_score"] or (v.get("behavior_equal_to_host") and v["parent"] is None))]
            if ready_c:
                return finish(act("submit_artifact", artifact=ready_c[0]["id"]), step="submit-component")
        library = sorted((v for v in arts.values() if v["id"] not in a["known"] and v["status"] == "admitted" and v.get("kind") in ("workflow", "component")),
                         key=lambda v: (v.get("kind") != "workflow", -v["created_tick"]))
        if library and (not admitted_held or (researcher and library[0].get("kind") == "component" and components)):
            return finish(act("inspect_artifact", artifact=library[0]["id"]), step="learn")
        if researcher and not can_search:
            self.diagnostic = {"policy": policy, "step": "stop", "stop": "energy", "budget_remaining": remaining}
        elif researcher and not SearchBudget().available(a, budget, unit):
            self.diagnostic = {"policy": policy, "step": "stop", "stop": "budget-exhausted", "budget_remaining": remaining}
        elif researcher:
            untested = [v for v in held if v["id"] not in notes]
            if untested:
                return finish(act("test_artifact", artifact=untested[0]["id"]), step="retest-held")
            choice = self._beam_candidate(a, own_wf, own_comp, held, held_comps, notes, champion, components)
            if choice is None:
                self.diagnostic = {"policy": policy, "step": "stop", "stop": "no-candidate", "budget_remaining": remaining}
            else:
                params, diag = choice
                return finish(act("propose_artifact", **params), step="propose", **diag)
        if o["tick"] % 43 == 17 and a["inventory"]["food"] >= 5 and o["neighbors"]:
            return act("transfer", target=o["neighbors"][0]["id"], resource="food", amount=1)
        if a["inventory"]["ore"] < (8 if held else 2):
            return obtain("ore", 8)
        if held:
            best = min(held, key=lambda v: (notes.get(v["id"], float("inf")), v["status"] != "admitted", -v["created_tick"]))
            return act("use_artifact", artifact=best["id"])
        return act("produce")

    def _beam_candidate(self, a: JSON, own_wf: list, own_comp: list, held: list, held_comps: JSON, notes: JSON, champion, components: bool):
        """Choose the next proposal: rotate over the frontier, order operators by private success rates, restart by
        recombination after repeated failures. Returns (params, diagnostic) or None when the neighbourhood is exhausted."""
        score_of = {v["id"]: v.get("dev_score") for v in own_wf}
        score_of.update({v["id"]: notes.get(v["id"]) for v in held})
        parentable = [v for v in own_wf if v["status"] in ("dev-tested", "not-admitted") and v.get("dev_score") is not None]
        parentable += [v for v in held if v["status"] == "admitted" and notes.get(v["id"]) is not None]
        frontier = sorted(parentable, key=lambda v: (score_of[v["id"]], v["created_tick"]))[:BEAM_WIDTH]
        nodes = [(v["id"], v["program"], score_of[v["id"]]) for v in frontier]
        if not nodes:                       # the baseline seeds the frontier only until something beats it
            nodes.append((None, ws.BASELINE, notes.get("baseline")))
        stats: JSON = {}
        for v in own_wf:
            if v.get("operator") and v.get("dev_score") is not None:
                family = v["operator"].split(":")[0]
                parent_score = score_of.get(v["parent"]) if v["parent"] else notes.get("baseline")
                ok = parent_score is not None and v["dev_score"] < parent_score
                trials, wins = stats.get(family, (0, 0))
                stats[family] = (trials + 1, wins + ok)
        recent = [v for v in sorted(own_wf, key=lambda v: -v["created_tick"]) if v.get("dev_score") is not None][:STALL_RESTART]
        stalled = len(recent) == STALL_RESTART and all((score_of.get(v["parent"]) if v["parent"] else notes.get("baseline")) is not None
                                                        and v["dev_score"] >= (score_of.get(v["parent"]) if v["parent"] else notes.get("baseline")) for v in recent)
        tried = {canonical(v["program"]) for v in own_wf + own_comp}
        if components and champion is not None:
            # Component lifecycle: once a component is held, first try refactoring the champion to call it.
            for cid, comp in sorted(held_comps.items(), key=lambda kv: -kv[1]["created_tick"]):
                field = comp["program"]["field"]
                if canonical(champion["program"][field]) == canonical({"op": "call", "artifact": cid}):
                    continue
                candidate = {**champion["program"], field: {"op": "call", "artifact": cid}}
                if canonical(candidate) not in tried:
                    return ({"program": candidate, "parent": champion["id"], "operator": f"call:{field}"},
                            {"operator": f"call:{field}", "parent": champion["id"][:12], "component": cid[:12], "frontier_rank": 0, "restart": False, "candidates": 1})
        held_programs = [v["program"] for v in held if v["status"] == "admitted"]
        failed_children: JSON = {}
        for v in own_wf:
            if v.get("dev_score") is not None:
                parent_score = score_of.get(v["parent"]) if v["parent"] else notes.get("baseline")
                if parent_score is not None and v["dev_score"] >= parent_score:
                    failed_children[v["parent"]] = failed_children.get(v["parent"], 0) + 1
        # Best-first in blocks: each frontier node gets 3 failed tries before the next node is preferred.
        order = sorted(nodes, key=lambda n: (failed_children.get(n[0], 0) // 3, n[2] if n[2] is not None else float("inf")))
        for rank, (pid, program, pscore) in enumerate(order):
            others = [n[1] for n in nodes if n[0] != pid and n[0] is not None] + held_programs
            cands = [(label, cand, {}) for label, cand in ws.neighbours(program, others)]
            if components and champion is not None and pid == champion["id"]:
                cands += [(label, cand, extra) for label, cand, extra in ws.component_operators(program, {k: v["program"] for k, v in held_comps.items()})]
            cands = [c for c in cands if canonical(c[1]) not in tried][:CANDIDATE_CAP]
            if stalled:
                compose = [c for c in cands if c[0].startswith("compose")]
                cands = compose or cands
            if not cands:
                continue

            total_trials = sum(t for t, _ in stats.values())

            def rate(label: str) -> float:
                # Private operator credit assignment only after enough evidence; before that, sample the declared
                # neighbourhood uniformly (keyed), exactly like the reference policy.
                if total_trials < MIN_TRIALS:
                    return 0.5
                trials, wins = stats.get(label.split(":")[0], (0, 0))
                return (wins + 1) / (trials + 2)
            cands.sort(key=lambda c: (-rate(c[0]), keyed(self.seed, "controller-beam", a["id"], canonical(c[1]))))
            label, cand, extra = cands[0]
            if extra.get("kind") == "component":
                params = {"program": cand, "parent": extra.get("parent"), "operator": label}
            else:
                params = {"program": cand, "parent": pid, "operator": label}
                if label.startswith("compose:"):
                    field = label.split(":")[1]
                    src = [v["id"] for v in held if v["status"] == "admitted" and canonical(v["program"][field]) == canonical(cand[field])]
                    if src:
                        params["sources"] = src[:1]
            return params, {"operator": label, "parent": (pid or "baseline")[:12], "frontier": [((n[0] or "baseline")[:8], n[2]) for n in nodes],
                            "frontier_rank": rank, "restart": stalled, "candidates": len(cands)}
        return None
