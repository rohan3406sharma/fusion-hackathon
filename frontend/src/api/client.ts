import type {
  Dependencies, EntityDetail, EntityImpactPayload, GraphPayload, Intervention, Metadata, MitigationResult,
  MonteCarloResult, RunResult, ScenarioRecord, ScenarioSpec, SystemicRow, CriticalPath, Portfolio, FinderRequest, FinderResult,
  OptimiseRequest, OptimiseResult, Hazard, CopilotFocus, CopilotAnswer, CopilotReport, CopilotStatus, HoldingView,
} from './types'

const BASE = (import.meta.env?.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

function describe(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ')
  return 'Request failed'
}

async function req<T>(path: string, init?: RequestInit, timeoutMs = 60000): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, { headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(timeoutMs), ...init })
  } catch (e) {
    if ((e as Error).name === 'TimeoutError') throw new ApiError(0, `The backend took too long to respond (${Math.round(timeoutMs / 1000)} s). Try again or reduce the Monte Carlo run count.`)
    throw new ApiError(0, 'Cannot reach the backend. Start it with: uvicorn app.main:app --port 8000 (see README).')
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { msg = describe((await res.json()).detail) } catch { /* non-JSON error */ }
    throw new ApiError(res.status, msg)
  }
  const ct = res.headers.get('content-type') ?? ''
  return (ct.includes('json') ? res.json() : res.text()) as Promise<T>
}
const post = <T,>(p: string, body?: unknown, timeoutMs?: number) => req<T>(p, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }, timeoutMs)

export const api = {
  metadata: () => req<Metadata>('/api/v1/metadata'),
  graph: () => req<GraphPayload>('/api/v1/graph'),
  scenarios: () => req<{ items: ScenarioRecord[]; total: number }>('/api/v1/scenarios'),
  createScenario: (spec: ScenarioSpec) => post<ScenarioRecord>('/api/v1/scenarios', spec),
  run: (id: string, maxDepth?: number | null, view: HoldingView = 'company') =>
    post<RunResult>(`/api/v1/scenarios/${id}/run`, { ...(maxDepth ? { max_depth: maxDepth } : {}), holding_view: view }),
  report: (id: string, format: 'md' | 'csv', mc?: { n: number; seed: number }, depth?: number | null, view: HoldingView = 'company') =>
    req<string>(`/api/v1/scenarios/${id}/report?format=${format}${mc ? `&include_monte_carlo=true&n_simulations=${mc.n}&seed=${mc.seed}` : ''}${depth ? `&max_depth=${depth}` : ''}&holding_view=${view}`),
  monteCarlo: (scenario_id: string, n_simulations: number, seed: number, max_depth?: number | null) =>
    post<MonteCarloResult>('/api/v1/analysis/monte-carlo', { scenario_id, n_simulations, seed, max_depth: max_depth || undefined }),
  entity: (id: string) => req<EntityDetail>(`/api/v1/entities/${id}`),
  dependencies: (id: string) => req<Dependencies>(`/api/v1/entities/${id}/dependencies`),
  entityImpact: (id: string, scenario_id: string, depth?: number | null) =>
    req<EntityImpactPayload>(`/api/v1/entities/${id}/impact?scenario_id=${scenario_id}${depth ? `&max_depth=${depth}` : ''}`),
  systemic: (scenario_id?: string, limit = 25) =>
    req<{ rows: SystemicRow[]; weights: Record<string, number>; component_descriptions: Record<string, string>; interpretation: string }>(
      `/api/v1/analysis/systemic-risk?limit=${limit}${scenario_id ? `&scenario_id=${scenario_id}` : ''}`),
  criticalPaths: (scenario_id: string, top = 10) => req<CriticalPath[]>(`/api/v1/analysis/critical-paths?scenario_id=${scenario_id}&top=${top}`),
  mitigationCompare: (scenario_id: string, interventions: Intervention[], p: number, depth?: number | null) =>
    post<MitigationResult>('/api/v1/mitigation/compare', { scenario_id, interventions, annual_event_probability: p, max_depth: depth || undefined }),
  recommendations: (scenario_id: string, p: number, top = 8, depth?: number | null) =>
    req<MitigationResult>(`/api/v1/mitigation/recommendations?scenario_id=${scenario_id}&top=${top}&annual_event_probability=${p}${depth ? `&max_depth=${depth}` : ''}`),
  portfolio: (view: HoldingView = 'company') => req<Portfolio>(`/api/v1/portfolio?holding_view=${view}`),
  finder: (body: FinderRequest) => post<FinderResult>('/api/v1/analysis/reverse-stress', body),
  promote: (hazard: Hazard, label: string, max_depth = 6) => post<ScenarioRecord>('/api/v1/analysis/reverse-stress/promote', { hazard, label, max_depth }),
  optimise: (body: OptimiseRequest) => post<OptimiseResult>('/api/v1/mitigation/optimise', body),
  backtestDemo: (scenario_id: string) => post<{ label: string; n: number; metrics: Record<string, number | null> | null; note: string }>(
    '/api/v1/analysis/backtest', { scenario_id, use_synthetic_demo: true }),
  copilotStatus: () => req<CopilotStatus>('/api/v1/copilot/status'),
  copilotAsk: (focus: CopilotFocus, question: string) => post<CopilotAnswer>('/api/v1/copilot/ask', { focus, question }, 170000),
  copilotReport: (focus: CopilotFocus, use_model: boolean) => post<CopilotReport>('/api/v1/copilot/report', { focus, use_model }, 170000),
  sources: () => req<Record<string, any>>('/api/v1/data/sources'),
  quality: () => req<Record<string, any>>('/api/v1/data/quality'),
}
