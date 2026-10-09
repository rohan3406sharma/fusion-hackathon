import { describe, expect, it } from 'vitest'
import { EMPTY_FILTERS, filterNodes } from './filters'
import { runToCsv } from './export'
import { fmtM, fmtPct, orderLabel } from './format'
import { tieredLayout } from './layout'
import { graph, run } from '../test/fixtures'
import { validateDraft } from '../pages/Builder'

const impacts = new Map(run.entities.map((e) => [e.entity_id, e]))

describe('filterNodes', () => {
  it('returns everything with empty filters', () => expect(filterNodes(graph.nodes, EMPTY_FILTERS, impacts)).toHaveLength(4))
  it('searches by name case-insensitively', () => expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, q: 'ROASTER' }, impacts).map((n) => n.id)).toEqual(['cafe']))
  it('filters by type, category and country', () => {
    expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, types: ['manufacturer'] }, impacts)).toHaveLength(2)
    expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, category: 'coffee' }, impacts)).toHaveLength(1)
    expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, country: 'India' }, impacts)).toHaveLength(2)
  })
  it('filters by risk status', () => {
    expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, status: 'direct' }, impacts).map((n) => n.id)).toEqual(['farm'])
    expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, status: 'unaffected' }, impacts)).toHaveLength(2)
  })
  it('combines filters with AND and can return empty', () => expect(filterNodes(graph.nodes, { ...EMPTY_FILTERS, q: 'bakery', status: 'direct' }, impacts)).toEqual([]))
})

describe('helpers', () => {
  it('formats', () => { expect(fmtM(1234.56)).toBe('$1,234.6M'); expect(fmtM(null)).toBe('—'); expect(fmtPct(0.256, 1)).toBe('25.6%'); expect(orderLabel(2)).toBe('Second-order'); expect(orderLabel(null)).toBe('Unaffected') })
  it('exports CSV with escaping', () => {
    const r = { ...run, entities: [{ ...run.entities[0], name: 'A, "quoted" name' }] }
    const csv = runToCsv(r)
    expect(csv.split('\n')[0].startsWith('scenario_id,scenario_name,data_status,entity_id,name')).toBe(true)
    expect(csv.split('\n')[1].startsWith('sc_test,Test Flood,synthetic,')).toBe(true)
    expect(csv).toContain('"A, ""quoted"" name"')
  })
  it('lays out every node in a distinct column/row', () => {
    const pos = tieredLayout(graph.nodes)
    expect(Object.keys(pos)).toHaveLength(4)
    expect(pos.farm.x).toBeLessThan(pos.mill.x)
    expect(pos.mill.x).toBeLessThan(pos.bakery.x)
  })
})

describe('scenario draft validation', () => {
  const ok = { hazard_type: 'flood' as const, intensity: 0.5, duration_days: 10, center_lat: 1, center_lon: 1, radius_km: 50, regions: [], affected_entity_ids: [], label: '', mode: 'footprint' as const }
  it('accepts a valid draft', () => expect(validateDraft('x', [ok])).toEqual([]))
  it('flags missing name, bad duration, empty selections', () => {
    expect(validateDraft('', [ok])).toHaveLength(1)
    expect(validateDraft('x', [{ ...ok, duration_days: 0 }])).toHaveLength(1)
    expect(validateDraft('x', [{ ...ok, mode: 'regions' }])).toHaveLength(1)
    expect(validateDraft('x', [{ ...ok, mode: 'entities' }])).toHaveLength(1)
    expect(validateDraft('x', [{ ...ok, radius_km: null }])).toHaveLength(1)
  })
})

import { fmtRank, plural } from './format'
describe('format helpers added in audit', () => {
  it('formats tie ranks and plurals', () => {
    expect(fmtRank(3)).toBe('3'); expect(fmtRank(9.5)).toBe('9.5')
    expect(plural(1, 'entity', 'entities')).toBe('1 entity'); expect(plural(0, 'entity', 'entities')).toBe('0 entities')
  })
})
