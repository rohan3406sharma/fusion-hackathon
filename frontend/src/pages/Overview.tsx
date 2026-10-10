import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { FinderResult } from '../api/types'
import { Bar as RBar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApp } from '../state/AppState'
import { Caveat, ErrorBox, Kpi, Loading, PageHeader, Panel } from '../components/ui'
import { fmtM, fmtPct, title } from '../lib/format'
import { CHART } from '../lib/colors'

export default function Overview() {
  const { run, active, error, loading, reload, metadata, holdingView } = useApp()
  const nav = useNavigate()
  const [finder, setFinder] = useState<FinderResult | null>(null)
  useEffect(() => { api.finder({ stability_draws: 200, holding_view: holdingView }).then(setFinder).catch(() => setFinder(null)) }, [holdingView])
  if (error && !run) return <ErrorBox message={error} onRetry={reload} />
  if (!run || !active) return <Loading label="Running the model on the synthetic Food & Beverage network" />
  const s = run.summary
  const orderData = run.orders.map((o) => ({ name: o.label, loss: o.loss_musd }))
  return (
    <div className="space-y-8">
      {error && <ErrorBox message={error} />}
      <PageHeader eyebrow="Climate-risk overview · Food & Beverage" title={active.name}>
        {active.description || 'Network-aware climate stress test.'} Every figure below is computed by the backend from a synthetic network and a synthetic hazard footprint.
      </PageHeader>
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6 ${loading ? 'opacity-60' : ''}`}>
        <Kpi label="Entities analysed" value={s.n_entities} sub={`${metadata?.n_relations ?? '—'} synthetic relationships`} />
        <Kpi label="Exposed facilities" value={s.n_exposed_facilities} sub="Direct disruption > 1%" />
        <Kpi label="Direct impact" value={fmtM(s.direct_loss_musd, 0)} sub="Location-only, value-added at risk" accent />
        <Kpi label="Network-aware impact" value={fmtM(s.total_loss_musd, 0)} sub={`Indirect ${fmtM(s.indirect_loss_musd, 0)}${s.indirect_to_direct_ratio != null ? ` · ${s.indirect_to_direct_ratio.toFixed(2)}× direct` : ''}`} accent />
        <Kpi label="Affected downstream" value={s.n_affected_downstream} sub="Reached only via supply links" />
        <Kpi label="Propagation" value={`${s.iterations} hops`} sub={s.converged ? 'Converged to tolerance' : 'Depth-limited'} />
      </div>
      <Caveat>
        Values are modelled value-added at risk over a {s.effective_duration_days.toFixed(0)}-day disruption window on <strong>synthetic</strong> data. The indirect/direct ratio is an output of
        these assumptions, not a universal multiplier. Third-order and deeper results are model-based with low confidence. <Link className="underline" to="/methodology">Read the methodology</Link>.
      </Caveat>
      {finder?.hidden_only_events[0] && (
        <section className="border border-gold/60 bg-paper p-5 shadow-soft" aria-label="Hidden exposure finder summary" data-testid="finder-card">
          <p className="eyebrow text-gold-dark">Hidden exposure finder · across {finder.n_events} synthetic events</p>
          <p className="mt-2 font-serif text-xl leading-snug">
            The largest hidden-only exposure is <span className="underline decoration-gold underline-offset-4">{finder.hidden_only_events[0].label}</span>: no holding is hit directly, yet the model has the portfolio losing {fmtPct(finder.hidden_only_events[0].portfolio_network_impact, 2)} of annual value added (synthetic data, uncalibrated).
          </p>
          <p className="mt-2 text-xs text-warm">
            Reaches {finder.hidden_only_events[0].holdings_affected} holdings
            {finder.hidden_only_events[0].p_top5 != null && ` · stays in the hidden-only top 5 in ${fmtPct(finder.hidden_only_events[0].p_top5)} of ${finder.stability?.n_draws} uncertainty draws`}
            {' '}· a ranking under synthetic assumptions, not a forecast.
          </p>
          {finder.structure_comparison && (
            <p className="mt-1 text-xs text-warm" data-testid="finder-card-companies">
              Holdings are counted as companies: {finder.structure_comparison.n_multi_segment} of {finder.holdings.length} own several business units, so a shock to one unit is diluted by the others (synthetic structures; any share outside food &amp; beverage is not modelled).
            </p>
          )}
          <Link className="btn mt-3" to="/finder">Open the finder</Link>
        </section>
      )}
      <nav aria-label="Guided journey" className="flex flex-wrap items-center gap-2 text-xs">
        <span className="eyebrow mr-1">Next</span>
        <Link className="btn" to="/finder">0 · Find hidden exposures</Link>
        <Link className="btn" to="/network">1 · Inspect the affected network</Link>
        <Link className="btn" to="/results">2 · Trace propagation &amp; compare</Link>
        <Link className="btn" to="/mitigation">3 · Test a mitigation</Link>
        <Link className="btn btn-ghost" to="/methodology">Methodology &amp; provenance</Link>
      </nav>
      <div className="grid gap-6 lg:grid-cols-5">
        <Panel className="lg:col-span-3" title="Loss by propagation order" subtitle="USD million · direct vs successive hops">
          <div className="h-64" aria-label="Loss by propagation order chart">
            <ResponsiveContainer>
              <BarChart data={orderData} margin={{ left: 0, right: 8 }}>
                <CartesianGrid stroke={CHART.grid} vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke={CHART.neutral} />
                <YAxis tick={{ fontSize: 11 }} stroke={CHART.neutral} />
                <Tooltip formatter={(v) => fmtM(Number(v))} />
                <RBar isAnimationActive={false} dataKey="loss" name="Loss (USD M)" fill={CHART.ink} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ul className="mt-3 space-y-1 text-xs text-warm">{run.orders.slice(1, 4).map((o) => <li key={o.order}><strong className="text-charcoal">{o.label}:</strong> {o.evidence}</li>)}</ul>
        </Panel>
        <Panel className="lg:col-span-2" title="Scenario" subtitle="Active hazard assumptions">
          <dl className="space-y-3 text-sm">
            {active.hazards.map((h, i) => (
              <div key={i}>
                <dt className="eyebrow">{h.label || title(h.hazard_type)}</dt>
                <dd className="num">{title(h.hazard_type)} · intensity index {h.intensity.toFixed(2)} · {h.duration_days} days</dd>
                <dd className="text-xs text-warm">{h.radius_km ? `Footprint ${h.radius_km} km around ${h.center_lat?.toFixed(1)}, ${h.center_lon?.toFixed(1)}` : ''}{h.affected_entity_ids.length ? ` Entities: ${h.affected_entity_ids.join(', ')}` : ''}{h.regions.length ? ` Regions: ${h.regions.join(', ')}` : ''}</dd>
              </div>
            ))}
            <div><dt className="eyebrow">Time horizon / source</dt><dd className="num">{active.time_horizon_year} · {active.data_source} (synthetic)</dd></div>
            <div><dt className="eyebrow">Resilience scales</dt><dd className="num text-xs">inventory ×{active.inventory_scale} · substitution ×{active.substitution_scale} · dependency ×{active.dependency_scale}</dd></div>
          </dl>
          <button className="btn mt-4" onClick={() => nav('/scenario')}>Edit scenario</button>
        </Panel>
      </div>
      <Panel title="Highest-risk supply-chain bottlenecks" subtitle="Systemic vulnerability score 0–100 (ranking aid, not a loss estimate)">
        <div className="overflow-x-auto">
          <table className="tbl">
            <thead><tr><th>Entity</th><th>Score</th><th>Downstream reach</th><th>Direct customers</th><th>Scenario status</th></tr></thead>
            <tbody>
              {run.bottlenecks.map((b) => {
                const imp = run.entities.find((e) => e.entity_id === b.entity_id)
                return (
                  <tr key={b.entity_id} className="row-click" onClick={() => nav(`/entity/${b.entity_id}`)}>
                    <td><Link className="underline decoration-gold underline-offset-4" to={`/entity/${b.entity_id}`}>{b.name}</Link></td>
                    <td className="num">{b.score.toFixed(1)}</td><td className="num">{b.downstream_reach} entities</td><td className="num">{b.out_degree} <span className="text-warm">(Σ dependency {b.weighted_out_dependency.toFixed(1)})</span></td>
                    <td>{imp ? title(imp.status) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Model & data confidence">
          <ul className="space-y-2 text-sm">
            <li><strong>Data:</strong> 100% synthetic entities and relationships; coordinates approximate and synthetic.</li>
            <li><strong>Direct loss:</strong> configurable proxy damage function; hazard intensity is an index, not a physical unit.</li>
            <li><strong>Propagation:</strong> first order well supported in direction; second order limited; third order model-only.</li>
            <li><strong>Uncertainty:</strong> run the Monte Carlo analysis on the <Link className="underline" to="/results">results page</Link> for a scenario-uncertainty range.</li>
          </ul>
        </Panel>
        <Panel title="Limitations">
          <ul className="list-disc space-y-1 pl-4 text-xs text-warm">{run.limitations.slice(0, 5).map((l) => <li key={l}>{l}</li>)}</ul>
        </Panel>
      </div>
    </div>
  )
}
