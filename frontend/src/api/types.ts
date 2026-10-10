export type Status = 'direct' | 'propagated' | 'unaffected'
export interface Hazard {
  hazard_type: 'flood' | 'heat' | 'drought'; intensity: number; duration_days: number
  center_lat?: number | null; center_lon?: number | null; radius_km?: number | null
  regions: string[]; affected_entity_ids: string[]; label: string
}
export interface ScenarioSpec {
  name: string; description: string; hazards: Hazard[]; time_horizon_year: number; data_source: 'synthetic_footprint'
  propagation_max_depth: number; inventory_scale: number; substitution_scale: number; dependency_scale: number
  compound_amplification: number; monte_carlo_runs: number; monte_carlo_seed: number
  use_graph_alternatives?: boolean; cycle_damping?: number
}
export interface ScenarioRecord extends ScenarioSpec { id: string; builtin: boolean; synthetic: boolean; created_at?: string }
export interface GraphNode {
  id: string; name: string; entity_type: string; food_category: string; output_product: string | null; country: string | null
  region: string | null; latitude: number | null; longitude: number | null; synthetic: boolean; operational_criticality: number
  value_added_musd: number; inventory_days: number; confidence: string; in_demo_portfolio: boolean
}
export interface GraphEdge {
  id: string; source: string; target: string; product: string; channel: 'supply' | 'financial'; relationship_type: string
  dependency: number; input_specificity: number; substitutability: number; storable: boolean; lead_time_days: number
  annual_flow_musd: number; distance_km: number | null; status: string; confidence: number
}
export interface GraphPayload { nodes: GraphNode[]; edges: GraphEdge[]; n_nodes: number; n_edges: number; edge_semantics: string; structure: Structure }
export interface Structure {
  n_nodes: number; n_edges: number; weak_component_sizes: number[]; largest_component_share: number
  cycles: string[][]; single_source_dependencies: { target: string; product: string; supplier: string; dependency: number }[]; is_dag: boolean
}
export interface EntityImpact {
  entity_id: string; name: string; entity_type: string; food_category: string; country: string | null; region: string | null
  synthetic: boolean; status: Status; hazard_intensity: number; direct_disruption: number; final_disruption: number
  hop_order: number | null; value_added_musd: number; direct_loss_musd: number; indirect_loss_musd: number; total_loss_musd: number
  loss_by_order_musd: Record<string, number>; evidence_label: string
}
export interface Breakdown { key: string; entities: number; affected: number; direct_loss_musd: number; indirect_loss_musd: number; total_loss_musd: number }
export interface PathHop { source: string; target: string; product: string; transmission: number }
export interface CriticalPath {
  origin_id: string; terminal_id: string; entity_ids: string[]; names: string[]; hops: PathHop[]
  cumulative_transmission: number; terminal_total_loss_musd: number
}
/** How a portfolio holding is defined: a company made of business units (segments), or each held unit on its own (v0.3). */
export type HoldingView = 'company' | 'business_unit'
export type HoldingKind = 'single_business' | 'multi_segment'
/** Company-structure fields shared by holding rows; present only for multi-segment companies. */
export interface CompanyStructure {
  kind?: HoldingKind; primary_entity_id?: string | null
  other_businesses_share?: number | null; network_disruption_if_other_hit?: number | null; network_disruption_one_node?: number | null
}
export interface SegmentRow { entity_id: string; name: string; segment: string; share: number; location_disruption?: number; direct_disruption?: number; network_disruption: number }
export interface ComparisonRow extends CompanyStructure {
  entity_id: string; name: string; location_disruption: number; network_disruption: number; location_loss_musd: number
  network_loss_musd: number; rank_location: number; rank_network: number; rank_change: number; hidden_exposure: boolean; weight: number
  segments?: SegmentRow[] | null
}
export interface Comparison {
  location_only_loss_musd: number; network_aware_loss_musd: number; absolute_difference_musd: number; relative_difference: number | null
  portfolio_location_loss_musd: number; portfolio_network_loss_musd: number; portfolio_absolute_difference_musd: number
  portfolio_relative_difference: number | null; portfolio_rows: ComparisonRow[]; hidden_exposure_count: number; scope_note: string
  portfolio_location_impact: number; portfolio_network_impact: number; portfolio_hidden_share: number | null
  hidden_exposure_curve: { threshold: number; count: number }[]
  holding_view?: HoldingView; portfolio_network_impact_if_other_hit?: number | null; portfolio_network_impact_one_node?: number | null
}
export interface RunSummary {
  n_entities: number; n_exposed_facilities: number; n_affected_downstream: number; direct_loss_musd: number; indirect_loss_musd: number
  total_loss_musd: number; indirect_to_direct_ratio: number | null; iterations: number; converged: boolean
  effective_duration_days: number; loss_period_fraction: number; max_depth_used: number
}
export interface RunResult {
  scenario: ScenarioSpec; scenario_id: string | null; summary: RunSummary
  orders: { order: string; label: string; entities: number; loss_musd: number; evidence: string }[]
  entities: EntityImpact[]; by_food_category: Breakdown[]; by_entity_type: Breakdown[]; by_region: Breakdown[]
  critical_paths: CriticalPath[]; comparison: Comparison
  bottlenecks: { entity_id: string; name: string; score: number; downstream_reach: number; betweenness: number; out_degree: number; weighted_out_dependency: number; note: string }[]
  assumptions: string[]; limitations: string[]; units: Record<string, string>
}
export interface Quantiles { mean: number; median: number; p05: number; p25: number; p75: number; p95: number; min: number; max: number }
export interface MonteCarloResult {
  n_simulations: number; seed: number; total_loss: Quantiles; direct_loss: Quantiles; indirect_loss: Quantiles; network_minus_location: Quantiles
  histogram: { lo: number; hi: number; count: number }[]
  sensitivity: { parameter: string; spearman_with_total_loss: number; approx_variance_share?: number; description: string }[]
  indirect_sensitivity?: { parameter: string; spearman_with_total_loss: number; approx_variance_share?: number; description: string }[]
  top_entities: { entity_id: string; name: string; median_loss_musd: number; p05_loss_musd: number; p95_loss_musd: number; probability_affected: number }[]
  assumptions: string[]; interpretation: string; deterministic_total_loss_musd: number
}
export interface EntityDetail extends GraphNode {
  facility_type: string | null; revenue_musd: number; capacity_tonnes_per_year: number | null; alternative_supplier_availability: number
  spare_capacity_fraction: number; exposed_asset_share: number | null; flood_vulnerability: number; heat_vulnerability: number
  drought_vulnerability: number; provenance: string; location_status: string; in_degree: number; out_degree: number
  supplier_concentration_hhi: number | null; single_source_inputs: string[]; missing_fields: string[]
  jrc_flood_rp100?: { cells: number; window_coverage?: number; flooded_share: number; deep_share: number; radius_km: number; return_period_years: number; source: string; licence: string; meaning: string } | null
  company?: { id: string; name: string; segment: string; share: number; other_businesses_share: number; pattern: string | null; in_demo_portfolio: boolean; synthetic: boolean
    segments: { entity_id: string; name: string; segment: string; share: number }[] } | null
}
export interface Neighbour {
  relation_id: string; entity_id: string; name: string; product: string; dependency: number; input_specificity: number
  substitutability: number; lead_time_days: number; status: string; confidence: number; channel: string
}
export interface Dependencies { entity_id: string; suppliers: Neighbour[]; customers: Neighbour[]; upstream_hops: Record<string, number>; downstream_hops: Record<string, number>; n_upstream: number; n_downstream: number }
export interface SystemicRow {
  entity_id: string; name: string; entity_type: string; food_category: string; score: number; rank: number
  components: Record<string, number>; contributions: Record<string, number>; in_degree: number; out_degree: number
  weighted_out_dependency: number; betweenness: number; pagerank_dependedness: number; downstream_reach: number
}
export interface EntityImpactPayload {
  scenario_id: string; impact: EntityImpact
  incoming_transmission: { supplier_id: string; supplier: string; product: string; supplier_disruption: number; transmission: number; passed_shock: number; dependency: number }[]
  systemic: SystemicRow; dominant_paths: CriticalPath[]
}
export type InterventionType = 'inventory_buffer' | 'supplier_diversification' | 'input_substitution' | 'facility_protection' | 'cold_chain_resilience' | 'relocate_storage'
export interface Intervention { type: InterventionType; entity_ids: string[]; magnitude?: number | null; label?: string }
export interface MitigationOption {
  label: string; types: string[]
  effect: { baseline_loss_musd: number; mitigated_loss_musd: number; loss_reduction_musd: number; loss_reduction_fraction: number | null; baseline_direct_musd: number; mitigated_direct_musd: number; baseline_indirect_musd: number; mitigated_indirect_musd: number }
  cost: { capex_musd: number; annual_opex_musd: number; annualised_cost_musd: number; time_months: number; feasibility: number; estimate_confidence: number; basis: string }
  annual_expected_benefit_musd: number; benefit_cost_ratio: number | null; bcr_low: number | null; bcr_high: number | null
  net_present_style_value_musd: number; notes: { target: string; product: string; note: string; shifted_musd: number }[]
  interventions: Intervention[]
  priority_score?: number; priority_components?: Record<string, number>
}
export interface MitigationResult {
  scenario_id: string; baseline: { total_loss_musd: number; direct_loss_musd: number; indirect_loss_musd: number }
  options: MitigationOption[]; combined: MitigationOption | null; priority_weights: Record<string, number>
  assumptions: string[]; annual_event_probability: number; candidates_evaluated?: number
}
export interface Metadata {
  name: string; version: string; domain: string; domain_note: string; n_entities: number; n_relations: number
  entity_types: string[]; food_categories: string[]; countries: string[]
  hazards: { hazard_type: string; k: number; tau: number; recovery: number }[]
  hazard_providers: { name: string; synthetic: boolean; description: string; limitations: string }[]
  unavailable_integrations: string[]; model_status: { calibrated: boolean; validated: boolean; note: string }
}

