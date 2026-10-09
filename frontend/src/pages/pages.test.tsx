import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { AppProvider } from '../state/AppState'
import { mockFetch } from '../test/fixtures'

vi.mock('../components/GraphView', async () => {
  const actual = await vi.importActual<typeof import('../components/GraphView')>('../components/GraphView')
  const React = await import('react')
  const Mock = React.forwardRef<unknown, { visible: Set<string>; onSelect: (id: string) => void }>(({ visible, onSelect }, _ref) => (
    <div data-testid="graph-canvas">{[...visible].map((id) => <button key={id} onClick={() => onSelect(id)}>{`node:${id}`}</button>)}</div>
  ))
  return { ...actual, default: Mock }
})
// Recharts needs layout; stub the responsive container.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div style={{ width: 400, height: 300 }}>{children}</div> }
})

const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><AppProvider><App /></AppProvider></MemoryRouter>)
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }) })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Overview', () => {
  it('shows KPIs sourced from the backend response', async () => {
    vi.stubGlobal('fetch', mockFetch())
    renderAt('/')
    expect(await screen.findByText('Test Flood', { selector: 'h1' })).toBeInTheDocument()
    const kpis = await screen.findAllByTestId('kpi')
    const text = kpis.map((k) => k.textContent).join(' | ')
    expect(text).toContain('$5M')    // direct
    expect(text).toContain('$7M')    // network-aware
    expect(screen.getByText('Test Flour Mill')).toBeInTheDocument()
    expect(screen.getAllByText(/Synthetic/i).length).toBeGreaterThan(0)
  })
  it('renders an error state with retry when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('down') }))
    renderAt('/')
    expect(await screen.findByRole('alert')).toHaveTextContent(/Cannot reach the backend/)
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })
})

describe('Network page', () => {
  it('filters nodes by search and status, and selection updates the detail panel', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', mockFetch({
      '/api/v1/entities/mill': () => new Response(JSON.stringify({ id: 'mill', name: 'Test Flour Mill', entity_type: 'processor', region: 'R', country: 'India', output_product: 'flour', inventory_days: 10, alternative_supplier_availability: 0.3, in_degree: 1, out_degree: 0, single_source_inputs: [], confidence: 'low' }), { headers: { 'Content-Type': 'application/json' } }),
      '/api/v1/entities/mill/impact': () => new Response(JSON.stringify({ scenario_id: 'sc_test', impact: {}, incoming_transmission: [], systemic: {}, dominant_paths: [] }), { headers: { 'Content-Type': 'application/json' } }),
    }))
    renderAt('/network')
    await screen.findByText('node:farm')
    expect(screen.getByTestId('visible-count')).toHaveTextContent('4 of 4')
    await user.type(screen.getByLabelText('Search'), 'roaster')
    expect(screen.getByTestId('visible-count')).toHaveTextContent('1 of 4')
    await user.clear(screen.getByLabelText('Search'))
    await user.selectOptions(screen.getByLabelText('Risk status'), 'direct')
    expect(screen.getByTestId('visible-count')).toHaveTextContent('1 of 4')
    expect(screen.queryByText('node:mill')).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Risk status'), 'propagated')
    await user.click(await screen.findByText('node:mill'))
    const panel = screen.getByTestId('detail-panel')
    await waitFor(() => expect(within(panel).getByTestId('detail-name')).toHaveTextContent('Test Flour Mill'))
    expect(within(panel).getByText('First-order')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /reset filters/i }))
    expect(screen.getByTestId('visible-count')).toHaveTextContent('4 of 4')
  })
})

describe('Scenario builder', () => {
  it('disables the run button until the draft is valid and lists problems', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', mockFetch())
    renderAt('/scenario')
    await screen.findByDisplayValue('Test Flood (copy)')
    const run = screen.getByRole('button', { name: 'Run analysis' })
    expect(run).toBeEnabled()
    await user.clear(screen.getByLabelText('Scenario name'))
    expect(run).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(/name is required/i)
  })
})

describe('Results empty/uncertainty states', () => {
  it('prompts to run Monte Carlo and shows results after the call', async () => {
    const user = userEvent.setup()
    const mc = { n_simulations: 500, seed: 42, total_loss: { mean: 7, median: 6.5, p05: 4, p25: 5, p75: 8, p95: 10, min: 3, max: 12 }, direct_loss: { mean: 5, median: 5, p05: 3, p25: 4, p75: 6, p95: 7, min: 2, max: 8 }, indirect_loss: { mean: 2, median: 1.5, p05: 0.5, p25: 1, p75: 2, p95: 3, min: 0, max: 4 }, network_minus_location: { mean: 2, median: 1.5, p05: 0.5, p25: 1, p75: 2, p95: 3, min: 0, max: 4 }, histogram: [{ lo: 3, hi: 5, count: 100 }, { lo: 5, hi: 7, count: 400 }], sensitivity: [{ parameter: 'vulnerability', spearman_with_total_loss: 0.8, description: '' }], top_entities: [], assumptions: ['x'], interpretation: 'Not a formal confidence interval.', deterministic_total_loss_musd: 7 }
    vi.stubGlobal('fetch', mockFetch({ '/api/v1/analysis/monte-carlo': () => new Response(JSON.stringify(mc), { headers: { 'Content-Type': 'application/json' } }) }))
    renderAt('/results')
    expect(await screen.findByText(/Run the analysis to see the loss distribution/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /run uncertainty analysis/i }))
    expect(await screen.findByText('Median total loss')).toBeInTheDocument()
    expect(screen.getByText(/Scenario-uncertainty range/)).toBeInTheDocument()
  })
})

describe('Audit regressions', () => {
  it('preselects the entity from ?select= and shows it in the detail panel', async () => {
    vi.stubGlobal('fetch', mockFetch())
    renderAt('/network?select=mill')
    const panel = await screen.findByTestId('detail-panel')
    await waitFor(() => expect(within(panel).getByTestId('detail-name')).toHaveTextContent('Test Flour Mill'))
  })
  it('restores the previously active scenario from storage', async () => {
    const store: Record<string, string> = { 'fin04.activeScenario': 'sc_test' }
    vi.stubGlobal('localStorage', { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => { store[k] = v } })
    vi.stubGlobal('fetch', mockFetch())
    renderAt('/')
    expect(await screen.findByText('Test Flood', { selector: 'h1' })).toBeInTheDocument()
    expect(store['fin04.activeScenario']).toBe('sc_test')
  })
  it('shows fractional tie ranks and hidden-exposure badges in the comparison table', async () => {
    const run2 = JSON.parse(JSON.stringify((await import('../test/fixtures')).run))
    run2.comparison.portfolio_rows = [{ entity_id: 'bakery', name: 'Test Bakery', location_disruption: 0, network_disruption: 0.08, location_loss_musd: 0, network_loss_musd: 1, rank_location: 9.5, rank_network: 1, rank_change: 8.5, hidden_exposure: true }]
    vi.stubGlobal('fetch', mockFetch({ '/api/v1/scenarios/sc_test/run': () => new Response(JSON.stringify(run2), { headers: { 'Content-Type': 'application/json' } }) }))
    renderAt('/results')
    expect(await screen.findByText('▲ 8.5')).toBeInTheDocument()
    expect(screen.getByText('9.5')).toBeInTheDocument()
    expect(screen.getByText('Hidden exposure')).toBeInTheDocument()
  })
})
