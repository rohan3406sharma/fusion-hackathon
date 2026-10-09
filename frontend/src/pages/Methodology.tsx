import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import { useApp } from '../state/AppState'
import { Badge, Caveat, ErrorBox, Kpi, Loading, PageHeader, Panel } from '../components/ui'
import { fmtPct, title } from '../lib/format'
import { CHART } from '../lib/colors'

type Dict = Record<string, any>

const ALGOS = [
  ['1 · Direct exposure', 'f = 1 − ∏c (1 − Dc · (1 − exp(−kh · Hc · E · Vh)))', 'Hazard intensity H (index), exposure E (asset share), vulnerability V (synthetic proxy) kept separate; duration factor D = 1 − exp(−d/τ). Configurable proxy, not a validated damage function.'],
  ['2 · Weighted graph', 'Edges supplier → customer with separate dependency, specificity, substitutability, confidence, provenance', 'Dependency = share of the customer\'s input of that product; not a monetary weight and not merged with confidence.'],
  ['3 · Propagation', 'τe = dep · spec · (1 − alt)(1 − sub) · inv ;  d(t+1) = 1 − (1 − d0)(1 − d_in(d(t)))', 'Additive within one input, noisy-OR across inputs, bounded in [0,1], monotone so cycles converge. Iteration t = t hops. Inventory test: clip((T − (I + L))/T, 0, 1) for storable goods.'],
  ['4 · Alternatives & substitution', 'Diversification limited by Σ spare capacity of unaffected same-product suppliers', 'Spare = revenue × spare fraction × (1 − 2·direct disruption); non-storable goods stay within the supplier\'s country; new edges are labelled “modelled”.'],
  ['5 · Graph analytics', 'Degree, weighted degree, betweenness (−log dep·spec), PageRank on reversed graph, reach, components, single-source inputs', 'Systemic score = Σ w·normalised component (exposure, reach, dependency, lack of alternatives, inventory fragility, criticality). A ranking aid; never converted to money.'],
  ['6 · Monte Carlo', 'Seeded sampling of intensity, vulnerability, dependency, substitutability, alternatives, inventory', 'Reports quantiles and Spearman sensitivities. A scenario distribution under analyst ranges, not a confidence interval.'],
  ['7 · Network vs location', 'Δ = Σ VA·(d_final − d_direct) · period fraction', 'Reported for the whole network and an 18-holding synthetic portfolio with rank changes. Model comparison only; the end-to-end claim is an open research gap.'],
  ['8 · Back-testing', 'POST /analysis/backtest with user-supplied observations', 'Interface only. The bundled demo uses pseudo-observations derived from the model itself and is explicitly circular. No validation has been performed.'],
  ['9 · Mitigation prioritisation', 'score = 100 · Σ w·{benefit, BCR, feasibility, speed, confidence}', 'Benefit = loss reduction; BCR uses an analyst-set annual event probability (shown with ×0.5/×2 sensitivity). Costs are synthetic placeholders.'],
]
const EVIDENCE = [
  ['Direct supplier → customer effect', 'High for direction, moderate for size', '5 independent firm-level studies'],
  ['Second-order propagation', 'Low to moderate', '2 studies (one non-climate natural experiment)'],
  ['Third-order propagation', 'Low', 'Simulation models only; no firm-level climate estimate'],
  ['Network-aware vs location-only portfolio exposure', 'Low (open gap)', 'Each part supported; end-to-end untested'],
  ['Hazard → financial loss', 'Uncertainty large', 'Hazard models and risk scores disagree widely'],
]

