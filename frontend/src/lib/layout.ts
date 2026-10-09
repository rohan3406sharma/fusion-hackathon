import type { GraphNode } from '../api/types'

const COLUMN: Record<string, number> = {
  agricultural_input: 0, utility: 0, agricultural_producer: 1, processor: 2, packaging_supplier: 3, manufacturer: 4,
  cold_storage: 5, transport_operator: 5, port_hub: 5, distribution_centre: 6, wholesaler: 6, retailer: 7, financial: 0,
}
export const TIER_LABELS = ['Inputs & utilities', 'Agricultural production', 'Processing', 'Packaging', 'Manufacturing', 'Logistics & storage', 'Distribution', 'Retail']

/** Deterministic tiered layout: x by supply-chain stage, y by food category then country (keeps chains visually together). */
export function tieredLayout(nodes: GraphNode[], width = 1000, height = 760): Record<string, { x: number; y: number }> {
  const cols: GraphNode[][] = TIER_LABELS.map(() => [])
  nodes.forEach((n) => cols[COLUMN[n.entity_type] ?? 4].push(n))
  const pos: Record<string, { x: number; y: number }> = {}
  cols.forEach((col, ci) => {
    col.sort((a, b) => a.food_category.localeCompare(b.food_category) || (a.country ?? '').localeCompare(b.country ?? '') || a.name.localeCompare(b.name))
    const gap = height / Math.max(col.length, 1)
    col.forEach((n, i) => { pos[n.id] = { x: (ci / (TIER_LABELS.length - 1)) * width, y: gap * (i + 0.5) + (ci % 2) * 8 } })
  })
  return pos
}
