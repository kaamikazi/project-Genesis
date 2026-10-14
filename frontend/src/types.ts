export type Resource = 'food' | 'ore' | 'alloy';
export type Inventory = Record<Resource, number>;
export interface WorldEvent { id?: string; tick: number; agent?: string; type: string; kind?: string; accepted?: boolean; reason?: string; result?: Record<string, unknown> }
export interface Agent {
  id: string; name: string; home: string; x: number; y: number; status: string; energy: number;
  role: string; inventory: Inventory; known: string[]; used: string[]; seen: string[];
  search_count: number; created_tick: number; last_result: WorldEvent | null; memories: WorldEvent[];
  goals: string[]; beliefs: Record<string, unknown>[]; relationships: Record<string, number>; capabilities: string[];
  predecessor: string | null; successor: string | null; retired_tick: number | null;
  inheritance: { policy: 'library' | 'none' | 'direct'; package: string[]; role: string; provenance: string; memories_inherited: number; skills_inherited: number } | null;
}
export interface Use { agent: string; tick: number; energy: number; baseline_energy: number; phase: number; mode: number; event: string }
export interface EvaluationCase { group: string; phase: number; mode: number; steps: number; ore: number; alloy: number; energy: number; baseline_energy: number }
export interface Artifact {
  id: string; creator: string; home: string; created_tick: number; creation_event: string;
  status: string; parent: string | null; generation: number; superseded_by: string | null; content: { program: Record<string, unknown> }; claim: string;
  evaluation: { status: string; scope: string; criterion: string; cases: EvaluationCase[]; energy: number; baseline_energy: number; failures: string[]; parent_energy?: number } | null;
  transmissions: { from: string; to: string; tick: number; via: string; event: string }[];
  uses: Use[]; first_uses: Record<string, Use>; adopters: string[];
}
export type Removal = 'none' | 'creators' | 'matched';
export interface Scenario { seed: number; width: number; height: number; population: number; sharing: boolean; controller: 'search' | 'baseline'; max_ticks: number; snapshot_every: number; search_budget: number; removal?: Removal; removal_tick?: number;
  succession?: 'none' | 'fresh'; successor_role?: 'producer' | 'researcher'; successor_access?: 'library' | 'none' | 'direct'; invention?: 'open' | 'frozen'; controller_seed?: number }
export interface Metrics { accepted: number; rejected: number; produced: number; production_energy: number; search_proposals: number; revisions_verified?: number; evaluation_cases: number; adoptions: number; transfers: number; controller_failures: number; model_calls: number; tokens: number; cost_usd: number; active_population?: number; verified_artifacts?: number; energy_per_alloy?: number | null;
  produced_after_removal?: number; production_energy_after_removal?: number; uses_after_creator_removal?: number; learned_after_creator_removal?: number; energy_per_alloy_after_removal?: number | null }
export interface World {
  tick: number; config: Scenario; terrain: string[][]; agents: Record<string, Agent>;
  sites: Record<string, { id: string; resource: Resource; x: number; y: number; stock: number; capacity: number }>;
  settlements: Record<string, Settlement>;
  artifacts: Record<string, Artifact>; metrics: Metrics; ledger: Record<Resource, { source: number; sink: number }>;
  lifecycle?: { removal: RemovalRecord | null; successions?: Succession[] };
}
export interface Settlement { id: string; name: string; x: number; y: number; inventory: Inventory; capacity?: number | null; access?: string; flows?: Record<'deposit' | 'withdraw' | 'retirement', Inventory> }
export interface Succession { predecessor: string; successor: string; name: string; home: string; role: string; policy: 'library' | 'none' | 'direct'; package: string[] }
export interface RemovalRecord { tick: number; policy: Removal; verified_creators: string[]; removed: string[]; note: string; inventory_moved: { agent: string; to: string; inventory: Inventory }[]; successors?: Succession[]; succession?: string }
export interface Status { run_id: string; running: boolean; speed: number; error: string | null; engine?: string }
export interface Run { id: string; tick: number; compatible: boolean; manifest: { config: Scenario; controller_mode: string; origin_tick: number; engine_version: string; parent: { run_id: string; tick: number; label?: string; intervention?: Record<string, unknown> } | null } }
export interface Payload { state: World; hash: string; metrics: Metrics; status: Status; events: WorldEvent[]; checkpoints: { tick: number; state_hash: string; label: string }[]; telemetry: { avg_ms: number | null; database_bytes: number; bytes: number | null } }
export interface Ratio { value: number | null; status: string; numerator: number; denominator: number; unit: string }
export interface ReducedBlock { produced_alloy: number; production_energy: number; charged_action_energy: number; total_energy_including_fatigue: number;
  energy_by_category: Record<string, number>; production_energy_per_alloy: Ratio; charged_energy_per_alloy: Ratio; total_energy_per_alloy: Ratio;
  library_acquisitions: number; use_executions: number; uses_with_saving: number; proposals: number; verified: number; revisions_verified: number; active_agent_ticks: number }
