import type { GraphPayload, Metadata, RunResult, ScenarioRecord } from '../api/types'

const node = (id: string, name: string, entity_type: string, food_category: string, country: string) => ({
  id, name, entity_type, food_category, output_product: 'flour', country, region: 'R', latitude: 1, longitude: 1, synthetic: true,
  operational_criticality: 0.5, value_added_musd: 50, inventory_days: 10, confidence: 'low', in_demo_portfolio: false,
})
export const graph: GraphPayload = {
  nodes: [node('farm', 'Test Wheat Farm', 'agricultural_producer', 'grains', 'India'), node('mill', 'Test Flour Mill', 'processor', 'grains', 'India'),
    node('bakery', 'Test Bakery', 'manufacturer', 'grains', 'United Kingdom'), node('cafe', 'Test Coffee Roaster', 'manufacturer', 'coffee', 'Germany')],
  edges: [{ id: 'farm->mill', source: 'farm', target: 'mill', product: 'wheat_grain', channel: 'supply', relationship_type: 'raw_material_supply', dependency: 0.7, input_specificity: 0.9, substitutability: 0.3, storable: true, lead_time_days: 2, annual_flow_musd: 10, distance_km: 5, status: 'synthetic', confidence: 0.5 }],
  n_nodes: 4, n_edges: 1, edge_semantics: '', structure: { n_nodes: 4, n_edges: 1, weak_component_sizes: [2, 1, 1], largest_component_share: 0.5, cycles: [], single_source_dependencies: [], is_dag: true },
}
export const scenarios: ScenarioRecord[] = [{
  id: 'sc_test', name: 'Test Flood', description: 'A test', builtin: true, synthetic: true, time_horizon_year: 2035, data_source: 'synthetic_footprint',
  propagation_max_depth: 6, inventory_scale: 1, substitution_scale: 1, dependency_scale: 1, compound_amplification: 0, monte_carlo_runs: 500, monte_carlo_seed: 42,
  hazards: [{ hazard_type: 'flood', intensity: 0.7, duration_days: 14, center_lat: 1, center_lon: 1, radius_km: 100, regions: [], affected_entity_ids: [], label: 'Flood' }],
}]
const impact = (entity_id: string, name: string, status: 'direct' | 'propagated' | 'unaffected', hop: number | null, d: number) => ({
  entity_id, name, entity_type: 'processor', food_category: 'grains', country: 'India', region: 'R', synthetic: true, status, hazard_intensity: 0.5,
  direct_disruption: status === 'direct' ? d : 0, final_disruption: d, hop_order: hop, value_added_musd: 50, direct_loss_musd: status === 'direct' ? 5 : 0,
  indirect_loss_musd: status === 'propagated' ? 2 : 0, total_loss_musd: status === 'unaffected' ? 0 : status === 'direct' ? 5 : 2, loss_by_order_musd: {}, evidence_label: 'label',
})
export const run: RunResult = {
  scenario: scenarios[0], scenario_id: 'sc_test',
  summary: { n_entities: 4, n_exposed_facilities: 1, n_affected_downstream: 1, direct_loss_musd: 5, indirect_loss_musd: 2, total_loss_musd: 7, indirect_to_direct_ratio: 0.4, iterations: 3, converged: true, effective_duration_days: 35, loss_period_fraction: 0.1, max_depth_used: 6 },
  orders: [{ order: 'direct', label: 'Direct impact', entities: 1, loss_musd: 5, evidence: 'e' }, { order: '1', label: 'First-order', entities: 1, loss_musd: 2, evidence: 'e1' },
    { order: '2', label: 'Second-order', entities: 0, loss_musd: 0, evidence: 'e2' }, { order: '3', label: 'Third-order', entities: 0, loss_musd: 0, evidence: 'e3' }],
  entities: [impact('farm', 'Test Wheat Farm', 'direct', 0, 0.6), impact('mill', 'Test Flour Mill', 'propagated', 1, 0.2), impact('bakery', 'Test Bakery', 'unaffected', null, 0), impact('cafe', 'Test Coffee Roaster', 'unaffected', null, 0)],
  by_food_category: [], by_entity_type: [], by_region: [], critical_paths: [],
  comparison: { location_only_loss_musd: 5, network_aware_loss_musd: 7, absolute_difference_musd: 2, relative_difference: 0.4, portfolio_location_loss_musd: 0, portfolio_network_loss_musd: 0, portfolio_absolute_difference_musd: 0, portfolio_relative_difference: null, portfolio_rows: [], hidden_exposure_count: 0, scope_note: 's' },
  bottlenecks: [{ entity_id: 'mill', name: 'Test Flour Mill', score: 55.5, downstream_reach: 3, betweenness: 0.12, out_degree: 3, weighted_out_dependency: 1.4, note: '' }],
  assumptions: ['a'], limitations: ['Synthetic limitation'], units: {},
}
export const metadata: Metadata = {
  name: 'x', version: '0', domain: 'food_and_beverage', domain_note: '', n_entities: 4, n_relations: 1, entity_types: ['agricultural_producer', 'processor', 'manufacturer'],
  food_categories: ['grains', 'coffee'], countries: ['India', 'Germany', 'United Kingdom'], hazards: [], hazard_providers: [], unavailable_integrations: [],
  model_status: { calibrated: false, validated: false, note: '' },
}
export function mockFetch(overrides: Record<string, () => Response | Promise<Response>> = {}) {
  const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'Content-Type': 'application/json' } })
  const routes: Record<string, () => Response | Promise<Response>> = {
    '/api/v1/metadata': () => json(metadata), '/api/v1/graph': () => json(graph), '/api/v1/scenarios': () => json({ items: scenarios, total: 1 }),
    '/api/v1/scenarios/sc_test/run': () => json(run), ...overrides,
  }
  return vi.fn(async (url: string) => {
    const key = Object.keys(routes).find((k) => url.split('?')[0] === k)
    if (!key) return json({ detail: `no mock for ${url}` }, 404)
    return routes[key]()
  })
}
