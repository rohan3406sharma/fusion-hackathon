import { Link, useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download } from 'lucide-react'
import { useApp } from '../state/AppState'
import { api } from '../api/client'
import { Badge, Caveat, Empty, ErrorBox, Kpi, Loading, PageHeader, Panel } from '../components/ui'
import { fmtM, fmtPct, fmtRank, plural, title } from '../lib/format'
import { CHART } from '../lib/colors'
import { downloadText, runToCsv, runToJson } from '../lib/export'
import { useState } from 'react'
import type { Breakdown } from '../api/types'

function BreakdownChart({ data, label }: { data: Breakdown[]; label: string }) {
  const rows = data.filter((d) => d.total_loss_musd > 0).slice(0, 10).map((d) => ({ name: title(d.key), direct: d.direct_loss_musd, indirect: d.indirect_loss_musd }))
  if (!rows.length) return <Empty>No losses in this breakdown.</Empty>
  return (
    <div className="h-72" aria-label={label}>
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ left: 10, right: 12 }}>
          <CartesianGrid stroke={CHART.grid} horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} stroke={CHART.neutral} /><YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} stroke={CHART.neutral} />
          <Tooltip formatter={(v) => fmtM(Number(v))} /><Legend />
          <Bar isAnimationActive={false} dataKey="direct" stackId="a" name="Direct" fill={CHART.direct} /><Bar isAnimationActive={false} dataKey="indirect" stackId="a" name="Indirect (modelled)" fill={CHART.indirect} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Results() {
  const { run, active, activeId, error, reload, mc, mcLoading, runMonteCarlo, loading } = useApp()
  const nav = useNavigate()
  const [n, setN] = useState(500)
  const [seed, setSeed] = useState(42)
  const [tab, setTab] = useState<'category' | 'type' | 'region'>('category')
  if (error && !run) return <ErrorBox message={error} onRetry={reload} />
  if (!run || !active) return <Loading label="Loading results" />
  const s = run.summary, c = run.comparison
  const affected = run.entities.filter((e) => e.status !== 'unaffected').sort((a, b) => b.total_loss_musd - a.total_loss_musd)
  const byOrder = [0, 1, 2, 3].map((o) => ({ o, items: affected.filter((e) => (o === 3 ? (e.hop_order ?? 0) >= 3 : e.hop_order === o)) }))
  const slug = active.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const exportMd = async () => { if (activeId) downloadText(`${slug}-report.md`, await api.report(activeId, 'md', mc ? { n: mc.n_simulations, seed: mc.seed } : undefined), 'text/markdown') }
  const exportJson = () => downloadText(`${slug}-run.json`, JSON.stringify({ exported_for: 'FIN-04 Climate Exposure Graph (synthetic Food & Beverage demonstration)', run, uncertainty: mc ?? null }, null, 2), 'application/json')
  const exportCmp = c.portfolio_rows
  const mcHist = mc?.histogram.map((h) => ({ x: Math.round((h.lo + h.hi) / 2), count: h.count }))

  return (
    <div className="space-y-8">
      {error && <ErrorBox message={error} />}
      <PageHeader eyebrow="Scenario results" title={active.name}
        actions={<>
          <button className="btn" onClick={() => downloadText(`${slug}-entities.csv`, runToCsv(run), 'text/csv')}><Download size={13} />CSV</button>
          <button className="btn" onClick={exportJson}><Download size={13} />JSON</button>
          <button className="btn btn-primary" onClick={exportMd}><Download size={13} />Scenario report{mc ? ' + uncertainty' : ''}</button>
        </>}>
        Direct, first-, second- and third-order effects are reported separately because their evidence differs. All amounts are modelled value-added at risk on synthetic data.
      </PageHeader>
      <nav aria-label="On this page" className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
        {[['orders', 'Orders'], ['affected', 'Affected entities'], ['where', 'Where the loss lands'], ['paths', 'Propagation paths'], ['compare', 'Location vs network'], ['uncertainty', 'Uncertainty'], ['assumptions', 'Assumptions']].map(([id, l]) => <a key={id} href={`#${id}`} className="underline decoration-taupe underline-offset-4 hover:decoration-gold">{l}</a>)}
      </nav>
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${loading ? 'opacity-60' : ''}`}>
        <Kpi label="Directly affected" value={s.n_exposed_facilities} sub={fmtM(s.direct_loss_musd)} accent />
        <Kpi label="Indirectly affected" value={s.n_affected_downstream} sub={fmtM(s.indirect_loss_musd)} accent />
        <Kpi label="Network-aware total" value={fmtM(s.total_loss_musd, 0)} sub={s.indirect_to_direct_ratio != null ? `${s.indirect_to_direct_ratio.toFixed(2)}× direct (scenario-specific)` : 'No direct loss'} />
        <Kpi label="Disruption window" value={`${s.effective_duration_days.toFixed(0)} d`} sub={`${s.iterations} hops · ${s.converged ? 'converged' : 'depth-limited'}`} />
      </div>

      <Panel id="orders" title="Propagation by order" subtitle="Each order carries a different strength of evidence">
        <div className="grid gap-4 md:grid-cols-4">
          {run.orders.slice(0, 4).map((o) => (
            <div key={o.order} className="border-l-2 border-gold pl-3">
              <p className="eyebrow">{o.label}</p><p className="font-serif text-2xl num">{fmtM(o.loss_musd)}</p><p className="text-xs text-warm">{plural(o.entities, 'entity', 'entities')}</p>
              <p className="mt-2 text-[0.7rem] leading-snug text-warm">{o.evidence}</p>
            </div>
          ))}
        </div>
        {run.orders[4] && run.orders[4].loss_musd > 0 && <p className="mt-3 text-xs text-warm">Deeper (4+): {fmtM(run.orders[4].loss_musd)} across {run.orders[4].entities} entities. {run.orders[4].evidence}</p>}
      </Panel>

      <div id="affected" className="grid scroll-mt-20 gap-6 lg:grid-cols-2">
        <Panel title="Directly affected entities" subtitle="Order 0">
          <EntityTable items={byOrder[0].items} onOpen={(id) => nav(`/entity/${id}`)} />
        </Panel>
        <Panel title="First-order propagation" subtitle="Direct customers of a disrupted supplier">
          <EntityTable items={byOrder[1].items} onOpen={(id) => nav(`/entity/${id}`)} />
        </Panel>
        <Panel title="Second-order propagation" subtitle="Limited empirical support">
          <EntityTable items={byOrder[2].items} onOpen={(id) => nav(`/entity/${id}`)} />
        </Panel>
        <Panel title="Third-order and deeper" subtitle="Model-based only · low confidence">
          <EntityTable items={byOrder[3].items} onOpen={(id) => nav(`/entity/${id}`)} />
        </Panel>
      </div>

      <Panel id="where" title="Where the loss lands" right={
        <div className="flex gap-1">{(['category', 'type', 'region'] as const).map((t) => <button key={t} className={`btn ${tab === t ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab(t)}>{t === 'category' ? 'Food category' : t === 'type' ? 'Entity type' : 'Country'}</button>)}</div>}>
        <BreakdownChart label={`Loss by ${tab}`} data={tab === 'category' ? run.by_food_category : tab === 'type' ? run.by_entity_type : run.by_region} />
      </Panel>

      <Panel id="paths" title="Critical propagation paths" subtitle="Dominant (max-product) route from a directly hit entity to each most-affected entity">
        {run.critical_paths.length === 0 ? <Empty>No multi-hop paths under this scenario.</Empty> : (
          <ol className="space-y-3 text-sm">
            {run.critical_paths.map((p) => (
              <li key={p.terminal_id} className="border-b border-taupe pb-3">
                <p className="leading-relaxed">{p.names.map((nme, i) => <span key={i}>{i > 0 && <span className="mx-1.5 text-gold-dark">→</span>}<Link className="underline decoration-taupe underline-offset-4" to={`/entity/${p.entity_ids[i]}`}>{nme}</Link></span>)}</p>
                <p className="mt-1 text-xs text-warm num"><Link className="mr-3 underline" to={`/network?select=${p.terminal_id}`}>View in graph</Link>Transmission per hop: {p.hops.map((h) => `${(h.transmission * 100).toFixed(0)}%`).join(' · ')} · terminal loss {fmtM(p.terminal_total_loss_musd)}</p>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      <Panel id="compare" title="Location-only vs network-aware" subtitle="The central comparison — a model comparison, not empirical proof">
        <div className="grid gap-4 md:grid-cols-3">
          <Kpi label="Location-only (whole network)" value={fmtM(c.location_only_loss_musd)} />
          <Kpi label="Network-aware (whole network)" value={fmtM(c.network_aware_loss_musd)} sub={`Δ ${fmtM(c.absolute_difference_musd)}${c.relative_difference != null ? ` (${fmtPct(c.relative_difference, 1)})` : ' (relative n/a: no direct loss)'}`} accent />
          <Kpi label="Demo portfolio (18 synthetic holdings)" value={`${fmtM(c.portfolio_location_loss_musd)} → ${fmtM(c.portfolio_network_loss_musd)}`} sub={`${c.hidden_exposure_count} hidden exposure(s)`} />
        </div>
        <div className="mt-5 overflow-x-auto">
          <table className="tbl">
            <thead><tr><th>Holding</th><th>Direct disruption</th><th>Network disruption</th><th>Rank (location)</th><th>Rank (network)</th><th>Change</th><th></th></tr></thead>
            <tbody>
              {exportCmp.map((r) => (
                <tr key={r.entity_id} className="row-click" onClick={() => nav(`/entity/${r.entity_id}`)}>
                  <td>{r.name}</td><td className="num">{fmtPct(r.location_disruption, 1)}</td><td className="num">{fmtPct(r.network_disruption, 1)}</td>
                  <td className="num">{fmtRank(r.rank_location)}</td><td className="num">{fmtRank(r.rank_network)}</td>
                  <td className="num">{r.rank_change > 0 ? `▲ ${fmtRank(r.rank_change)}` : r.rank_change < 0 ? `▼ ${fmtRank(-r.rank_change)}` : '—'}</td>
                  <td>{r.hidden_exposure && <Badge tone="gold">Hidden exposure</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4"><Caveat title="Scope">{c.scope_note} Tied holdings share an average rank; holdings untouched in both views are shown with no rank change.</Caveat></div>
      </Panel>

      <Panel id="uncertainty" title="Uncertainty analysis (Monte Carlo)" subtitle="Scenario distribution over analyst-defined input ranges"
        right={<div className="flex items-end gap-2">
          <div><label className="lbl" htmlFor="mcn">Runs</label><input id="mcn" type="number" className="field w-24" min={20} max={5000} value={n} onChange={(e) => setN(Number(e.target.value))} /></div>
          <div><label className="lbl" htmlFor="mcs">Seed</label><input id="mcs" type="number" className="field w-24" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></div>
          <button className="btn btn-primary" disabled={mcLoading || n < 20 || n > 5000} onClick={() => runMonteCarlo(n, seed)}>{mcLoading ? 'Simulating…' : 'Run uncertainty analysis'}</button>
        </div>}>
        {!mc ? <Empty>Run the analysis to see the loss distribution, quantiles and parameter sensitivity. Results are cached and reproducible for a given seed.</Empty> : (
          <div className="space-y-6">
            <div className="grid gap-3 md:grid-cols-4">
              <Kpi label="Median total loss" value={fmtM(mc.total_loss.median, 0)} />
              <Kpi label="5th – 95th percentile" value={`${fmtM(mc.total_loss.p05, 0)} – ${fmtM(mc.total_loss.p95, 0)}`} sub="Scenario-uncertainty range" />
              <Kpi label="Median indirect" value={fmtM(mc.indirect_loss.median, 0)} sub={`${fmtM(mc.indirect_loss.p05, 0)} – ${fmtM(mc.indirect_loss.p95, 0)}`} />
              <Kpi label="Simulations" value={mc.n_simulations} sub={`seed ${mc.seed} · deterministic ${fmtM(mc.deterministic_total_loss_musd, 0)}`} />
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="h-64" aria-label="Loss distribution">
                <ResponsiveContainer><BarChart data={mcHist}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="x" tick={{ fontSize: 11 }} stroke={CHART.neutral} tickFormatter={(v) => `$${v}M`} /><YAxis tick={{ fontSize: 11 }} stroke={CHART.neutral} />
                  <Tooltip labelFormatter={(v) => `~${fmtM(Number(v), 0)}`} /><ReferenceLine x={Math.round(mc.total_loss.median)} stroke={CHART.ink} strokeDasharray="4 3" />
                  <Bar isAnimationActive={false} dataKey="count" name="Simulations" fill={CHART.indirect} /></BarChart></ResponsiveContainer>
              </div>
              <div className="h-64" aria-label="Parameter sensitivity">
                <ResponsiveContainer><BarChart data={mc.sensitivity.map((x) => ({ name: title(x.parameter), rho: Number(x.spearman_with_total_loss.toFixed(2)) }))} layout="vertical" margin={{ left: 30 }}>
                  <CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" domain={[-1, 1]} tick={{ fontSize: 11 }} stroke={CHART.neutral} /><YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} stroke={CHART.neutral} />
                  <Tooltip /><Bar isAnimationActive={false} dataKey="rho" name="Rank correlation with total loss">{mc.sensitivity.map((x, i) => <Cell key={i} fill={x.spearman_with_total_loss >= 0 ? CHART.ink : CHART.direct} />)}</Bar></BarChart></ResponsiveContainer>
              </div>
            </div>
            <Caveat title="Interpretation">{mc.interpretation} Sensitivity bars are Spearman rank correlations across simulations (association, not causation).</Caveat>
            <details className="text-xs text-warm"><summary className="cursor-pointer">Sampled assumptions</summary><ul className="mt-2 list-disc pl-4">{mc.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
            <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Entity</th><th>Median</th><th>5th pct</th><th>95th pct</th><th>P(affected)</th></tr></thead>
              <tbody>{mc.top_entities.map((t) => <tr key={t.entity_id}><td>{t.name}</td><td className="num">{fmtM(t.median_loss_musd)}</td><td className="num">{fmtM(t.p05_loss_musd)}</td><td className="num">{fmtM(t.p95_loss_musd)}</td><td className="num">{fmtPct(t.probability_affected)}</td></tr>)}</tbody></table></div>
          </div>
        )}
      </Panel>
      <Panel id="assumptions" title="Assumptions & limitations">
        <div className="grid gap-6 md:grid-cols-2 text-xs text-warm">
          <ul className="list-disc space-y-1 pl-4">{run.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          <ul className="list-disc space-y-1 pl-4">{run.limitations.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      </Panel>
    </div>
  )
}

function EntityTable({ items, onOpen }: { items: { entity_id: string; name: string; final_disruption: number; direct_disruption: number; total_loss_musd: number; hop_order: number | null; value_added_musd: number }[]; onOpen: (id: string) => void }) {
  if (!items.length) return <Empty>No entities at this order.</Empty>
  return (
    <div className="max-h-72 overflow-auto">
      <table className="tbl"><thead><tr><th>Entity</th><th>Disruption</th><th>Loss</th></tr></thead>
        <tbody>{items.slice(0, 30).map((e) => <tr key={e.entity_id} className="row-click" onClick={() => onOpen(e.entity_id)}><td>{e.name}</td><td className="num">{fmtPct(e.final_disruption, 1)}</td><td className="num">{fmtM(e.total_loss_musd)}</td></tr>)}</tbody></table>
      {items.length > 30 && <p className="mt-2 text-xs text-warm">Showing 30 of {items.length}.</p>}
    </div>
  )
}
