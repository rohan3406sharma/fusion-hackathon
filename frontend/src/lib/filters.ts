import type { EntityImpact, GraphNode, Status } from '../api/types'

export interface NodeFilters { q: string; types: string[]; category: string; country: string; status: Status | 'all' }
export const EMPTY_FILTERS: NodeFilters = { q: '', types: [], category: '', country: '', status: 'all' }

export function filterNodes(nodes: GraphNode[], f: NodeFilters, impacts: Map<string, EntityImpact>): GraphNode[] {
  const q = f.q.trim().toLowerCase()
  return nodes.filter((n) => {
    if (q && !(n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || (n.output_product ?? '').includes(q) ||
      (n.region ?? '').toLowerCase().includes(q) || (n.country ?? '').toLowerCase().includes(q))) return false
    if (f.types.length && !f.types.includes(n.entity_type)) return false
    if (f.category && n.food_category !== f.category) return false
    if (f.country && n.country !== f.country) return false
    if (f.status !== 'all' && (impacts.get(n.id)?.status ?? 'unaffected') !== f.status) return false
    return true
  })
}