export interface HoldingMeta {
  entity_id: string; name: string; weight: number; entity_type: string; country?: string | null; kind?: HoldingKind; primary_entity_id?: string
  other_businesses_share?: number; pattern?: string | null
  segments?: { entity_id: string; name: string; segment: string; share: number; entity_type: string; country: string | null }[]
}
export interface Portfolio { name: string; synthetic: boolean; weighting: string; holding_view?: HoldingView; n_business_units?: number; n_multi_segment?: number; holdings: HoldingMeta[] }
export interface FinderRequest {
  hazards?: ('flood' | 'heat' | 'drought')[]; intensity?: number; radii_km?: number[]; min_vulnerability?: number; top_k?: number
  shortlist?: number; stability_draws?: number; seed?: number; include_pairs?: boolean; max_depth?: number; weights?: Record<string, number>
  holding_view?: HoldingView
}
export interface HoldingImpact extends CompanyStructure {
  entity_id: string; name: string; weight: number; direct_disruption: number; network_disruption: number; segments?: SegmentRow[] | null
}
export interface StructureView {
  view: 'business_unit' | 'company' | 'company_if_other_hit' | 'company_one_node'; label: string; n_holdings: number; n_distinct_events: number
  n_hidden_only: number; top_hidden_only: { id: string; label: string; impact: number } | null; mean_top10_impact: number
}
export interface StructureComparison { views: StructureView[]; n_multi_segment: number; multi_segment_holdings: string[]; hidden_only_events_on_own_sites: number | null; note: string }
export interface FinderEvent {
  rank: number; id: string; kind: 'node' | 'footprint'; hazard: string; label: string; origin_id: string | null; country: string | null; region: string | null
  portfolio_network_impact: number; portfolio_location_impact: number; hidden_share: number; hidden_only: boolean; variants: number
  holdings_affected: number; entities_hit_directly: number; top_holdings: HoldingImpact[]
  p_top5: number | null; median_rank: number | null; rank_iqr: number[] | null; fragile: boolean | null; hazard_component: Hazard
  jrc_flood_check?: string | null
  portfolio_network_impact_if_other_hit?: number | null; portfolio_network_impact_one_node?: number | null
}
export interface FinderResult {
  n_events: number; n_node_events: number; n_footprint_events: number; n_distinct_events: number; n_hidden_only: number; runtime_seconds: number
  events: FinderEvent[]; hidden_only_events: FinderEvent[]; hidden_share_curve: { threshold: number; events: number }[]
  holdings: HoldingMeta[]
  matrix: { entity_id: string; name: string; entity_type: string; worst_event_id: string; total: number; holdings_reached: number; values: Record<string, number> }[]
  single_points_of_failure: { entity_id: string; name: string; entity_type: string; holdings: HoldingImpact[]; is_holding: boolean }[]
  structural_bound: { n_pairs: number; method: string; top: { entities: string[]; impact: number }[]; greedy: { entities: string[]; impact: number }; greedy_matches: boolean; note: string } | null
  stability: { n_draws: number; seed: number; shortlist: number; kendall_tau_top20: number | null; kendall_tau_top20_hidden_only: number | null; note: string } | null
  hazard_layer?: { name: string; citation: string; licence: string; source: string; retrieved: string; mode: string; flood_events_checked: number
    flood_events_without_modelled_flooding: number; top20_flood_events_consistent: number; top20_flood_events: number
    entities_total?: number; entities_with_any_flooding?: number; entities_window_clipped?: number; caveat: string } | null
  parameters: Record<string, unknown>; units: Record<string, string>; assumptions: string[]; limitations: string[]
  holding_view?: HoldingView; structure_comparison?: StructureComparison | null
}
export interface OptimiseRequest {
  budget_musd: number; finder?: FinderRequest; tail_events?: number; candidates?: Intervention[]; max_candidates?: number
  exhaustive_check?: boolean; robustness_draws?: number; seed?: number
}
export interface OptimiseCandidate { label: string; type: string; entity_ids: string[]; magnitude: number | null; annualised_cost_musd: number; single_reduction: number }
export interface OptimiseResult {
  budget_musd: number; tail_events: number; n_events: number; baseline_objective: number; plan_objective: number; reduction: number
  reduction_fraction: number | null; greedy_objective: number; local_search_improved: boolean; plan: OptimiseCandidate[]; plan_cost_musd: number
  plan_interventions: Intervention[]; candidates: OptimiseCandidate[]; frontier: { label: string; cumulative_cost_musd: number; objective: number }[]
  exhaustive: { pool_size: number; pool_note: string; n_feasible_plans: number; best_objective: number; best_plan: string[]; optimality_gap: number | null; note: string } | null
  cost_sensitivity: { cost_factor: number; plan: string[]; objective: number; jaccard_with_base: number }[]
  robustness: { n_draws: number; seed: number; median_reduction: number; p05: number; p95: number; share_positive: number } | null
  evaluations: number; runtime_seconds: number; method: string; units: Record<string, string>; assumptions: string[]
}

