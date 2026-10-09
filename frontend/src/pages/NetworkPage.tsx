import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Maximize2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react'
import GraphView, { SHAPE_LEGEND, type GraphHandle, walk } from '../components/GraphView'
import { Badge, Caveat, ErrorBox, Loading, PageHeader, SynBadge } from '../components/ui'
import { api } from '../api/client'
import type { EntityDetail, EntityImpactPayload } from '../api/types'
import { useApp } from '../state/AppState'
import { EMPTY_FILTERS, filterNodes, type NodeFilters } from '../lib/filters'
import { fmtM, fmtPct, orderLabel, title } from '../lib/format'
import { STATUS_COLOR } from '../lib/colors'

export default function NetworkPage() {
  const { graph, impacts, run, error, loading, depthOverride, setDepth, metadata } = useApp()
  const [filters, setFilters] = useState<NodeFilters>(EMPTY_FILTERS)
  const [params, setParams] = useSearchParams()
  const [selected, setSelectedRaw] = useState<string | null>(params.get('select'))
  const setSelected = (id: string | null) => { setSelectedRaw(id); setParams(id ? { select: id } : {}, { replace: true }) }
  const [layout, setLayout] = useState<'tiered' | 'force'>('tiered')
  const [showFin, setShowFin] = useState(false)
  const [showPath, setShowPath] = useState(true)
  const [detail, setDetail] = useState<EntityDetail | null>(null)
  const [impact, setImpact] = useState<EntityImpactPayload | null>(null)
  const handle = useRef<GraphHandle>(null)

  const visibleNodes = useMemo(() => (graph ? filterNodes(graph.nodes, filters, impacts) : []), [graph, filters, impacts])
  const visible = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes])

  useEffect(() => {
    if (!selected) { setDetail(null); setImpact(null); return }
    let dead = false
    api.entity(selected).then((d) => !dead && setDetail(d)).catch(() => undefined)
    if (run?.scenario_id) api.entityImpact(selected, run.scenario_id).then((i) => !dead && setImpact(i)).catch(() => !dead && setImpact(null))
    return () => { dead = true }
  }, [selected, run?.scenario_id, run?.summary.total_loss_musd])

  if (error && !graph) return <ErrorBox message={error} />
  if (!graph || !run) return <Loading label="Loading graph" />
  const imp = selected ? impacts.get(selected) : undefined
  const up = selected ? walk(graph, selected, 'up') : null
  const down = selected ? walk(graph, selected, 'down') : null
  const path = showPath && impact?.dominant_paths[0] ? impact.dominant_paths[0].entity_ids : []
  const set = (p: Partial<NodeFilters>) => setFilters((f) => ({ ...f, ...p }))
  const types = metadata?.entity_types ?? []

  return (
    <div>
      <PageHeader eyebrow="Interactive supply-chain graph" title="Who depends on whom">
        Directed supplier → customer edges from the backend. Colour shows scenario status; dashed outlines mark synthetic records; node size scales with value added.
      </PageHeader>
      <details className="mb-4 bg-paper hairline p-4" aria-label="Filters" open={typeof window === 'undefined' || window.innerWidth >= 1024}>
        <summary className="cursor-pointer text-xs uppercase tracking-[0.14em] text-warm">Filters &amp; depth <span data-testid="visible-count" className="ml-3 normal-case tracking-normal">{visibleNodes.length} of {graph.nodes.length} entities shown</span></summary>
        <div className="mt-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1.3fr]">
          <div>
            <label className="lbl" htmlFor="q">Search</label>
            <input id="q" className="field" placeholder="Name, product, region…" value={filters.q} onChange={(e) => set({ q: e.target.value })} />
          </div>
          <div>
            <label className="lbl" htmlFor="cat">Food category</label>
            <select id="cat" className="field" value={filters.category} onChange={(e) => set({ category: e.target.value })}>
              <option value="">All</option>{metadata?.food_categories.map((c) => <option key={c} value={c}>{title(c)}</option>)}
            </select>
          </div>
          <div>
            <label className="lbl" htmlFor="ctry">Country</label>
            <select id="ctry" className="field" value={filters.country} onChange={(e) => set({ country: e.target.value })}>
              <option value="">All</option>{metadata?.countries.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="lbl" htmlFor="st">Risk status</label>
            <select id="st" className="field" value={filters.status} onChange={(e) => set({ status: e.target.value as NodeFilters['status'] })}>
              <option value="all">All</option><option value="direct">Directly exposed</option><option value="propagated">Propagated impact</option><option value="unaffected">Unaffected</option>
            </select>
          </div>
          <div>
            <label className="lbl" htmlFor="depth">Propagation depth: {depthOverride ?? run.summary.max_depth_used} hops</label>
            <input id="depth" type="range" min={1} max={8} value={depthOverride ?? run.summary.max_depth_used} onChange={(e) => setDepth(Number(e.target.value))} className="range mt-2" />
          </div>
        </div>
        <fieldset className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
          <legend className="sr-only">Entity type</legend>
          <span className="lbl !mb-0">Entity type</span>
          {types.map((t) => (
            <label key={t} className="flex cursor-pointer items-center gap-1.5 text-xs">
              <input type="checkbox" checked={filters.types.includes(t)} onChange={(e) => set({ types: e.target.checked ? [...filters.types, t] : filters.types.filter((x) => x !== t) })} />{title(t)}
            </label>
          ))}
        </fieldset>
        <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-taupe pt-3">
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={showFin} onChange={(e) => setShowFin(e.target.checked)} />Show financial channel (not propagated)</label>
          <button className="btn" onClick={() => { setFilters(EMPTY_FILTERS); setDepth(null); setSelected(null) }}><RotateCcw size={13} />Reset filters &amp; depth</button>
          {loading && <p className="text-xs text-warm">Re-running model…</p>}
        </div>
        </div>
      </details>
      <div className="grid gap-4 xl:grid-cols-[1fr_330px]">
        <div className="min-w-0 space-y-3">
          <div className="relative h-[72vh] min-h-[460px] max-md:h-[78vh] border border-taupe bg-white shadow-soft">
            <GraphView ref={handle} graph={graph} impacts={impacts} visible={visible} selectedId={selected} pathIds={path} showFinancial={showFin} layout={layout} onSelect={setSelected} />
            <div className="absolute right-3 top-3 flex flex-col gap-1">
              <button className="btn btn-ghost bg-white" aria-label="Zoom in" onClick={() => handle.current?.zoomIn()}><ZoomIn size={14} /></button>
              <button className="btn btn-ghost bg-white" aria-label="Zoom out" onClick={() => handle.current?.zoomOut()}><ZoomOut size={14} /></button>
              <button className="btn btn-ghost bg-white" aria-label="Fit to view" onClick={() => handle.current?.fit()}><Maximize2 size={14} /></button>
              <button className="btn btn-ghost bg-white" aria-label="Reset view" onClick={() => handle.current?.reset()}><RotateCcw size={14} /></button>
            </div>
            <div className="absolute bottom-3 left-3 flex gap-1 bg-white/90 p-1 text-xs">
              <button className={`btn ${layout === 'tiered' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setLayout('tiered')}>Supply tiers</button>
              <button className={`btn ${layout === 'force' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setLayout('force')}>Force layout</button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 bg-paper hairline px-4 py-3 text-xs" aria-label="Legend">
            {(['direct', 'propagated', 'unaffected'] as const).map((k) => (
              <span key={k} className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 border border-dashed border-charcoal" style={{ background: STATUS_COLOR[k] }} />{k === 'direct' ? 'Directly exposed' : k === 'propagated' ? 'Propagated impact (opacity = disruption)' : 'Unaffected'}</span>
            ))}
            <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 border border-dashed border-charcoal" />Dashed outline = synthetic</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-5 bg-charcoal" />Upstream suppliers</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-5 bg-gold-dark" />Downstream customers</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-5 bg-direct" />Dominant propagation path</span>
            <span className="text-warm">Shapes: {SHAPE_LEGEND.map(([s, l]) => `${s} = ${l}`).join(' · ')}</span>
          </div>
          <Caveat title="Reading the graph">Edge width shows dependency share, not money. No relationship here is a disclosed contract; the network is a synthetic demonstration.</Caveat>
        </div>

        <aside className="bg-paper hairline p-5" aria-label="Entity details" data-testid="detail-panel">
          {!selected || !graph.nodes.find((n) => n.id === selected) ? (
            <div className="text-sm text-warm"><p className="eyebrow mb-2">Entity details</p>Select a node to see its profile, hop depth and dependencies. Click the background to clear.</div>
          ) : (
            <div className="space-y-4 text-sm fade-in">
              <div>
                <p className="eyebrow">{title(graph.nodes.find((n) => n.id === selected)!.entity_type)}</p>
                <h2 className="text-xl leading-snug" data-testid="detail-name">{graph.nodes.find((n) => n.id === selected)!.name}</h2>
                <div className="mt-2 flex gap-1.5"><SynBadge /><Badge tone={imp?.status === 'direct' ? 'direct' : imp?.status === 'propagated' ? 'gold' : 'neutral'}>{title(imp?.status ?? 'unaffected')}</Badge></div>
              </div>
              {imp && imp.status !== 'unaffected' && (
                <dl className="grid grid-cols-2 gap-3 text-xs">
                  <div><dt className="eyebrow">Hop depth</dt><dd className="num text-base">{orderLabel(imp.hop_order)}</dd></div>
                  <div><dt className="eyebrow">Disruption</dt><dd className="num text-base">{fmtPct(imp.final_disruption)}</dd></div>
                  <div><dt className="eyebrow">Direct loss</dt><dd className="num">{fmtM(imp.direct_loss_musd)}</dd></div>
                  <div><dt className="eyebrow">Indirect loss</dt><dd className="num">{fmtM(imp.indirect_loss_musd)}</dd></div>
                </dl>
              )}
              {imp && <p className="text-xs text-warm">{imp.evidence_label}</p>}
              {detail && (
                <dl className="space-y-1 text-xs">
                  <div className="flex justify-between"><dt className="text-warm">Location</dt><dd>{detail.region}, {detail.country}</dd></div>
                  <div className="flex justify-between"><dt className="text-warm">Product</dt><dd>{detail.output_product ? title(detail.output_product) : '—'}</dd></div>
                  <div className="flex justify-between"><dt className="text-warm">Inventory</dt><dd className="num">{detail.inventory_days} d</dd></div>
                  <div className="flex justify-between"><dt className="text-warm">Alt. suppliers</dt><dd className="num">{fmtPct(detail.alternative_supplier_availability)}</dd></div>
                  <div className="flex justify-between"><dt className="text-warm">Suppliers / customers</dt><dd className="num">{detail.in_degree} / {detail.out_degree}</dd></div>
                  {detail.single_source_inputs.length > 0 && <div className="flex justify-between"><dt className="text-warm">Single-source</dt><dd>{detail.single_source_inputs.map(title).join(', ')}</dd></div>}
                  <div className="flex justify-between"><dt className="text-warm">Record confidence</dt><dd>{detail.confidence} · synthetic</dd></div>
                </dl>
              )}
              <div className="text-xs">
                <p className="eyebrow mb-1">Reach</p>
                <p>Upstream: <strong className="num">{(up?.nodes.size ?? 1) - 1}</strong> suppliers (transitive) · Downstream: <strong className="num">{(down?.nodes.size ?? 1) - 1}</strong> customers</p>
              </div>
              {impact?.dominant_paths[0] && (
                <div className="text-xs">
                  <label className="mb-1 flex items-center gap-2"><input type="checkbox" checked={showPath} onChange={(e) => setShowPath(e.target.checked)} /><span className="eyebrow">Highlight propagation path</span></label>
                  <p className="leading-relaxed">{impact.dominant_paths[0].names.join(' → ')}</p>
                  <p className="mt-1 text-warm">Cumulative transmission {(impact.dominant_paths[0].cumulative_transmission * 100).toFixed(1)}% · {impact.dominant_paths[0].hops.length} hop(s)</p>
                </div>
              )}
              <Link className="btn w-full justify-center" to={`/entity/${selected}`}>Open entity intelligence</Link>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