export interface SuccessorRow { successor: string; predecessor: string; policy: string; role: string; package: string[];
  first_library_acquisition: { tick: number; event: string; artifact: string } | null;
  first_use_with_saving: { tick: number; event: string; artifact: string; energy: number; baseline_energy: number } | null;
  use_executions: number; uses_with_saving: number; produced_alloy: number; production_energy_per_alloy: Ratio }
export interface Reduced { origin_tick: number; last_tick: number; removal_tick: number | null; theoretical_max_alloy_from_initial_ore: number; final_alloy_inventory: number;
  overall: ReducedBlock; windows: Record<string, ReducedBlock & { start_exclusive: number; end_inclusive: number; ticks: number }>;
  remaining: { accessible: Record<string, number>; inaccessible: Record<string, number> }; successors: SuccessorRow[];
  reconciliation: { holdings_match_final_state: boolean; statuses_match_final_state: boolean } | null }
export interface Aggregate { worlds: number; worlds_with_value: number; mean_of_world_ratios: number | null; pooled_ratio: number | null }
export interface Comparison {
  protocol: string; exploratory: boolean; planned_ticks: number; planned_seeds: number[]; removal_tick: number; conditions: string[]; stopping_rule?: string;
  completed_runs: number; failed_runs: number; intervention_boundary: string; removal_design: string; interpretation: string;
  attempts: { seed: number; condition: string; status: string; metrics?: Metrics; reducer?: Reduced; failure?: string; export?: { file: string; compressed_bytes: number; uncompressed_bytes: number } | string; wall_seconds?: number }[];
  aggregates?: Record<string, { production_energy_per_alloy: Aggregate; charged_energy_per_alloy: Aggregate }>;
}
export interface Continuation { label: string; status: string; failure?: string; intervention: Record<string, unknown>; run_id?: string; removed?: string[];
  successors_at_boundary?: { id: string; known: string[]; capabilities: string[]; memories: number }[];
  summary?: { settlement_production_energy_per_alloy: Ratio; settlement_charged_energy_per_alloy: Ratio; produced_alloy_in_window: number; library_acquisitions_in_window: number;
    successors: SuccessorRow[]; ore_on_sites_at_end: number; depleted: boolean; new_verified_creators_after_boundary: string[] };
  export?: { file: string; compressed_bytes: number; uncompressed_bytes: number } }
export interface Inheritance {
  protocol: string; population?: number; checkpoint_tick: number; removal_boundary_tick: number; diagnostic_window: { start_exclusive: number; end_inclusive: number; ticks: number };
  live_window_ticks: number; design: string; eligibility: string; stopping_rule: string; parity_mask: string;
  seeds: { seed: number; status: string; reason?: string; failure?: string; checkpoint?: { tick: number; verified_procedures: string[]; ore_remaining: number; ore_needed_estimate: number };
    diagnostic: Continuation[]; live: Continuation[]; physical_parity?: { identical: boolean; same_retirees: boolean } }[];
  aggregates: Record<string, { settlement_production_energy_per_alloy: Aggregate; successor_production_energy_per_alloy: Aggregate; successors: number;
    successors_with_library_acquisition: number; successors_with_use_with_saving: number }>;
}
