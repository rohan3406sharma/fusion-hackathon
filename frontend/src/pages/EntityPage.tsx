import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import type { Dependencies, EntityDetail, EntityImpactPayload, MitigationResult, Neighbour } from '../api/types'
import { useApp } from '../state/AppState'
import { Badge, Bar as MiniBar, Caveat, Empty, ErrorBox, Loading, PageHeader, Panel, SynBadge } from '../components/ui'
import { fmtM, fmtPct, orderLabel, title } from '../lib/format'
import { CHART } from '../lib/colors'

function Rel({ rows, onOpen, empty }: { rows: Neighbour[]; onOpen: (id: string) => void; empty: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>
  return (
    <div className="max-h-72 overflow-auto"><table className="tbl"><thead><tr><th>Entity</th><th>Input</th><th>Dependency</th><th>Lead</th><th>Status</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.relation_id} className="row-click" onClick={() => onOpen(r.entity_id)}>
          <td>{r.name}{r.channel === 'financial' && <> <Badge>financial</Badge></>}</td><td>{title(r.product)}</td>
          <td className="num"><span className="mr-2">{fmtPct(r.dependency)}</span><span className="inline-block w-12 align-middle"><MiniBar value={r.dependency} /></span></td>
          <td className="num">{r.lead_time_days} d</td><td><Badge>{r.status}</Badge></td>
        </tr>))}</tbody></table></div>
  )
}