export default function Methodology() {
  const { metadata, activeId } = useApp()
  const [bt, setBt] = useState<Awaited<ReturnType<typeof api.backtestDemo>> | null>(null)
  const [btBusy, setBtBusy] = useState(false)
  const [src, setSrc] = useState<Dict | null>(null)
  const [q, setQ] = useState<Dict | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { Promise.all([api.sources(), api.quality()]).then(([s, qq]) => { setSrc(s); setQ(qq) }).catch((e: Error) => setErr(e.message)) }, [])
  if (err) return <ErrorBox message={err} />
  if (!src || !q) return <Loading label="Loading data inventory" />
  const miss = Object.entries(q.missing_field_share as Record<string, number>).map(([k, v]) => ({ name: k, share: Number((v * 100).toFixed(1)) }))
  const aud = src.reference_audit as Dict
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Data & methodology" title="What the numbers rest on">
        Transparency over precision: every figure is a model output on synthetic data, with its evidence strength and limitations stated alongside.
      </PageHeader>
      <Caveat title="Read first">Third-order propagation and the network-aware vs location-only comparison are model-dependent and are <strong>not</strong> established empirical results. There is no universal indirect-loss multiplier. The model is not calibrated or validated against any observed event{metadata ? ` (calibrated: ${String(metadata.model_status.calibrated)}, validated: ${String(metadata.model_status.validated)})` : ''}.</Caveat>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Entities" value={q.entities} sub={`${q.synthetic_entities} synthetic · ${q.observed_entities} observed`} />
        <Kpi label="Relationships" value={q.relations} sub={Object.entries(q.relations_by_status).map(([k, v]) => `${v} ${k}`).join(' · ')} />
        <Kpi label="Coordinates available" value={fmtPct(q.coordinates_available_share)} sub="all approximate & synthetic" />
        <Kpi label="Unmodelled supplier share" value={fmtPct(q.unmodelled_supplier_share_per_input)} sub="mean per (customer, input)" />
      </div>

      <Panel title="Dataset inventory" subtitle="Provenance, licence and limitations">
        <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Dataset</th><th>Kind</th><th>Status</th><th>Licence</th><th>Limitations</th></tr></thead>
          <tbody>{(src.datasets as Dict[]).map((d) => (
            <tr key={d.id}><td className="whitespace-nowrap">{d.id}</td><td>{title(d.kind)}</td><td><Badge tone={d.synthetic ? 'gold' : 'neutral'}>{d.synthetic ? 'synthetic' : 'real, reference only'}</Badge></td><td>{d.licence}</td><td className="text-xs text-warm">{d.limitations}</td></tr>))}</tbody></table></div>
        <h3 className="mt-6 text-base">External sources</h3>
        <ul className="mt-2 space-y-1 text-xs">{(src.external_sources as Dict[]).map((e) => <li key={e.name}><strong>{e.name}</strong> — <Badge>{e.status}</Badge> {e.licence}. {e.note}</li>)}</ul>
        <p className="mt-3 text-xs text-warm">Attribution: {src.required_attribution}</p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Sectivia reference audit" subtitle="Why it is not used as food data">
          {aud.present ? (
            <div className="space-y-2 text-xs">
              <p>{aud.n_companies} companies, {aud.n_relations} links; {fmtPct(aud.countries_usa_share)} US; {aud.companies_without_any_link} unlinked; {aud.relations_with_source_field} links carry a per-link source.</p>
              <p>Sectors: {Object.entries(aud.sectors as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(' · ')}. Food &amp; Beverage segments found: <strong>{(aud.food_and_beverage_segments_found as string[]).length || 'none'}</strong>.</p>
              <p className="text-warm">{aud.verdict}</p>
            </div>) : <p className="text-xs text-warm">Reference files not present.</p>}
        </Panel>
        <Panel title="Missing-data statistics" subtitle="Share of entities lacking each optional field">
          <div className="h-48" aria-label="Missing data chart"><ResponsiveContainer><BarChart data={miss} layout="vertical" margin={{ left: 40 }}><CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" unit="%" tick={{ fontSize: 11 }} stroke={CHART.neutral} /><YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 10 }} stroke={CHART.neutral} /><Tooltip /><Bar isAnimationActive={false} dataKey="share" name="% missing" fill={CHART.neutral} /></BarChart></ResponsiveContainer></div>
        </Panel>
      </div>

      <Panel title="Graph validation & coverage">
        <div className="grid gap-4 text-xs md:grid-cols-3">
          <div><p className="eyebrow">Validation</p><p className="mt-1">{q.validation.ok ? 'Passed' : 'FAILED'} · {q.validation.errors.length} errors · {q.validation.warnings.length} warnings shown</p></div>
          <div><p className="eyebrow">Cycles (flagged, kept)</p><p className="mt-1">{q.validation.cycles.length ? q.validation.cycles.map((c: string[]) => c.join(' ↔ ')).join('; ') : 'none'}</p><p className="mt-1 text-warm">Handled by a monotone bounded update that converges or stops at the depth cap.</p></div>
          <div><p className="eyebrow">Structure</p><p className="mt-1">Largest component {fmtPct(q.structure.largest_component_share)} · {q.structure.single_source_dependencies.length} single-source dependencies (≥60%)</p></div>
        </div>
      </Panel>

      <Panel title="Algorithms">
        <div className="space-y-5">{ALGOS.map(([t, f, d]) => (
          <div key={t} className="border-l-2 border-gold pl-4"><h3 className="text-base">{t}</h3><code className="mt-1 block overflow-x-auto bg-taupe/60 px-2 py-1 text-xs">{f}</code><p className="mt-1 text-xs text-warm">{d}</p></div>))}</div>
      </Panel>

      <Panel title="Back-testing interface" subtitle="No historical validation exists in this project">
        <p className="text-xs text-warm">The API accepts observed disruption fractions per entity and returns MAE, RMSE, bias, rank correlation and precision/recall. No observed dataset is bundled. The button below runs the interface on <strong>pseudo-observations generated from the model itself</strong>; the agreement it reports is circular and is not evidence of accuracy.</p>
        <button className="btn mt-3" disabled={btBusy || !activeId} onClick={async () => { if (!activeId) return; setBtBusy(true); try { setBt(await api.backtestDemo(activeId)) } catch (e) { setErr((e as Error).message) } finally { setBtBusy(false) } }}>{btBusy ? 'Running…' : 'Run circular interface demo'}</button>
        {bt && (
          <div className="mt-3 text-xs"><Caveat title="Not validation">{bt.label}</Caveat>
            {bt.metrics && <dl className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">{Object.entries(bt.metrics).map(([k, v]) => <div key={k}><dt className="eyebrow">{k}</dt><dd className="num">{typeof v === 'number' ? v.toFixed(3) : '—'}</dd></div>)}</dl>}</div>)}
      </Panel>

      <Panel title="Evidence strength (from the FIN-04 evidence review)">
        <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Claim</th><th>Confidence</th><th>Basis</th></tr></thead><tbody>{EVIDENCE.map(([a, b, c]) => <tr key={a}><td>{a}</td><td>{b}</td><td className="text-warm">{c}</td></tr>)}</tbody></table></div>
      </Panel>

      <Panel title="Hazard parameters & scenario assumptions">
        <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Hazard</th><th>Severity k</th><th>Duration τ (d)</th><th>Recovery (d)</th></tr></thead>
          <tbody>{metadata?.hazards.map((h) => <tr key={h.hazard_type}><td>{title(h.hazard_type)}</td><td className="num">{h.k}</td><td className="num">{h.tau}</td><td className="num">{h.recovery}</td></tr>)}</tbody></table></div>
        <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-warm">{metadata?.hazard_providers.map((p) => <li key={p.name}><strong>{p.name}</strong>: {p.description} {p.limitations}</li>)}
          {metadata?.unavailable_integrations.map((u) => <li key={u}>{u}</li>)}</ul>
      </Panel>

      <Panel title="Model limitations">
        <ul className="list-disc space-y-1 pl-4 text-xs text-warm">
          <li>All entities, links, coordinates and vulnerabilities are synthetic; no real company, contract or loss is represented.</li>
          <li>Hazard intensity is an index on a synthetic footprint; no flood depth, temperature, return period or probability is modelled.</li>
          <li>Losses are value-added at risk over the disruption window, not forecasts; no demand response, price effects or re-routing beyond stated parameters.</li>
          <li>Edges are static within a run; the evidence suggests customers re-wire after shocks (not modelled except via the mitigation lab).</li>
          <li>Financial (lender/insurer) channels are displayed but not propagated.</li>
          <li>Monte Carlo ranges reflect only the sampled parameter uncertainty, not structural model error.</li>
        </ul>
      </Panel>
    </div>
  )
}
