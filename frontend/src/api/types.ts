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
export interface ComparisonRow {
  entity_id: string; name: string; location_disruption: number; network_disruption: number; location_loss_musd: number
  network_loss_musd: number; rank_location: number; rank_network: number; rank_change: number; hidden_exposure: boolean
}
export interface Comparison {
  location_only_loss_musd: number; network_aware_loss_musd: number; absolute_difference_musd: number; relative_difference: number | null
  portfolio_location_loss_musd: number; portfolio_network_loss_musd: number; portfolio_absolute_difference_musd: number
  portfolio_relative_difference: number | null; portfolio_rows: ComparisonRow[]; hidden_exposure_count: number; scope_note: string
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
  sensitivity: { parameter: string; spearman_with_total_loss: number; description: string }[]
  top_entities: { entity_id: string; name: string; median_loss_musd: number; p05_loss_musd: number; p95_loss_musd: number; probability_affected: number }[]
  assumptions: string[]; interpretation: string; deterministic_total_loss_musd: number
}
export interface EntityDetail extends GraphNode {
  facility_type: string | null; revenue_musd: number; capacity_tonnes_per_year: number | null; alternative_supplier_availability: number
  spare_capacity_fraction: number; exposed_asset_share: number | null; flood_vulnerability: number; heat_vulnerability: number
  drought_vulnerability: number; provenance: string; location_status: string; in_degree: number; out_degree: number
  supplier_concentration_hhi: number | null; single_source_inputs: string[]; missing_fields: string[]
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
