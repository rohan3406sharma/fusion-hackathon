import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { Hazard, ScenarioSpec } from '../api/types'
import { useApp } from '../state/AppState'
import { Caveat, ErrorBox, Field, PageHeader, Panel } from '../components/ui'
import { title } from '../lib/format'

type Mode = 'footprint' | 'regions' | 'entities'
interface HazardDraft extends Hazard { mode: Mode }

const blankHazard = (): HazardDraft => ({ hazard_type: 'flood', intensity: 0.6, duration_days: 14, center_lat: 30.4, center_lon: 76.2, radius_km: 150, regions: [], affected_entity_ids: [], label: '', mode: 'footprint' })

export function validateDraft(name: string, hazards: HazardDraft[]): string[] {
  const errs: string[] = []
  if (!name.trim()) errs.push('Scenario name is required.')
  hazards.forEach((h, i) => {
    const n = `Hazard ${i + 1}`
    if (h.intensity < 0 || h.intensity > 1) errs.push(`${n}: intensity must be between 0 and 1.`)
    if (!(h.duration_days >= 1 && h.duration_days <= 730)) errs.push(`${n}: duration must be 1–730 days.`)
    if (h.mode === 'footprint' && !(h.radius_km && h.radius_km > 0 && h.center_lat != null && h.center_lon != null)) errs.push(`${n}: footprint needs a centre and a radius.`)
    if (h.mode === 'regions' && !h.regions.length) errs.push(`${n}: select at least one region.`)
    if (h.mode === 'entities' && !h.affected_entity_ids.length) errs.push(`${n}: select at least one facility.`)
  })
  return errs
}

