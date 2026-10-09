import type {
  Dependencies, EntityDetail, EntityImpactPayload, GraphPayload, Intervention, Metadata, MitigationResult,
  MonteCarloResult, RunResult, ScenarioRecord, ScenarioSpec, SystemicRow, CriticalPath,
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

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, { headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(60000), ...init })
  } catch (e) {
    if ((e as Error).name === 'TimeoutError') throw new ApiError(0, 'The backend took too long to respond (60 s). Try again or reduce the Monte Carlo run count.')
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
const post = <T,>(p: string, body?: unknown) => req<T>(p, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  metadata: () => req<Metadata>('/api/v1/metadata'),
  graph: () => req<GraphPayload>('/api/v1/graph'),
  scenarios: () => req<{ items: ScenarioRecord[]; total: number }>('/api/v1/scenarios'),
  createScenario: (spec: ScenarioSpec) => post<ScenarioRecord>('/api/v1/scenarios', spec),
  run: (id: string, maxDepth?: number | null) => post<RunResult>(`/api/v1/scenarios/${id}/run`, maxDepth ? { max_depth: maxDepth } : {}),
  report: (id: string, format: 'md' | 'csv', mc?: { n: number; seed: number }) =>
    req<string>(`/api/v1/scenarios/${id}/report?format=${format}${mc ? `&include_monte_carlo=true&n_simulations=${mc.n}&seed=${mc.seed}` : ''}`),
  monteCarlo: (scenario_id: string, n_simulations: number, seed: number, max_depth?: number | null) =>
    post<MonteCarloResult>('/api/v1/analysis/monte-carlo', { scenario_id, n_simulations, seed, max_depth: max_depth || undefined }),
  entity: (id: string) => req<EntityDetail>(`/api/v1/entities/${id}`),
  dependencies: (id: string) => req<Dependencies>(`/api/v1/entities/${id}/dependencies`),
  entityImpact: (id: string, scenario_id: string) => req<EntityImpactPayload>(`/api/v1/entities/${id}/impact?scenario_id=${scenario_id}`),
  systemic: (scenario_id?: string, limit = 25) =>
    req<{ rows: SystemicRow[]; weights: Record<string, number>; component_descriptions: Record<string, string>; interpretation: string }>(
      `/api/v1/analysis/systemic-risk?limit=${limit}${scenario_id ? `&scenario_id=${scenario_id}` : ''}`),
  criticalPaths: (scenario_id: string, top = 10) => req<CriticalPath[]>(`/api/v1/analysis/critical-paths?scenario_id=${scenario_id}&top=${top}`),
  mitigationCompare: (scenario_id: string, interventions: Intervention[], p: number) =>
    post<MitigationResult>('/api/v1/mitigation/compare', { scenario_id, interventions, annual_event_probability: p }),
  recommendations: (scenario_id: string, p: number, top = 8) =>
    req<MitigationResult>(`/api/v1/mitigation/recommendations?scenario_id=${scenario_id}&top=${top}&annual_event_probability=${p}`),
  backtestDemo: (scenario_id: string) => post<{ label: string; n: number; metrics: Record<string, number | null> | null; note: string }>(
    '/api/v1/analysis/backtest', { scenario_id, use_synthetic_demo: true }),
  sources: () => req<Record<string, any>>('/api/v1/data/sources'),
  quality: () => req<Record<string, any>>('/api/v1/data/quality'),
}
