export type Resource = 'food' | 'ore' | 'alloy';
export type Inventory = Record<Resource, number>;
export interface WorldEvent { id?: string; tick: number; agent?: string; type: string; kind?: string; accepted?: boolean; reason?: string; result?: Record<string, unknown> }
export interface Agent {
  id: string; name: string; home: string; x: number; y: number; status: string; energy: number;
  role: string; inventory: Inventory; known: string[]; used: string[]; seen: string[];
  search_count: number; created_tick: number; last_result: WorldEvent | null; memories: WorldEvent[];
  goals: string[]; beliefs: Record<string, unknown>[]; relationships: Record<string, number>;
}
export interface EvaluationCase { group: string; phase: number; mode: number; steps: number; ore: number; alloy: number; energy: number; baseline_energy: number }
export interface Artifact {
  id: string; creator: string; home: string; created_tick: number; creation_event: string;
  status: string; parent: string | null; generation: number; superseded_by: string | null; content: { program: Record<string, unknown> }; claim: string;
  evaluation: { status: string; scope: string; criterion: string; cases: EvaluationCase[]; energy: number; baseline_energy: number; failures: string[]; parent_energy?: number } | null;
  transmissions: { from: string; to: string; tick: number; via: string; event: string }[];
  uses: { agent: string; tick: number; energy: number; baseline_energy: number; phase: number; event: string }[]; adopters: string[];
}
export type Removal = 'none' | 'creators' | 'matched';
export interface Scenario { seed: number; width: number; height: number; population: number; sharing: boolean; controller: 'search' | 'baseline'; max_ticks: number; snapshot_every: number; search_budget: number; removal?: Removal; removal_tick?: number }
export interface Metrics { accepted: number; rejected: number; produced: number; production_energy: number; search_proposals: number; revisions_verified?: number; evaluation_cases: number; adoptions: number; transfers: number; controller_failures: number; model_calls: number; tokens: number; cost_usd: number; active_population?: number; verified_artifacts?: number; energy_per_alloy?: number | null;
  produced_after_removal?: number; production_energy_after_removal?: number; uses_after_creator_removal?: number; learned_after_creator_removal?: number; energy_per_alloy_after_removal?: number | null }
export interface World {
  tick: number; config: Scenario; terrain: string[][]; agents: Record<string, Agent>;
  sites: Record<string, { id: string; resource: Resource; x: number; y: number; stock: number; capacity: number }>;
  settlements: Record<string, { id: string; name: string; x: number; y: number; inventory: Inventory }>;
  artifacts: Record<string, Artifact>; metrics: Metrics; ledger: Record<Resource, { source: number; sink: number }>;
  lifecycle?: { removal: RemovalRecord | null };
}
export interface RemovalRecord { tick: number; policy: Removal; verified_creators: string[]; removed: string[]; note: string; inventory_moved: { agent: string; to: string; inventory: Inventory }[] }
export interface Status { run_id: string; running: boolean; speed: number; error: string | null; engine?: string }
export interface Run { id: string; tick: number; compatible: boolean; manifest: { config: Scenario; controller_mode: string; origin_tick: number; engine_version: string; parent: { run_id: string; tick: number } | null } }
export interface Payload { state: World; hash: string; metrics: Metrics; status: Status; events: WorldEvent[]; checkpoints: { tick: number; state_hash: string; label: string }[]; telemetry: { avg_ms: number | null; database_bytes: number; bytes: number | null } }
export interface PairedField { left: number | null; right: number | null; difference: number | null }
export type PairedRow = { seed: number; left: string; right: string } & Record<string, PairedField | number | string>;
export interface Comparison {
  protocol: string; exploratory: boolean; planned_ticks: number; planned_seeds: number[]; removal_tick: number; conditions: string[];
  completed_runs: number; failed_runs: number; intervention_boundary: string; removal_design: string; interpretation: string;
  attempts: { seed: number; condition: string; status: string; metrics?: Metrics; failure?: string; export?: string; wall_seconds?: number }[];
  paired: Record<string, PairedRow[]>;
}