export default function Builder() {
  const { graph, active, refreshScenarios } = useApp()
  const nav = useNavigate()
  const [name, setName] = useState('Custom food-chain stress test')
  const [desc, setDesc] = useState('')
  const [hazards, setHazards] = useState<HazardDraft[]>([blankHazard()])
  const [adv, setAdv] = useState({ propagation_max_depth: 6, inventory_scale: 1, substitution_scale: 1, dependency_scale: 1, compound_amplification: 0, monte_carlo_runs: 500, monte_carlo_seed: 42, time_horizon_year: 2035, use_graph_alternatives: true, cycle_damping: 0.5 })
  const [entQ, setEntQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [serverErr, setServerErr] = useState<string | null>(null)

  const regions = useMemo(() => [...new Set((graph?.nodes ?? []).map((n) => n.region).filter((r): r is string => !!r && r !== 'n/a'))].sort(), [graph])
  const errs = validateDraft(name, hazards)

  const loadFrom = (s: ScenarioSpec) => {
    setName(`${s.name} (copy)`); setDesc(s.description)
    setHazards(s.hazards.map((h) => ({ ...h, mode: h.radius_km ? 'footprint' : h.regions.length ? 'regions' : 'entities' })))
    setAdv({ propagation_max_depth: s.propagation_max_depth, inventory_scale: s.inventory_scale, substitution_scale: s.substitution_scale, dependency_scale: s.dependency_scale, compound_amplification: s.compound_amplification, monte_carlo_runs: s.monte_carlo_runs, monte_carlo_seed: s.monte_carlo_seed, time_horizon_year: s.time_horizon_year, use_graph_alternatives: s.use_graph_alternatives ?? true, cycle_damping: s.cycle_damping ?? 0.5 })
  }
  useEffect(() => { if (active) loadFrom(active) }, [active?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const upd = (i: number, p: Partial<HazardDraft>) => setHazards((hs) => hs.map((h, k) => (k === i ? { ...h, ...p } : h)))
  const centreOn = (i: number, id: string) => { const n = graph?.nodes.find((x) => x.id === id); if (n?.latitude != null) upd(i, { center_lat: n.latitude, center_lon: n.longitude }) }

  const submit = async () => {
    setServerErr(null); setBusy(true)
    const spec: ScenarioSpec = {
      name: name.trim(), description: desc, data_source: 'synthetic_footprint', ...adv,
      hazards: hazards.map(({ mode, ...h }) => ({
        ...h,
        center_lat: mode === 'footprint' ? h.center_lat : null, center_lon: mode === 'footprint' ? h.center_lon : null, radius_km: mode === 'footprint' ? h.radius_km : null,
        regions: mode === 'regions' ? h.regions : [], affected_entity_ids: mode === 'entities' ? h.affected_entity_ids : [],
      })),
    }
    try { const rec = await api.createScenario(spec); await refreshScenarios(rec.id); nav('/results') }
    catch (e) { setServerErr((e as Error).message) }
    finally { setBusy(false) }
  }
  const num = (v: string) => (v === '' ? 0 : Number(v))
  const nameOf = (id: string) => graph?.nodes.find((n) => n.id === id)?.name ?? id
  const entsFor = (sel: string[]) => (graph?.nodes ?? []).filter((n) => !entQ || n.name.toLowerCase().includes(entQ.toLowerCase()) || n.id.includes(entQ.toLowerCase()) || sel.includes(n.id)).sort((a, b) => Number(sel.includes(b.id)) - Number(sel.includes(a.id)) || a.name.localeCompare(b.name)).slice(0, 60)

  return (
    <div>
      <PageHeader eyebrow="Climate scenario builder" title="Configure a physical climate shock"
        actions={<button className="btn" onClick={() => active && loadFrom(active)}>Reset to active scenario</button>}>
        Define hazards, where they strike, and the resilience assumptions that moderate propagation. Hazard intensity is a dimensionless index on a synthetic footprint.
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Panel title="Scenario">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Name"><input className="field" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} aria-label="Scenario name" /></Field>
              <Field label="Time horizon (year)" hint="Label only; the synthetic engine has no climate-projection dependence."><input type="number" className="field" min={2020} max={2100} value={adv.time_horizon_year} onChange={(e) => setAdv({ ...adv, time_horizon_year: num(e.target.value) })} /></Field>
              <div className="md:col-span-2"><Field label="Description"><input className="field" value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={1000} /></Field></div>
            </div>
          </Panel>
          {hazards.map((h, i) => (
            <Panel key={i} title={`Hazard ${i + 1}`} right={hazards.length > 1 && <button className="btn btn-ghost" aria-label={`Remove hazard ${i + 1}`} onClick={() => setHazards(hazards.filter((_, k) => k !== i))}><Trash2 size={13} /></button>}>
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Hazard type">
                  <select className="field" aria-label={`Hazard type ${i + 1}`} value={h.hazard_type} onChange={(e) => upd(i, { hazard_type: e.target.value as Hazard['hazard_type'] })}>
                    <option value="flood">Flood</option><option value="heat">Extreme heat</option><option value="drought">Drought</option>
                  </select>
                </Field>
                <Field label={`Intensity index: ${h.intensity.toFixed(2)}`} hint="0–1 scenario index (not metres or °C)">
                  <input type="range" min={0} max={1} step={0.05} value={h.intensity} onChange={(e) => upd(i, { intensity: Number(e.target.value) })} className="range" aria-label={`Intensity ${i + 1}`} />
                </Field>
                <Field label="Duration (days)"><input type="number" className="field" min={1} max={730} value={h.duration_days} onChange={(e) => upd(i, { duration_days: num(e.target.value) })} aria-label={`Duration ${i + 1}`} /></Field>
              </div>
              <div className="mt-5">
                <p className="lbl">Where does it strike?</p>
                <div className="mb-3 flex flex-wrap gap-2">
                  {(['footprint', 'regions', 'entities'] as Mode[]).map((m) => (
                    <button key={m} className={`btn ${h.mode === m ? 'btn-primary' : 'btn-ghost'}`} onClick={() => upd(i, { mode: m })}>{m === 'footprint' ? 'Circular footprint' : m === 'regions' ? 'Named regions' : 'Specific facilities'}</button>
                  ))}
                </div>
                {h.mode === 'footprint' && (
                  <div className="grid gap-4 md:grid-cols-4">
                    <Field label="Centre latitude"><input type="number" className="field" value={h.center_lat ?? ''} onChange={(e) => upd(i, { center_lat: num(e.target.value) })} /></Field>
                    <Field label="Centre longitude"><input type="number" className="field" value={h.center_lon ?? ''} onChange={(e) => upd(i, { center_lon: num(e.target.value) })} /></Field>
                    <Field label="Radius (km)"><input type="number" className="field" min={1} value={h.radius_km ?? ''} onChange={(e) => upd(i, { radius_km: num(e.target.value) })} /></Field>
                    <Field label="Centre on facility">
                      <select className="field" defaultValue="" onChange={(e) => e.target.value && centreOn(i, e.target.value)}>
                        <option value="">Choose…</option>{(graph?.nodes ?? []).filter((n) => n.latitude != null).map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
                      </select>
                    </Field>
                  </div>
                )}
                {h.mode === 'regions' && (
                  <div className="grid max-h-48 grid-cols-2 gap-1 overflow-y-auto border border-taupe p-3 md:grid-cols-3">
                    {regions.map((r) => <label key={r} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={h.regions.includes(r)} onChange={(e) => upd(i, { regions: e.target.checked ? [...h.regions, r] : h.regions.filter((x) => x !== r) })} />{r}</label>)}
                  </div>
                )}
                {h.mode === 'entities' && (
                  <div>
                    <input className="field mb-2" placeholder="Search facilities…" value={entQ} onChange={(e) => setEntQ(e.target.value)} aria-label="Search facilities" />
                    {h.affected_entity_ids.length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{h.affected_entity_ids.map((id) => <button key={id} className="btn btn-ghost !py-1 text-xs" aria-label={`Remove ${nameOf(id)}`} onClick={() => upd(i, { affected_entity_ids: h.affected_entity_ids.filter((x) => x !== id) })}>{nameOf(id)} ×</button>)}</div>}
                    <div className="grid max-h-48 grid-cols-1 gap-1 overflow-y-auto border border-taupe p-3 md:grid-cols-2">
                      {entsFor(h.affected_entity_ids).map((n) => <label key={n.id} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={h.affected_entity_ids.includes(n.id)} onChange={(e) => upd(i, { affected_entity_ids: e.target.checked ? [...h.affected_entity_ids, n.id] : h.affected_entity_ids.filter((x) => x !== n.id) })} />{n.name}<span className="text-warm">({title(n.entity_type)})</span></label>)}
                    </div>
                    <p className="mt-1 text-xs text-warm">{h.affected_entity_ids.length} selected</p>
                  </div>
                )}
              </div>
            </Panel>
          ))}
          <button className="btn" disabled={hazards.length >= 4} onClick={() => setHazards([...hazards, { ...blankHazard(), hazard_type: 'heat' }])}><Plus size={13} />Add compound / consecutive hazard</button>
          <Panel title="Propagation & resilience assumptions" subtitle="These scale the per-edge factors documented in the methodology">
            <div className="grid gap-4 md:grid-cols-3">
              <Field label={`Propagation depth: ${adv.propagation_max_depth} hops`} hint="Hops of supplier → customer transmission to simulate"><input type="range" min={1} max={10} value={adv.propagation_max_depth} onChange={(e) => setAdv({ ...adv, propagation_max_depth: Number(e.target.value) })} className="range" aria-label="Propagation depth" /></Field>
              <Field label={`Inventory buffers ×${adv.inventory_scale.toFixed(2)}`}><input type="range" min={0} max={3} step={0.05} value={adv.inventory_scale} onChange={(e) => setAdv({ ...adv, inventory_scale: Number(e.target.value) })} className="range" aria-label="Inventory scale" /></Field>
              <Field label={`Substitution & alternatives ×${adv.substitution_scale.toFixed(2)}`}><input type="range" min={0} max={2} step={0.05} value={adv.substitution_scale} onChange={(e) => setAdv({ ...adv, substitution_scale: Number(e.target.value) })} className="range" aria-label="Substitution scale" /></Field>
              <Field label={`Dependency strength ×${adv.dependency_scale.toFixed(2)}`}><input type="range" min={0.25} max={1.5} step={0.05} value={adv.dependency_scale} onChange={(e) => setAdv({ ...adv, dependency_scale: Number(e.target.value) })} className="range" aria-label="Dependency scale" /></Field>
              <Field label={`Compound amplification ${(adv.compound_amplification * 100).toFixed(0)}%`} hint="Analyst assumption; applies only where hazards overlap"><input type="range" min={0} max={0.5} step={0.05} disabled={hazards.length < 2} value={adv.compound_amplification} onChange={(e) => setAdv({ ...adv, compound_amplification: Number(e.target.value) })} className="range" aria-label="Compound amplification" /></Field>
              <Field label={`Feedback-loop damping ×${adv.cycle_damping.toFixed(2)}`} hint="Multiplier on links inside supply loops (1 = undamped)"><input type="range" min={0} max={1} step={0.05} value={adv.cycle_damping} onChange={(e) => setAdv({ ...adv, cycle_damping: Number(e.target.value) })} className="range" aria-label="Feedback-loop damping" /></Field>
              <label className="flex items-start gap-2 text-xs"><input type="checkbox" className="mt-0.5" checked={adv.use_graph_alternatives} onChange={(e) => setAdv({ ...adv, use_graph_alternatives: e.target.checked })} aria-label="Use modelled alternative suppliers" />
                <span>Use modelled alternative suppliers: same-product producers in the graph can cover a shortfall from their spare capacity, unless they are hit too</span></label>
              <div className="grid grid-cols-2 items-start gap-3">
                <Field label="MC runs"><input type="number" className="field" min={0} max={5000} value={adv.monte_carlo_runs} onChange={(e) => setAdv({ ...adv, monte_carlo_runs: num(e.target.value) })} /></Field>
                <Field label="Seed"><input type="number" className="field" min={0} value={adv.monte_carlo_seed} onChange={(e) => setAdv({ ...adv, monte_carlo_seed: num(e.target.value) })} /></Field>
              </div>
            </div>
          </Panel>
        </div>
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Panel title="Run analysis">
            {errs.length > 0 ? <ul className="mb-3 list-disc space-y-1 pl-4 text-xs text-direct" role="alert">{errs.map((e) => <li key={e}>{e}</li>)}</ul> : <p className="mb-3 text-xs text-warm">Ready. The backend will validate, store and run this scenario, then open the results.</p>}
            {serverErr && <div className="mb-3"><ErrorBox message={serverErr} /></div>}
            <button className="btn btn-primary w-full justify-center" disabled={errs.length > 0 || busy} onClick={submit}>{busy ? 'Running…' : 'Run analysis'}</button>
          </Panel>
          <Caveat>The footprint is a synthetic circle with Gaussian fall-off, not a hazard map. Duration enters the direct-disruption proxy and the inventory-buffer test.</Caveat>
        </aside>
      </div>
    </div>
  )
}
