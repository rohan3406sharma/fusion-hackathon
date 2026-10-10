import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CopilotPanel from './CopilotPanel'
import type { CopilotAnswer, CopilotFocus, Provenance } from '../api/types'

const downloads: { name: string; text: string }[] = []
vi.mock('../lib/export', async () => ({ ...(await vi.importActual<object>('../lib/export')), downloadText: (name: string, text: string) => downloads.push({ name, text }) }))

const focus: CopilotFocus = { kind: 'finder_event', event_id: 'node:grid_nl:drought', finder: {} }
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'Content-Type': 'application/json' } })
const sent = (text: string, prov: Provenance[], template = false, cites = ['impact_network']) => ({ text, cites, provenance: prov, template })
const answer = (over: Partial<CopilotAnswer> = {}): CopilotAnswer => ({
  title: 'Hidden exposure: Drought at Dutch Regional Grid Operator', question: 'q', mode: 'llm', provider: 'ollama', model: 'qwen3:8b', fallback_reason: null, latency_ms: 12300,
  sections: {
    answer: [sent('Drought at Dutch Regional Grid Operator takes 1.13% of annual value added in the model.', ['unvalidated_model_output'])],
    mitigations: [sent('In the model, Protect the grid lowers the scenario loss by $53.1M (modelled value, not validated).', ['model_assumption', 'unvalidated_model_output'])],
    uncertainty: [sent('The ranking is robust under the draws: 100% of 200.', ['model_robustness'], true, ['p_top5']), sent('No empirical validation exists.', ['model_assumption'], true, ['notice_unvalidated'])],
  },
  unsupported: [], standing_notes: ['n1', 'A language model, when used, only chooses and phrases cited facts; every value, name and path is filled in by the server.'],
  facts: [{ id: 'impact_network', label: 'Portfolio impact, network-aware', value: 0.0113, rendered: '1.13%', unit: '% of annual value added', provenance: 'unvalidated_model_output', source: 'events[].portfolio_network_impact' },
    { id: 'p_top5', label: 'Share of draws in the top 5', value: 1, rendered: '100%', unit: '%', provenance: 'model_robustness', source: 'events[].p_top5' },
    { id: 'notice_unvalidated', label: 'Validation status', value: 'x', rendered: 'x', unit: 'text', provenance: 'model_assumption', source: 'METHODOLOGY.md' }],
  validation: { attempted: true, accepted: true, violations: [] }, ...over,
})
const status = (ready: boolean) => ({ configured_provider: ready ? 'ollama' : 'deterministic', deterministic: true, ollama: { reachable: ready, model: 'qwen3:8b', model_present: ready }, anthropic: { configured: false, model: 'claude-haiku-5-5' } })
function stub(routes: Record<string, () => Response | Promise<Response>>) {
  const f = vi.fn(async (url: string) => { const k = Object.keys(routes).find((r) => String(url).endsWith(r)); return k ? routes[k]() : json({ detail: 'no mock' }, 404) })
  vi.stubGlobal('fetch', f); return f
}
beforeEach(() => { downloads.length = 0 })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('CopilotPanel', () => {
  it('shows a loading state, then the grounded answer with provenance chips, mode badge and evidence', async () => {
    const user = userEvent.setup()
    let release: (r: Response) => void = () => undefined
    stub({ '/copilot/status': () => json(status(true)), '/copilot/ask': () => new Promise<Response>((res) => { release = res }) })
    render(<CopilotPanel focus={focus} />)
    expect(await screen.findByText(/Local model ready/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Ask$/ }))
    expect(await screen.findByTestId('copilot-loading')).toHaveTextContent(/first request can take up to about 90 seconds/)
    expect(screen.getByRole('button', { name: /Reading the evidence/ })).toBeDisabled()
    release(json(answer()))
    const out = await screen.findByTestId('copilot-answer')
    expect(within(out).getByText(/Language-model phrasing, validated \(qwen3:8b\)/)).toBeInTheDocument()
    expect(within(out).getByText(/takes 1.13% of annual value added/)).toBeInTheDocument()
    expect(within(out).getAllByText('Unvalidated model output').length).toBeGreaterThan(0)
    expect(within(out).getAllByText('Ranking stability under draws').length).toBeGreaterThan(0)
    expect(within(out).getByText(/modelled value, not validated/)).toBeInTheDocument()
    await user.click(within(out).getAllByText(/evidence \(1\)/)[0])
    expect(within(out).getAllByText('events[].portfolio_network_impact').length).toBeGreaterThanOrEqual(2)    // inline evidence + the evidence table
  })

  it('says plainly when it fell back to templates and why', async () => {
    const user = userEvent.setup()
    stub({ '/copilot/status': () => json(status(true)), '/copilot/ask': () => json(answer({ mode: 'deterministic', provider: 'deterministic', model: null, fallback_reason: 'model reply failed grounding validation: literal_number' })) })
    render(<CopilotPanel focus={focus} />)
    await user.click(await screen.findByRole('button', { name: /^Ask$/ }))
    expect(await screen.findByText('Deterministic template')).toBeInTheDocument()
    expect(screen.getByTestId('copilot-fallback')).toHaveTextContent('literal_number')
  })

  it('shows the unavailable-model state without blocking the feature', async () => {
    const user = userEvent.setup()
    stub({ '/copilot/status': () => json(status(false)), '/copilot/ask': () => json(answer({ mode: 'deterministic', fallback_reason: 'deterministic provider selected' })) })
    render(<CopilotPanel focus={focus} />)
    expect(await screen.findByTestId('copilot-status')).toHaveTextContent(/Language model not available · deterministic templates in use/)
    expect(screen.getByRole('checkbox')).toBeDisabled()                                       // cannot ask for model phrasing when none exists
    await user.click(screen.getByRole('button', { name: /^Ask$/ }))
    expect(await screen.findByTestId('copilot-answer')).toBeInTheDocument()
  })

  it('lists what the model declined to answer', async () => {
    const user = userEvent.setup()
    stub({ '/copilot/status': () => json(status(true)), '/copilot/ask': () => json(answer({ unsupported: ['The model has no event probabilities, so it cannot say how likely this event is.', 'No empirical validation exists: the model has not been checked against observed disruptions or losses.'] })) })
    render(<CopilotPanel focus={focus} />)
    await user.click(await screen.findByRole('button', { name: /^Ask$/ }))
    const list = await screen.findByTestId('copilot-unsupported')
    expect(list).toHaveTextContent('no event probabilities'); expect(list).toHaveTextContent('No empirical validation')
  })

  it('shows API errors with retry, and a timeout message', async () => {
    const user = userEvent.setup()
    let n = 0
    stub({ '/copilot/status': () => json(status(true)), '/copilot/ask': () => (n++ === 0 ? json({ detail: "event 'x' is not in the finder results for these settings" }, 404) : json(answer())) })
    render(<CopilotPanel focus={focus} />)
    await user.click(await screen.findByRole('button', { name: /^Ask$/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('is not in the finder results')
    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByTestId('copilot-answer')).toBeInTheDocument()
  })

  it('clears the old answer when the focus changes, and guards empty questions and a missing focus', async () => {
    const user = userEvent.setup()
    stub({ '/copilot/status': () => json(status(true)), '/copilot/ask': () => json(answer()) })
    const { rerender } = render(<CopilotPanel focus={focus} />)
    await user.click(await screen.findByRole('button', { name: /^Ask$/ }))
    await screen.findByTestId('copilot-answer')
    rerender(<CopilotPanel focus={{ ...focus, event_id: 'node:other:flood' }} />)
    await waitFor(() => expect(screen.queryByTestId('copilot-answer')).not.toBeInTheDocument())
    await user.clear(screen.getByLabelText('Your question'))
    expect(screen.getByRole('button', { name: /^Ask$/ })).toBeDisabled()
    rerender(<CopilotPanel focus={null} />)
    expect(screen.getByText(/Choose an event, scenario or plan/)).toBeInTheDocument()
  })

  it('produces an executive summary and downloads it as Markdown', async () => {
    const user = userEvent.setup()
    const md = '# Executive summary: Hidden exposure\n\n## Evidence table\n\n| Fact |\n'
    const f = stub({ '/copilot/status': () => json(status(true)), '/copilot/report': () => json({ title: 'Hidden exposure: Drought at Dutch Regional Grid Operator', mode: 'deterministic', fallback_reason: null, markdown: md }) })
    render(<CopilotPanel focus={focus} />)
    await user.click(await screen.findByRole('button', { name: /Executive summary/ }))
    const rep = await screen.findByTestId('copilot-report')
    expect(rep).toHaveTextContent('Evidence table'); expect(rep).toHaveTextContent('Deterministic template')
    const call = (f.mock.calls as unknown as [string, RequestInit][]).find(([u]) => String(u).endsWith('/copilot/report'))!
    expect(JSON.parse(String(call[1].body)).use_model).toBe(false)
    await user.click(screen.getByRole('button', { name: /Download .md/ }))
    expect(downloads).toHaveLength(1); expect(downloads[0].name).toMatch(/\.md$/); expect(downloads[0].text).toBe(md)
  })
})