export default function EntityPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const { graph, activeId, run, impacts } = useApp()
  const [detail, setDetail] = useState<EntityDetail | null>(null)
  const [deps, setDeps] = useState<Dependencies | null>(null)
  const [impact, setImpact] = useState<EntityImpactPayload | null>(null)
  const [mit, setMit] = useState<MitigationResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    if (!id || !activeId) return
    let dead = false
    setErr(null); setDetail(null); setDeps(null); setImpact(null); setMit(null)
    Promise.all([api.entity(id), api.dependencies(id), api.entityImpact(id, activeId)])
      .then(([d, dp, im]) => { if (dead) return; setDetail(d); setDeps(dp); setImpact(im)
        if (im.impact.status !== 'unaffected') {
          api.mitigationCompare(activeId, [
            { type: 'inventory_buffer', entity_ids: [id], magnitude: 14, label: '+14 days input inventory' },
            { type: 'supplier_diversification', entity_ids: [id], magnitude: 0.5, label: 'Shift 50% of each supplier to alternatives' },
            { type: 'input_substitution', entity_ids: [id], magnitude: 0.2, label: 'Qualify substitute inputs (+0.2)' },
            { type: 'facility_protection', entity_ids: [id], magnitude: 0.4, label: 'Protect this facility (-40% vulnerability)' },
          ], 0.1).then((m) => !dead && setMit(m)).catch(() => undefined)
        } })
      .catch((e: Error) => !dead && setErr(e.message))
    return () => { dead = true }
  }, [id, activeId, run?.summary.total_loss_musd])

  const hits = useMemo(() => (graph?.nodes ?? []).filter((n) => !q || n.name.toLowerCase().includes(q.toLowerCase()) || n.id.includes(q.toLowerCase())).slice(0, 60), [graph, q])
  const alternatives = useMemo(() => (detail && graph ? graph.nodes.filter((n) => n.output_product === detail.output_product && n.id !== detail.id && detail.output_product) : []), [detail, graph])

  if (!id) {
    return (
      <div>
        <PageHeader eyebrow="Entity intelligence" title="Choose an entity">Open any farm, processor, logistics node or retailer for its profile, dependencies, systemic score and mitigation options.</PageHeader>
        <input className="field mb-4 max-w-md" placeholder="Search entities…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search entities" />
        <Panel><table className="tbl"><thead><tr><th>Entity</th><th>Type</th><th>Country</th><th>Scenario status</th></tr></thead>
          <tbody>{hits.map((n) => <tr key={n.id} className="row-click" onClick={() => nav(`/entity/${n.id}`)}><td>{n.name}</td><td>{title(n.entity_type)}</td><td>{n.country}</td><td>{title(impacts.get(n.id)?.status ?? 'unaffected')}</td></tr>)}</tbody></table></Panel>
      </div>
    )
  }
  if (err) return <div className="space-y-3"><ErrorBox message={err} /><Link className="btn" to="/entity">Back to entity list</Link></div>
  if (!detail || !deps || !impact) return <Loading label="Loading entity" />
  const im = impact.impact, sys = impact.systemic
  const contrib = Object.entries(sys.contributions).map(([k, v]) => ({ name: title(k), pts: Number(v.toFixed(1)) }))
  return (
    <div className="space-y-6">
      <PageHeader eyebrow={`Entity intelligence · ${title(detail.entity_type)}`} title={detail.name}
        actions={<><Link className="btn" to="/entity">All entities</Link><Link className="btn" to={`/network?select=${id}`}>Show in graph</Link></>}>
        {detail.facility_type} in {detail.region}, {detail.country}. <SynBadge /> {' '}<Badge tone={im.status === 'direct' ? 'direct' : im.status === 'propagated' ? 'gold' : 'neutral'}>{title(im.status)}</Badge>
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Profile">
          <dl className="space-y-1.5 text-xs">
            {([['ID', detail.id], ['Food category', title(detail.food_category)], ['Output', detail.output_product ? title(detail.output_product) : 'missing'],
              ['Coordinates', detail.latitude != null ? `${detail.latitude.toFixed(2)}, ${detail.longitude?.toFixed(2)} (${detail.location_status.replace(/_/g, ' ')})` : 'missing (headquarters only)'],
              ['Revenue proxy', fmtM(detail.revenue_musd, 0)], ['Value added', fmtM(detail.value_added_musd, 0)],
              ['Capacity', detail.capacity_tonnes_per_year != null ? `${detail.capacity_tonnes_per_year.toLocaleString()} t/yr` : 'not applicable / missing'],
              ['Input inventory', `${detail.inventory_days} days`], ['Alternative suppliers', fmtPct(detail.alternative_supplier_availability)], ['Operational criticality', fmtPct(detail.operational_criticality)],
              ['Supplier concentration (HHI)', detail.supplier_concentration_hhi != null ? detail.supplier_concentration_hhi.toFixed(2) : '—'],
              ['Single-source inputs', detail.single_source_inputs.length ? detail.single_source_inputs.map(title).join(', ') : 'none'],
              ['Missing fields', detail.missing_fields.length ? detail.missing_fields.join(', ') : 'none']] as [string, string][]).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-taupe pb-1"><dt className="text-warm">{k}</dt><dd className="text-right">{v}</dd></div>))}
          </dl>
          <p className="mt-3 text-[0.7rem] text-warm">Provenance: {detail.provenance} · confidence {detail.confidence}</p>
        </Panel>
        <Panel title="Direct hazard exposure & disruption" subtitle={`Scenario: ${run?.scenario.name}`}>
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div><p className="eyebrow">Hazard intensity here</p><p className="font-serif text-2xl num">{im.hazard_intensity.toFixed(2)}</p><p className="text-warm">index 0–1</p></div>
              <div><p className="eyebrow">Hop order</p><p className="font-serif text-2xl">{orderLabel(im.hop_order)}</p></div>
              <div><p className="eyebrow">Direct disruption</p><p className="font-serif text-2xl num">{fmtPct(im.direct_disruption, 1)}</p></div>
              <div><p className="eyebrow">Final disruption</p><p className="font-serif text-2xl num">{fmtPct(im.final_disruption, 1)}</p></div>
              <div><p className="eyebrow">Direct loss</p><p className="num text-base">{fmtM(im.direct_loss_musd)}</p></div>
              <div><p className="eyebrow">Indirect loss</p><p className="num text-base">{fmtM(im.indirect_loss_musd)}</p></div>
            </div>
            <div><p className="eyebrow mb-1">Vulnerability (synthetic proxy)</p>
              {([['Flood', detail.flood_vulnerability], ['Heat', detail.heat_vulnerability], ['Drought', detail.drought_vulnerability]] as [string, number][]).map(([k, v]) => (
                <div key={k} className="mb-1 flex items-center gap-2"><span className="w-14">{k}</span><div className="flex-1"><MiniBar value={v} /></div><span className="num w-10 text-right">{v.toFixed(2)}</span></div>))}
            </div>
            <p className="text-warm">{im.evidence_label}</p>
          </div>
        </Panel>
        <Panel title="Systemic vulnerability score" subtitle="Ranking aid 0–100 · not a loss estimate">
          <p className="font-serif text-4xl num">{sys.score.toFixed(1)}<span className="ml-2 text-sm text-warm">rank {sys.rank} of {graph?.nodes.length}</span></p>
          <div className="mt-3 h-48" aria-label="Score components"><ResponsiveContainer><BarChart data={contrib} layout="vertical" margin={{ left: 20 }}><CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" tick={{ fontSize: 10 }} stroke={CHART.neutral} />
            <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} stroke={CHART.neutral} /><Tooltip /><Bar isAnimationActive={false} dataKey="pts" name="Points" fill={CHART.ink} /></BarChart></ResponsiveContainer></div>
          <p className="mt-2 text-[0.7rem] text-warm">Downstream reach {sys.downstream_reach} entities · {sys.out_degree} direct customers (Σ dependency {sys.weighted_out_dependency.toFixed(1)}). Centrality is not climate risk.</p>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Suppliers" subtitle={`${deps.suppliers.length} direct · ${deps.n_upstream} upstream within 3 hops`}><Rel rows={deps.suppliers} onOpen={(e) => nav(`/entity/${e}`)} empty="No modelled suppliers (primary producer or unmodelled)." /></Panel>
        <Panel title="Customers" subtitle={`${deps.customers.length} direct · ${deps.n_downstream} downstream within 3 hops`}><Rel rows={deps.customers} onOpen={(e) => nav(`/entity/${e}`)} empty="No modelled customers (end of chain)." /></Panel>
      </div>

      <Panel title="How this entity receives the shock" subtitle="Per incoming link: supplier disruption × transmission factor">
        {impact.incoming_transmission.length === 0 ? <Empty>No incoming supply-channel links. (Financial links, if listed above, are not propagated.)</Empty> : (
          <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Supplier</th><th>Input</th><th>Supplier disruption</th><th>Transmission</th><th>Passed shock</th></tr></thead>
            <tbody>{impact.incoming_transmission.map((t) => <tr key={t.supplier_id + t.product}><td>{t.supplier}</td><td>{title(t.product)}</td><td className="num">{fmtPct(t.supplier_disruption, 1)}</td><td className="num">{fmtPct(t.transmission, 1)}</td><td className="num">{fmtPct(t.passed_shock, 1)}</td></tr>)}</tbody></table></div>)}
        {impact.dominant_paths[0] && <p className="mt-3 text-xs"><strong>Dominant path:</strong> {impact.dominant_paths[0].names.join(' → ')} <span className="text-warm">({(impact.dominant_paths[0].cumulative_transmission * 100).toFixed(1)}% cumulative)</span></p>}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Alternative-supplier options" subtitle={detail.output_product ? `Other producers of ${title(detail.output_product)} in the network (synthetic)` : ''}>
          {alternatives.length === 0 ? <Empty>No alternative producers of this output are modelled.</Empty> : (
            <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Candidate</th><th>Country</th><th>Scenario status</th></tr></thead>
              <tbody>{alternatives.map((a) => <tr key={a.id} className="row-click" onClick={() => nav(`/entity/${a.id}`)}><td>{a.name}</td><td>{a.country}</td><td>{title(impacts.get(a.id)?.status ?? 'unaffected')}</td></tr>)}</tbody></table></div>)}
        </Panel>
        <Panel title="Mitigation opportunities" subtitle="Hypothetical single interventions at this entity under the active scenario">
          {!mit ? <Empty>{im.status === 'unaffected' ? 'Entity is not affected by this scenario; nothing to mitigate here.' : 'Evaluating interventions…'}</Empty> : (
            <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Intervention</th><th>Loss reduction (network)</th><th>Annualised cost</th></tr></thead>
              <tbody>{mit.options.map((o) => <tr key={o.label}><td>{o.label}</td><td className="num">{fmtM(o.effect.loss_reduction_musd)}{o.effect.loss_reduction_fraction != null && <span className="text-warm"> ({fmtPct(o.effect.loss_reduction_fraction, 1)})</span>}</td><td className="num">{fmtM(o.cost.annualised_cost_musd, 2)}</td></tr>)}</tbody></table></div>)}
          <p className="mt-3 text-[0.7rem] text-warm">Costs are synthetic placeholders. Compare combinations in the <Link className="underline" to="/mitigation">Mitigation laboratory</Link>.</p>
        </Panel>
      </div>
      <Caveat>This profile describes a synthetic entity. Locations, vulnerabilities, inventories and relationships are assumptions, not measurements.</Caveat>
    </div>
  )
}