export type Provenance = 'synthetic_input' | 'model_assumption' | 'real_hazard_context' | 'unvalidated_model_output' | 'model_robustness' | 'empirically_validated'
export type CopilotFocus =
  | { kind: 'finder_event'; event_id: string; finder: FinderRequest }
  | { kind: 'scenario'; scenario_id: string; max_depth?: number | null; holding_view?: HoldingView }
  | { kind: 'mitigation_plan'; optimise: OptimiseRequest }
export interface CopilotFact { id: string; label: string; value: string | number | boolean | null; rendered: string; unit: string; provenance: Provenance; source: string }
export interface CopilotSentence { text: string; cites: string[]; provenance: Provenance[]; template: boolean }
export interface CopilotAnswer {
  title: string; question: string; mode: 'llm' | 'deterministic'; provider: string; model: string | null; fallback_reason: string | null; latency_ms: number
  sections: Record<string, CopilotSentence[]>; unsupported: string[]; standing_notes: string[]; facts: CopilotFact[]
  validation: { attempted?: boolean; accepted?: boolean; violations?: string[]; details?: string[]; sentences_checked?: number; sentences_failed?: number }
}
export interface CopilotReport { title: string; mode: 'llm' | 'deterministic'; fallback_reason: string | null; markdown: string }
export interface CopilotStatus {
  configured_provider: string; deterministic: boolean
  ollama: { reachable: boolean; model: string; model_present: boolean; url?: string }; anthropic: { configured: boolean; model: string }
}
