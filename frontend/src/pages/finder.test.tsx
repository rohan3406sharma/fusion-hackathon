import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { AppProvider } from '../state/AppState'
import { finderResult, mockFetch, optimiseResult, scenarios } from '../test/fixtures'

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div style={{ width: 400, height: 300 }}>{children}</div> }
})
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'Content-Type': 'application/json' } })
const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><AppProvider><App /></AppProvider></MemoryRouter>)
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }) })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Hidden exposure finder', () => {
  it('ranks hidden-only events, sorts by reach and flags fragile ranks', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', mockFetch({ '/api/v1/analysis/reverse-stress': () => json(finderResult) }))
    renderAt('/finder')
    const table = await screen.findByTestId('hidden-table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Flood at Test Port')
    expect(rows[1]).toHaveTextContent('Fragile')
    await user.selectOptions(screen.getByLabelText('Sort events'), 'reach')
    expect(within(screen.getByTestId('hidden-table')).getAllByRole('row')[1]).toHaveTextContent('Heat at Test Grid')
    await user.click(screen.getByRole('button', { name: 'All events' }))
    expect(screen.getByTestId('event-table')).toHaveTextContent('Drought around Test Region')
    expect(screen.getByTestId('exposure-matrix')).toHaveTextContent('Test Flour Mill')
    expect(screen.getByText(/Exhaustive search over 10 pairs/)).toBeInTheDocument()
  })

  it('opens an event as a scenario and runs the optimiser', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      '/api/v1/analysis/reverse-stress': () => json(finderResult),
      '/api/v1/analysis/reverse-stress/promote': () => json({ ...scenarios[0], id: 'sc_test', name: 'Finder: Flood at Test Port' }, 201),
      '/api/v1/mitigation/optimise': () => json(optimiseResult),
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/finder')
    await screen.findByTestId('hidden-table')
    await user.click(screen.getByRole('button', { name: 'Optimise' }))
    const out = await screen.findByTestId('optimiser-result')
    expect(out).toHaveTextContent('Protect Test Flour Mill')
    expect(out).toHaveTextContent('brute force over 31 feasible plans')
    await user.click(screen.getAllByRole('button', { name: 'Open as scenario' })[0])
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/reverse-stress/promote'))).toBe(true))
    expect(await screen.findByText(/Scenario results/i, { selector: 'p' })).toBeInTheDocument()
  })

  it('shows companies with their business units and re-runs everything when the holding view switches', async () => {
    const user = userEvent.setup()
    const store: Record<string, string> = {}
    vi.stubGlobal('localStorage', { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => { store[k] = v } })
    const company = {
      entity_id: 'co_test', name: 'Test Consumer Group', weight: 0.5, direct_disruption: 0, network_disruption: 0.12, kind: 'multi_segment', primary_entity_id: 'bakery',
      other_businesses_share: 0.5, network_disruption_if_other_hit: 0.24, network_disruption_one_node: 0.4,
      segments: [{ entity_id: 'bakery', name: 'Test Bakery', segment: 'Bakery', share: 0.3, direct_disruption: 0, network_disruption: 0.4 },
        { entity_id: 'cafe', name: 'Test Coffee Roaster', segment: 'Coffee', share: 0.2, direct_disruption: 0, network_disruption: 0 }],
    }
    const view = (v: string, n: number, ho: number, mean: number) => ({ view: v, label: v, n_holdings: n, n_distinct_events: 268, n_hidden_only: ho, top_hidden_only: { id: 'h1', label: 'Flood at Test Port', impact: 0.0106 }, mean_top10_impact: mean })
    const res = {
      ...finderResult, holding_view: 'company',
      hidden_only_events: finderResult.hidden_only_events.map((e, i) => (i === 0 ? { ...e, top_holdings: [company] } : e)),
      structure_comparison: { views: [view('business_unit', 3, 165, 0.0325), view('company', 2, 152, 0.0323), view('company_if_other_hit', 2, 152, 0.0324), view('company_one_node', 2, 153, 0.0404)],
        n_multi_segment: 1, multi_segment_holdings: ['Test Consumer Group'], hidden_only_events_on_own_sites: 13, note: 'Same events, same engine.' },
    }
    const fetchMock = mockFetch({ '/api/v1/analysis/reverse-stress': () => json(res) })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/finder')
    const table = await screen.findByTestId('structure-table')
    expect(table).toHaveTextContent('Business units (v0.3)')
    for (const t of ['165', '152', '153', '4.04%', '3.23%']) expect(table).toHaveTextContent(t)
    const box = screen.getByTestId('company-breakdown')
    expect(box).toHaveTextContent('Test Consumer Group')
    expect(box).toHaveTextContent('company 12.0% · up to 24.0% if its non-F&B businesses were hit as hard · 40.0% as one node')
    expect(box).toHaveTextContent('Outside food & beverage: 50% of value added · not modelled')
    expect(within(box).getByRole('link', { name: 'Bakery' })).toHaveAttribute('href', '/entity/bakery')
    expect(screen.getByText(/hit a unit the company itself owns/)).toHaveTextContent('13')
    const calls = () => fetchMock.mock.calls as unknown as [string, RequestInit | undefined][]     // the mock declares only the URL
    const bodies = (path: string) => calls().filter(([u, init]) => u.includes(path) && init?.body).map(([, init]) => JSON.parse(String(init?.body)))
    expect(bodies('/reverse-stress')[0].holding_view).toBe('company')
    expect(screen.getByRole('button', { name: 'Companies' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'Business units' }))
    await waitFor(() => expect(bodies('/reverse-stress').some((b) => b.holding_view === 'business_unit')).toBe(true))
    await waitFor(() => expect(bodies('/run').some((b) => b.holding_view === 'business_unit')).toBe(true))
    expect(store['fin04.holdingView']).toBe('business_unit')
  })

  it('shows an error when the search fails', async () => {
    vi.stubGlobal('fetch', mockFetch({ '/api/v1/analysis/reverse-stress': () => json({ detail: 'unknown holdings in weights' }, 422) }))
    renderAt('/finder')
    expect(await screen.findByRole('alert')).toHaveTextContent('unknown holdings in weights')
  })
})
