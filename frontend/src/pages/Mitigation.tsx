import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Plus, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { Intervention, InterventionType, MitigationOption, MitigationResult } from '../api/types'
import { useApp } from '../state/AppState'
import { Caveat, Empty, ErrorBox, Field, Loading, PageHeader, Panel } from '../components/ui'
import { fmtM, fmtPct, title } from '../lib/format'
import { CHART } from '../lib/colors'

const TYPES: { v: InterventionType; label: string; unit: string; def: number; min: number; max: number; step: number }[] = [
  { v: 'inventory_buffer', label: 'Increase inventory buffers', unit: 'extra days', def: 14, min: 1, max: 120, step: 1 },
  { v: 'supplier_diversification', label: 'Diversify suppliers / alternative sourcing', unit: 'share of flow moved', def: 0.5, min: 0.1, max: 1, step: 0.05 },
  { v: 'input_substitution', label: 'Qualify substitute inputs', unit: 'substitutability +', def: 0.2, min: 0.05, max: 0.9, step: 0.05 },
  { v: 'facility_protection', label: 'Protect exposed facilities', unit: 'vulnerability reduction', def: 0.4, min: 0.1, max: 0.95, step: 0.05 },
  { v: 'cold_chain_resilience', label: 'Improve cold-chain resilience', unit: 'vulnerability reduction', def: 0.4, min: 0.1, max: 0.95, step: 0.05 },
  { v: 'relocate_storage', label: 'Relocate critical storage', unit: 'vulnerability reduction', def: 0.85, min: 0.3, max: 0.95, step: 0.05 },
]
type Draft = Intervention & { key: number }

function OptionCard({ o, base }: { o: MitigationOption; base: number }) {
  return (
    <div className="border border-taupe bg-paper p-4 text-xs">
      <p className="font-serif text-base leading-snug">{o.label}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <div><dt className="eyebrow">Mitigated loss</dt><dd className="num text-sm">{fmtM(o.effect.mitigated_loss_musd)}</dd></div>
        <div><dt className="eyebrow">Reduction</dt><dd className="num text-sm">{fmtM(o.effect.loss_reduction_musd)} {o.effect.loss_reduction_fraction != null && `(${fmtPct(o.effect.loss_reduction_fraction, 1)})`}</dd></div>
        <div><dt className="eyebrow">Annualised cost*</dt><dd className="num">{fmtM(o.cost.annualised_cost_musd, 2)}</dd></div>
        <div><dt className="eyebrow">Benefit-cost ratio</dt><dd className="num">{o.benefit_cost_ratio != null ? `${o.benefit_cost_ratio.toFixed(2)} (${o.bcr_low?.toFixed(2)}–${o.bcr_high?.toFixed(2)})` : '—'}</dd></div>
        <div><dt className="eyebrow">Time / feasibility</dt><dd className="num">{o.cost.time_months} mo · {fmtPct(o.cost.feasibility)}</dd></div>
        <div><dt className="eyebrow">Estimate confidence</dt><dd className="num">{fmtPct(o.cost.estimate_confidence)}</dd></div>
      </dl>
      {o.priority_score != null && <p className="mt-2"><strong>Priority score {o.priority_score.toFixed(1)}</strong> <span className="text-warm">(benefit {o.priority_components?.benefit.toFixed(2)}, BCR {o.priority_components?.benefit_cost_ratio.toFixed(2)}, feasibility {o.priority_components?.feasibility.toFixed(2)})</span></p>}
      {o.notes.length > 0 && <ul className="mt-2 list-disc pl-4 text-warm">{o.notes.slice(0, 4).map((n, i) => <li key={i}>{title(n.product)} → {n.note}{n.shifted_musd > 0 && ` (${fmtM(n.shifted_musd)})`}</li>)}</ul>}
      <p className="sr-only">Baseline {base}</p>
    </div>
  )
}

