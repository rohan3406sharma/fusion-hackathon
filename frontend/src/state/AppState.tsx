import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { EntityImpact, GraphPayload, HoldingView, Metadata, MonteCarloResult, RunResult, ScenarioRecord } from '../api/types'

interface Ctx {
  metadata: Metadata | null
  graph: GraphPayload | null
  scenarios: ScenarioRecord[]
  activeId: string | null
  active: ScenarioRecord | null
  run: RunResult | null
  impacts: Map<string, EntityImpact>
  mc: MonteCarloResult | null
  depthOverride: number | null
  holdingView: HoldingView
  loading: boolean
  mcLoading: boolean
  error: string | null
  setActive: (id: string) => void
  setDepth: (d: number | null) => void
  setHoldingView: (v: HoldingView) => void
  refreshScenarios: (selectId?: string) => Promise<void>
  runMonteCarlo: (n: number, seed: number) => Promise<void>
  reload: () => void
}
const KEY = 'fin04.activeScenario'
const readSaved = (): string | null => { try { return localStorage.getItem(KEY) } catch { return null } }
const save = (id: string) => { try { localStorage.setItem(KEY, id) } catch { /* storage unavailable */ } }
const VIEW_KEY = 'fin04.holdingView'
const readView = (): HoldingView => { try { return localStorage.getItem(VIEW_KEY) === 'business_unit' ? 'business_unit' : 'company' } catch { return 'company' } }
const saveView = (v: HoldingView) => { try { localStorage.setItem(VIEW_KEY, v) } catch { /* storage unavailable */ } }
const AppCtx = createContext<Ctx | null>(null)
export const useApp = () => {
  const c = useContext(AppCtx)
  if (!c) throw new Error('useApp outside provider')
  return c
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const [graph, setGraph] = useState<GraphPayload | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioRecord[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [run, setRun] = useState<RunResult | null>(null)
  const [mc, setMc] = useState<MonteCarloResult | null>(null)
  const [depthOverride, setDepth] = useState<number | null>(null)
  const [holdingView, setView] = useState<HoldingView>(readView)
  const [loading, setLoading] = useState(true)
  const [mcLoading, setMcLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const seq = useRef(0)

  useEffect(() => {
    let dead = false
    setLoading(true)
    Promise.all([api.metadata(), api.graph(), api.scenarios()])
      .then(([m, g, s]) => {
        if (dead) return
        setMetadata(m); setGraph(g); setScenarios(s.items); setError(null)
        setActiveId((cur) => cur ?? (s.items.find((x) => x.id === readSaved())?.id ?? s.items[0]?.id ?? null))
        if (!s.items.length) setLoading(false)
      })
      .catch((e: Error) => { if (!dead) { setError(e.message); setLoading(false) } })
    return () => { dead = true }
  }, [tick])

  useEffect(() => {
    if (!activeId) return
    save(activeId)
    const my = ++seq.current
    setLoading(true)
    api.run(activeId, depthOverride, holdingView)
      .then((r) => { if (my === seq.current) { setRun(r); setMc(null); setError(null) } })
      .catch((e: Error) => { if (my === seq.current) setError(e.message) })
      .finally(() => { if (my === seq.current) setLoading(false) })
  }, [activeId, depthOverride, holdingView])

  const refreshScenarios = useCallback(async (selectId?: string) => {
    const s = await api.scenarios()
    setScenarios(s.items)
    if (selectId) { setDepth(null); setActiveId(selectId) }
  }, [])

  const runMonteCarlo = useCallback(async (n: number, seed: number) => {
    if (!activeId) return
    setMcLoading(true)
    try { setMc(await api.monteCarlo(activeId, n, seed, depthOverride)); setError(null) }
    catch (e) { setError((e as Error).message) }
    finally { setMcLoading(false) }
  }, [activeId, depthOverride])

  const impacts = useMemo(() => new Map((run?.entities ?? []).map((e) => [e.entity_id, e])), [run])
  const active = scenarios.find((s) => s.id === activeId) ?? null
  const value: Ctx = {
    metadata, graph, scenarios, activeId, active, run, impacts, mc, depthOverride, holdingView, loading, mcLoading, error,
    setActive: (id) => { setDepth(null); setActiveId(id) }, setDepth, refreshScenarios, runMonteCarlo, reload: () => setTick((t) => t + 1),
    setHoldingView: (v) => { saveView(v); setView(v) },
  }
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>
}
