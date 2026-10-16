"""Versioned metric dictionary (v0.5.1). Every reported counter is defined here: what it counts, its unit, what is
included or excluded, and which recorded field it is computed from. `genesis.reducer` computes the `metrics`
block from these definitions; `docs/METRICS.md` is generated from this file (tools/write_metrics_doc.py).

Distinct counters are allowed to differ. Similar names never mean the same thing unless defined identically here.
"""
from __future__ import annotations

METRICS_VERSION = "genesis-metrics-1"

# name -> (definition, unit, inclusion rule, event source)
METRICS: dict[str, tuple[str, str, str, str]] = {
    # --- search: what was proposed and tested ------------------------------------------------------------------
    "search.credit_actions": ("Accepted propose, development-test (incl. component test) and submit actions.", "actions",
                              "researchers and any other proposer; withdrawals are free and excluded", "action_accepted propose_artifact | test_artifact(role development) | submit_artifact"),
    "search.proposals": ("Accepted workshop proposals (workflows and components).", "proposals", "workshop-1 only", "action_accepted propose_artifact with program_hash"),
    "search.identical_program_proposals": ("Proposals whose program content hash equals an earlier proposal by the same agent.", "proposals",
                                           "same agent only; content identity, not behaviour", "propose result program_hash"),
    "search.distinct_programs": ("Distinct program content hashes proposed in the world.", "programs", "all agents", "propose result program_hash"),
    "search.own_candidate_tests": ("Development tests of a workflow the tester itself created (no host).", "tests", "excludes component tests and re-tests of held artifacts",
                                   "action_accepted test_artifact role development, no host, artifact created by the tester"),
    "search.held_retests": ("Development tests of an artifact the tester did not create (its own reading of a held workflow).", "tests", "no host",
                            "action_accepted test_artifact role development, artifact created by another agent"),
    "search.component_tests": ("In-host development tests of a component.", "tests", "host present", "action_accepted test_artifact with host"),
    "search.repeated_decisions_own": ("Own-candidate tests whose decisions on the 24 development cases (behaviour hash) equal an earlier own-candidate test by the same agent.",
                                      "tests", "same agent; first occurrence not counted; equality on 24 sampled inputs, NOT program equivalence", "test result behavior_hash"),
    "search.repeated_decisions_world": ("Own-candidate tests whose behaviour hash appeared in an earlier own-candidate test by ANY agent in the world (v0.5 'duplicate_behaviour_dev_results').",
                                        "tests", "world scope; first occurrence not counted", "test result behavior_hash"),
    "search.matching_outcome_different_decisions_own": ("Own-candidate tests whose development score equals an earlier own-candidate score of the same agent although their decisions differ from every earlier one.",
                                                        "tests", "same agent", "test result dev_score and behavior_hash"),
    "search.untested_proposals": ("Proposals never development-tested (workflow test or component test) by the end of the run.", "proposals",
                                  "workflows and components; withdrawn-before-test included", "propose and test events"),
    "search.submissions": ("Accepted submissions (workflows and components).", "submissions", "rejected submissions excluded", "action_accepted submit_artifact"),
    "search.stale_reference_rejections": ("Rejected submissions whose admission reference was no longer current (or did not match the named reference).", "rejections",
                                          "v0.5 reason 'no longer current' and v0.5.1 'stale reference'/'reference conflict'", "action_rejected submit_artifact reason"),
    "search.repeated_rejected_attempts": ("Rejected actions identical (kind and parameters) to the same agent's immediately preceding rejected action.", "rejections",
                                          "requires v0.5.1 rejected-event params; v0.5 records lack params (unavailable)", "action_rejected params"),
    "search.withdrawals": ("Accepted withdraw_artifact actions.", "actions", "v0.5.1+", "action_accepted withdraw_artifact"),
    "search.withdrawals_of_stale_candidates": ("Decisions to withdraw a candidate because its admission reference was no longer current.", "decisions", "v0.5.1+", "decision diagnostic step withdraw-stale"),
    "search.reserve_stops": ("Decisions where the allocation bundle declined to propose because the pool or the remaining lifetime could not fund propose + test + submit.", "decisions", "beam-alloc only", "decision diagnostic stop reserve"),
    "search.novelty_rejected_candidates": ("Candidates the allocation bundle skipped as decision-equivalent (for every input) to a program the agent had proposed or held.", "candidates", "beam-alloc only; not task evaluations", "decision diagnostic novelty_rejected"),
    "search.novelty_point_evaluations": ("Program evaluations on representative inputs performed by the exact-novelty check (CPU work; no task cases, outcomes or credits).", "evaluations", "beam-alloc only", "decision diagnostic novelty_point_evaluations"),
    # --- admission ------------------------------------------------------------------------------------------------
    "admission.improvement_admissions": ("Admitted submissions that passed the strict improvement criterion.", "admissions", "workflows and components; refactors excluded",
                                         "submit result admitted and admission_path != refactor"),
    "admission.refactor_admissions": ("Admitted behaviour-preserving refactors (declared refactor path; no improvement claimed).", "admissions", "", "submit result admission_path == refactor"),
    # --- lineage across generations -------------------------------------------------------------------------------
    "lineage.improvements_on_earlier_cohort_reference": ("Admitted improvement workflows whose admission reference (nearest admitted ancestor) was created by an earlier cohort than the submitter's.",
                                                         "admissions", "refactors excluded", "submit result reference + artifact creator cohort"),
    "lineage.improvements_on_earlier_cohort_parent": ("Admitted improvement workflows whose IMMEDIATE parent was created by an earlier cohort (v0.5 cross_generation.admitted_revisions; refactors included there).",
                                                      "admissions", "refactors excluded here", "propose result parent_cohort / lineage"),
    "lineage.improvements_with_earlier_cohort_ancestry": ("Admitted improvement workflows with any earlier-cohort creator anywhere in their parent chain.", "admissions",
                                                          "refactors excluded; v0.5.1 records ancestor_cohorts at proposal", "propose result ancestor_cohorts"),
    # --- knowledge at boundaries (from freeze records) ---------------------------------------------------------------
    "knowledge.held_best": ("Best admitted workflow HELD by a cohort's members at its freeze, however acquired (may include later cohorts' work adopted during overlap).",
                            "cost per alloy (validation)", "selection by validation", "freeze held_best"),
    "knowledge.created_upto_best": ("Best admitted workflow CREATED by this or earlier cohorts by the freeze tick (creation-event attribution; adoption cannot change it).",
                                    "cost per alloy (validation)", "v0.5.1 freezes", "freeze created_upto_best"),
    "knowledge.further_improvement": ("Cohort k's own created best is strictly better than knowledge.created_upto_best frozen at cohort k-1's boundary (validation; sealed reported separately).",
                                      "transitions", "a transition with no admitted cohort-k workflow counts as not improved and is reported as such", "freeze records"),
    # --- production ------------------------------------------------------------------------------------------------
    "production.actions": ("Accepted produce, use_artifact and practice_step actions.", "actions", "", "action_accepted"),
    "production.alloy": ("Alloy produced by production actions.", "alloy", "starting inventory excluded", "production results"),
    "production.alloy_per_action": ("production.alloy / production.actions.", "alloy per action", "unavailable when no actions", "derived"),
    "production.rejected_use_missing_prerequisite": ("Rejected use_artifact attempts because a called component was not held.", "rejections", "", "action_rejected reason"),
    "production.busy_ticks": ("Ticks an agent was occupied by multi-tick batches (reported by production results).", "agent-ticks", "", "production result busy_ticks"),
    "time.agent_ticks_by_activity": ("Active-agent decisions by the action they produced, accepted or rejected.", "agent-ticks", "one decision per active agent per tick",
                                     "decisions + events"),
    "population.base": ("Configured base population (agents per cohort).", "agents", "", "initial config"),
    "population.peak_active": ("Largest number of active agents deciding in any one tick (overlap doubles it).", "agents", "", "decisions with an observation"),
    "selection.final_pick_selection_panel_score": ("Score of the final freeze's selection_panel_best on the shared selection-0 panel (observer-side; never shown to agents; selection-used, not a final test).",
                                                   "cost per alloy", "v0.5.2 final_selection selection-panel", "freeze selection_panel_best"),
    "selection.evaluations": ("Candidates and case evaluations spent choosing the final pick (bounded by selection_candidates x 24).", "evaluations", "", "freeze selection_accounting"),
    "selection.final_pick_sealed": ("Sealed score of the final pick, computed only after the run closed.", "cost per alloy", "", "sealed results"),
    "admission.panel_queries": ("Submissions per researcher per cohort panel, and how often the cap was reached.", "submissions", "validation_policy cohort-panels", "agent panel_queries"),
    # --- v0.6 model-backed inhabitants ---------------------------------------------------------------------------
    "model.decisions_by_mode": ("Committed decisions of designated model agents by true source: model-proposal, model-intent-execution (standing model choice, no new call), offline-policy, fallback.",
                                "decisions", "designated agents only; other agents keep their ordinary modes", "decision controller + decision model meta"),
    "model.attributed_calls": ("Provider requests (primary and repair attempts, including failed and outcome-unknown ones) attributed to the committed decision of their tick.",
                               "requests", "recorded re-use is historical and never counted again", "decision model.new_calls; ledger rows"),
    "model.attributed_reported_tokens": ("Provider-reported input + output tokens of attributed requests (estimates excluded).", "tokens", "basis reported only",
                                         "decision model.new_tokens; ledger reconciled usage"),
    "model.budget_buckets": ("Per run/agent: committed (reconciled), pending (reserved/dispatching), uncertain (outcome-unknown, never released), historical (recordings).",
                             "requests, tokens, ms, micro-units", "integer units; money only with configured prices", "ledger reservation / reconciled"),
    "model.reconciled": ("True when every referenced ledger row exists, receipts match, consumed rows are referenced exactly once, and world metrics equal ledger-attributed calls and reported tokens.",
                         "boolean", "", "reducer model_reconciliation"),
    # --- comparisons --------------------------------------------------------------------------------------------------
    "compare.paired": ("A paired comparison reports expected worlds, completed worlds, eligible pairs (both values present), missing values with reasons, wins/losses/ties among eligible pairs, and the denominator used by the decision rule. Means are over eligible pairs only.",
                       "worlds", "a missing artifact is never scored as zero", "tools/summarize_m5b.py"),
}


def as_markdown() -> str:
    lines = [f"# Metric dictionary ({METRICS_VERSION})", "",
             "Generated from `genesis/metrics_dictionary.py`. Distinct counters may differ; similar names are not interchangeable.", "",
             "| Metric | Definition | Unit | Inclusion | Source |", "|---|---|---|---|---|"]
    for name, (definition, unit, inclusion, source) in METRICS.items():
        cell = lambda text: text.replace("|", r"\|")  # noqa: E731
        lines.append(f"| `{name}` | {cell(definition)} | {cell(unit)} | {cell(inclusion) or '—'} | {cell(source)} |")
    return "\n".join(lines) + "\n"