export default function Mitigation() {
  const { graph, activeId, active, depthOverride } = useApp()
  const [drafts, setDrafts] = useState<Draft[]>([{ key: 1, type: 'inventory_buffer', entity_ids: [], magnitude: 14 }])
  const [p, setP] = useState(0.1)
  const [res, setRes] = useState<MitigationResult | null>(null)
  const [rec, setRec] = useState<MitigationResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const names = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n.name])), [graph])

  useEffect(() => {
    if (!activeId) return
    let dead = false
    setRec(null); setRes(null)
    api.recommendations(activeId, p, 8, depthOverride).then((r) => !dead && setRec(r)).catch((e: Error) => !dead && setErr(e.message))
    return () => { dead = true }
  }, [activeId, p, depthOverride])

  const compare = async () => {
    if (!activeId) return
    setBusy(true); setErr(null)
    try { setRes(await api.mitigationCompare(activeId, drafts.map(({ key, ...d }) => d), p, depthOverride)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const upd = (k: number, patch: Partial<Draft>) => setDrafts((ds) => ds.map((d) => (d.key === k ? { ...d, ...patch } : d)))
  const chart = res ? [{ name: 'Baseline', direct: res.baseline.direct_loss_musd, indirect: res.baseline.indirect_loss_musd },
    ...res.options.map((o) => ({ name: o.label.length > 28 ? o.label.slice(0, 26) + '…' : o.label, direct: o.effect.mitigated_direct_musd, indirect: o.effect.mitigated_indirect_musd })),
    ...(res.combined ? [{ name: 'Combined package', direct: res.combined.effect.mitigated_direct_musd, indirect: res.combined.effect.mitigated_indirect_musd }] : [])] : []

  if (!graph || !active) return <Loading label="Loading" />
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Mitigation laboratory" title="Compare hypothetical interventions">
        Re-runs the propagation engine with changed parameters under <strong>{active.name}</strong>. Nothing here has been implemented in the real world; costs are synthetic placeholders.
      </PageHeader>
      {err && <ErrorBox message={err} />}
      <Panel title="Build a comparison" subtitle="Each intervention is evaluated alone; with several, a combined package is also shown"
        right={<div className="w-44"><label className="lbl" htmlFor="prob">Annual event probability</label><input id="prob" type="number" className="field" min={0.01} max={1} step={0.01} value={p} onChange={(e) => setP(Math.min(1, Math.max(0.01, Number(e.target.value))))} /></div>}>
        <div className="space-y-4">
          {drafts.map((d) => {
            const meta = TYPES.find((t) => t.v === d.type)!
            return (
              <div key={d.key} className="grid items-end gap-3 border-b border-taupe pb-4 md:grid-cols-[1.4fr_1.6fr_1fr_auto]">
                <Field label="Intervention"><select className="field" value={d.type} onChange={(e) => { const t = TYPES.find((x) => x.v === e.target.value)!; upd(d.key, { type: t.v, magnitude: t.def }) }}>{TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}</select></Field>
                <Field label="Target entities" hint={d.entity_ids.length ? undefined : d.type === 'cold_chain_resilience' || d.type === 'relocate_storage' ? 'Default: all cold-chain / storage nodes' : 'Choose at least one'}>
                  <select className="field" value="" aria-label="Add target" onChange={(e) => e.target.value && upd(d.key, { entity_ids: [...new Set([...d.entity_ids, e.target.value])] })}>
                    <option value="">Add entity…</option>{graph.nodes.filter((n) => n.entity_type !== 'financial').map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
                  </select>
                  {d.entity_ids.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{d.entity_ids.map((id) => <button key={id} className="btn btn-ghost !py-0.5 text-[0.7rem]" aria-label={`Remove ${names.get(id) ?? id}`} onClick={() => upd(d.key, { entity_ids: d.entity_ids.filter((x) => x !== id) })}>{names.get(id) ?? id} ×</button>)}</div>}
                </Field>
                <Field label={`${meta.unit}: ${d.magnitude}`}><input type="range" min={meta.min} max={meta.max} step={meta.step} value={d.magnitude ?? meta.def} onChange={(e) => upd(d.key, { magnitude: Number(e.target.value) })} className="range" aria-label="Magnitude" /></Field>
                <div className="flex gap-1">
                  {d.entity_ids.length > 0 && <button className="btn btn-ghost" onClick={() => upd(d.key, { entity_ids: [] })}>Clear</button>}
                  <button className="btn btn-ghost" aria-label="Remove intervention" disabled={drafts.length < 2} onClick={() => setDrafts(drafts.filter((x) => x.key !== d.key))}><Trash2 size={13} /></button>
                </div>
              </div>)
          })}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn" disabled={drafts.length >= 12} onClick={() => setDrafts([...drafts, { key: Date.now(), type: 'inventory_buffer', entity_ids: [], magnitude: 14 }])}><Plus size={13} />Add intervention</button>
          <button className="btn btn-primary" disabled={busy || drafts.some((d) => d.entity_ids.length === 0 && !['cold_chain_resilience', 'relocate_storage'].includes(d.type))} onClick={compare}>{busy ? 'Comparing…' : 'Compare with baseline'}</button>
          <button className="btn btn-ghost" onClick={() => { setRes(null); setDrafts([{ key: Date.now(), type: 'inventory_buffer', entity_ids: [], magnitude: 14 }]) }}>Reset</button>
        </div>
      </Panel>

      {res && (
        <Panel title="Baseline vs mitigated" subtitle="Network-aware loss, USD million">
          <div className="h-72" aria-label="Mitigation comparison chart"><ResponsiveContainer><BarChart data={chart}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 10 }} stroke={CHART.neutral} interval={0} /><YAxis tick={{ fontSize: 11 }} stroke={CHART.neutral} />
            <Tooltip formatter={(v) => fmtM(Number(v))} /><Legend /><Bar isAnimationActive={false} dataKey="direct" stackId="a" name="Direct" fill={CHART.direct} /><Bar isAnimationActive={false} dataKey="indirect" stackId="a" name="Indirect" fill={CHART.indirect} /></BarChart></ResponsiveContainer></div>
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {res.options.map((o) => <OptionCard key={o.label} o={o} base={res.baseline.total_loss_musd} />)}
            {res.combined && <OptionCard o={res.combined} base={res.baseline.total_loss_musd} />}
          </div>
          <ul className="mt-4 list-disc pl-4 text-xs text-warm">{res.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          <p className="mt-2 text-xs text-warm">*Cost basis: {res.options[0]?.cost.basis}. Priority weights: {Object.entries(res.priority_weights).map(([k, v]) => `${title(k)} ${v}`).join(', ')}.</p>
        </Panel>
      )}

      <Panel title="Recommended interventions for this scenario" subtitle={rec ? `${rec.candidates_evaluated} candidates evaluated; top ${rec.options.length} by transparent priority score` : 'Evaluating candidates…'}>
        {!rec ? <Loading label="Evaluating candidate interventions" /> : rec.options.length === 0 ? <Empty>No affected entities to mitigate.</Empty> : (
          <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>#</th><th>Intervention</th><th>Reduction</th><th>Cost/yr*</th><th>BCR</th><th>Time</th><th>Feasibility</th><th>Score</th><th></th></tr></thead>
            <tbody>{rec.options.map((o, i) => <tr key={o.label}><td>{i + 1}</td><td>{o.label}</td><td className="num">{fmtM(o.effect.loss_reduction_musd)}</td><td className="num">{fmtM(o.cost.annualised_cost_musd, 2)}</td><td className="num">{o.benefit_cost_ratio?.toFixed(2) ?? '—'}</td><td className="num">{o.cost.time_months} mo</td><td className="num">{fmtPct(o.cost.feasibility)}</td><td className="num">{o.priority_score?.toFixed(1)}</td><td><button className="btn btn-ghost !py-1" onClick={() => { setDrafts(o.interventions.map((iv, k) => ({ ...iv, key: Date.now() + k }))); setRes(null); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>Load</button></td></tr>)}</tbody></table></div>
        )}
        <div className="mt-4"><Caveat title="Not an optimiser">This ranks a fixed candidate list with a configurable score. It does not solve a constrained optimisation, and the event probability ({fmtPct(p)}) and all costs are analyst placeholders. See <Link className="underline" to="/methodology">methodology</Link>.</Caveat></div>
      </Panel>
    </div>
  )
}
