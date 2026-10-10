import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ScanSearch } from 'lucide-react'
import { api } from '../api/client'
import type { FinderEvent, FinderRequest, FinderResult, OptimiseResult, StructureView } from '../api/types'
import { useApp } from '../state/AppState'
import { Badge, Bar, Caveat, Empty, ErrorBox, Field, Kpi, Loading, PageHeader, Panel } from '../components/ui'
import CopilotPanel from '../components/CopilotPanel'
import { CompanyBreakdown } from '../components/Holdings'
import type { CopilotFocus } from '../api/types'
import { fmtM, fmtPct, title } from '../lib/format'

const HAZARDS = ['flood', 'heat', 'drought'] as const
const RADII = [150, 350]
const pct2 = (v: number) => fmtPct(v, 2)
const short = (name: string) => name.split(' ')[0]

function EventTable({ rows, onPromote, busyId, hiddenList, onExplain, explainId }: { rows: FinderEvent[]; onPromote: (e: FinderEvent) => void; busyId: string | null; hiddenList: boolean; onExplain: (e: FinderEvent) => void; explainId: string | null }) {
  if (!rows.length) return <Empty>No events in this list for the current settings.</Empty>
  return (
    <div className="overflow-x-auto">
      <table className="tbl" data-testid={hiddenList ? 'hidden-table' : 'event-table'}>
        <thead><tr><th>#</th><th>Event</th><th>Portfolio impact</th><th>Location-only</th><th>Hidden share</th><th>Holdings reached</th><th>P(top 5)</th><th></th></tr></thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td className="num">{e.rank}</td>
              <td className="min-w-[16rem]">
                <span className="font-medium">{e.label}</span>{e.hidden_only && <> <Badge tone="gold">Hidden only</Badge></>}
                {e.jrc_flood_check && <p className={`mt-0.5 text-[0.7rem] ${e.jrc_flood_check.startsWith('no') ? 'text-direct' : 'text-warm'}`}>JRC 100-yr river-flood map: {e.jrc_flood_check}</p>}
                <p className="mt-0.5 text-[0.7rem] text-warm">{e.kind === 'node' ? 'Single-node shock' : 'Regional footprint'}{e.variants ? ` · ${e.variants} near-duplicate variant${e.variants > 1 ? 's' : ''} collapsed` : ''}</p>
                {e.top_holdings.length > 0 && <p className="mt-0.5 text-[0.7rem] text-warm">Hits: {e.top_holdings.slice(0, 3).map((h) => h.name).join(', ')}</p>}
              </td>
              <td className="num">{pct2(e.portfolio_network_impact)}</td>
              <td className="num">{pct2(e.portfolio_location_impact)}</td>
              <td className="num"><span className="mr-2">{fmtPct(e.hidden_share)}</span><span className="inline-block w-14 align-middle"><Bar value={e.hidden_share} color="#9A7B17" /></span></td>
              <td className="num">{e.holdings_affected}</td>
              <td className="num">{e.p_top5 == null ? '—' : <>{fmtPct(e.p_top5)}{e.fragile && <> <Badge tone="direct">Fragile</Badge></>}</>}</td>
              <td className="whitespace-nowrap">
                <button className={`btn !py-1 ${explainId === e.id ? 'btn-primary' : 'btn-ghost'}`} aria-pressed={explainId === e.id} aria-label={`Explain ${e.label}`} onClick={() => onExplain(e)}>Explain</button>{' '}
                <button className="btn btn-ghost !py-1" disabled={busyId !== null} onClick={() => onPromote(e)}>{busyId === e.id ? 'Opening…' : 'Open as scenario'}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const VIEW_SHORT: Record<StructureView['view'], string> = {
  business_unit: 'Business units (v0.3)', company: 'Companies (this view)', company_if_other_hit: 'Companies, non-F&B hit too', company_one_node: 'Company as one node',
}

/** Same library, four definitions of a holding: why counting a company's business units changes the answer. */
function CompanyView({ res, selected }: { res: FinderResult; selected: FinderEvent | null }) {
  const sc = res.structure_comparison
  if (!sc) return null
  const multi = (e: FinderEvent | null) => (e ? e.top_holdings.filter((h) => h.kind === 'multi_segment' && h.segments?.length) : [])
  const fallback = [...res.hidden_only_events, ...res.events].find((e) => multi(e).length > 0) ?? null
  const ev = multi(selected).length ? selected : fallback
  const own = sc.hidden_only_events_on_own_sites
  return (
    <Panel id="companies" title="Companies, not just business units" subtitle={`${sc.n_multi_segment} holdings own several business units (synthetic structures): ${sc.multi_segment_holdings.join(', ')}`}>
      <p className="text-sm">A listed holding is a company. A company's disruption here is the value-added-weighted average of its business units, so a shock to one unit is diluted by the others; any share outside food &amp; beverage is <strong>not modelled</strong>, and the upper end treats it as hit like the rest. The same event library is scored four ways below.</p>
      <div className="mt-4 overflow-x-auto">
        <table className="tbl" data-testid="structure-table">
          <thead><tr><th>Holdings counted as</th><th>Holdings</th><th>Hidden-only events</th><th>Top hidden-only event</th><th>Mean of the 10 worst events</th></tr></thead>
          <tbody>{sc.views.map((v) => (
            <tr key={v.view} className={v.view === 'company' ? 'font-medium' : ''}>
              <td title={v.label}>{VIEW_SHORT[v.view]}</td><td className="num">{v.n_holdings}</td><td className="num">{v.n_hidden_only}</td>
              <td>{v.top_hidden_only ? <>{v.top_hidden_only.label} <span className="num text-warm">{pct2(v.top_hidden_only.impact)}</span></> : '—'}</td>
              <td className="num">{pct2(v.mean_top10_impact)}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {own != null && own > 0 && <p className="mt-3 text-xs text-warm"><strong className="text-charcoal">{own}</strong> events that look hidden-only when each business unit is its own holding hit a unit the company itself owns once the whole company is counted: a site check of the company would see them.</p>}
      {ev && (
        <div className="mt-5 space-y-4 border-t border-taupe pt-4">
          <p className="eyebrow">{ev === selected ? 'Selected event' : 'Highest-ranked event reaching a multi-segment company'}: {ev.label}</p>
          {multi(ev).map((h) => <CompanyBreakdown key={h.entity_id} h={h} />)}
        </div>
      )}
      <p className="mt-4 text-xs text-warm">{sc.note} Diversification inside a company is not immunity: research also finds shocks travelling between a firm's own plants (Giroud &amp; Mueller 2019; Seetharam 2018), which the one-node row bounds from above.</p>
    </Panel>
  )
}

function copilotFocus(on: 'event' | 'plan', eventId: string | null, finder: FinderRequest, budget: number, exhaustive: boolean): CopilotFocus | null {
  if (on === 'event') return eventId ? { kind: 'finder_event', event_id: eventId, finder } : null
  return { kind: 'mitigation_plan', optimise: { budget_musd: budget, finder: { ...finder, stability_draws: 0, include_pairs: false }, exhaustive_check: exhaustive, robustness_draws: 50 } }
}

export default function Finder() {
  const { refreshScenarios, depthOverride, holdingView } = useApp()
  const nav = useNavigate()
  const [hazards, setHazards] = useState<string[]>([...HAZARDS])
  const [radii, setRadii] = useState<number[]>(RADII)
  const [intensity, setIntensity] = useState(0.8)
  const [draws, setDraws] = useState(200)
  const [seed, setSeed] = useState(42)
  const [res, setRes] = useState<FinderResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [tab, setTab] = useState<'hidden' | 'all'>('hidden')
  const [sortBy, setSortBy] = useState<'impact' | 'reach'>('impact')
  const [promoting, setPromoting] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [explainId, setExplainId] = useState<string | null>(null)
  const [copilotOn, setCopilotOn] = useState<'event' | 'plan'>('event')
  const [budget, setBudget] = useState(3)
  const [exhaustive, setExhaustive] = useState(true)
  const [opt, setOpt] = useState<OptimiseResult | null>(null)
  const [optBusy, setOptBusy] = useState(false)

  const body = (): FinderRequest => ({ hazards: hazards as FinderRequest['hazards'], radii_km: radii, intensity, stability_draws: draws, seed, max_depth: depthOverride ?? 6, holding_view: holdingView })
  const search = async () => {
    setBusy(true); setErr(null); setOpt(null)
    try { setRes(await api.finder(body())) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  useEffect(() => { search() }, [holdingView]) // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => {
    const list = res ? (tab === 'hidden' ? res.hidden_only_events : res.events) : []
    return sortBy === 'impact' ? list : [...list].sort((a, b) => b.holdings_affected - a.holdings_affected || b.portfolio_network_impact - a.portfolio_network_impact)
  }, [res, tab, sortBy])

  const promote = async (e: FinderEvent) => {
    setPromoting(e.id); setErr(null)
    try { const rec = await api.promote(e.hazard_component, e.label, depthOverride ?? 6); await refreshScenarios(rec.id); nav('/results') }
    catch (x) { setErr((x as Error).message) } finally { setPromoting(null) }
  }
  const optimise = async () => {
    setOptBusy(true); setErr(null)
    try { setOpt(await api.optimise({ budget_musd: budget, finder: { ...body(), stability_draws: 0, include_pairs: false }, exhaustive_check: exhaustive, robustness_draws: 50 })) }
    catch (x) { setErr((x as Error).message) } finally { setOptBusy(false) }
  }
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const maxCell = res ? Math.max(1e-12, ...res.matrix.flatMap((m) => Object.values(m.values))) : 1
  // order holding columns by how much upstream exposure they carry, so the active cells come first
  const cols = useMemo(() => (res ? [...res.holdings].sort((a, b) => res.matrix.reduce((t, m) => t + (m.values[b.entity_id] ?? 0), 0) - res.matrix.reduce((t, m) => t + (m.values[a.entity_id] ?? 0), 0)) : []), [res])

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Hidden exposure finder · portfolio reverse stress test" title="Which climate event would hurt this portfolio most?">
        Instead of testing a scenario you chose, the engine scores every event in a generated library against the portfolio and ranks them.
        Hidden share is the part of each loss a location-only screen, which checks only the holdings' own sites, would not see.
      </PageHeader>

      <Panel title="Search settings" subtitle="Synthetic reference events: ranked by consequence, not likelihood"
        right={<button className="btn btn-primary" disabled={busy || !hazards.length || !radii.length} onClick={search}><ScanSearch size={14} />{busy ? 'Searching…' : 'Search'}</button>}>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-5">
          <fieldset><legend className="lbl">Hazards</legend>
            <div className="flex flex-wrap gap-3 text-sm">{HAZARDS.map((h) => <label key={h} className="flex items-center gap-1.5"><input type="checkbox" checked={hazards.includes(h)} onChange={() => setHazards(toggle(hazards, h))} />{title(h)}</label>)}</div>
          </fieldset>
          <fieldset><legend className="lbl">Footprint radii</legend>
            <div className="flex flex-wrap gap-3 text-sm">{RADII.map((r) => <label key={r} className="flex items-center gap-1.5"><input type="checkbox" checked={radii.includes(r)} onChange={() => setRadii(toggle(radii, r))} />{r} km</label>)}</div>
          </fieldset>
          <Field label={`Reference intensity: ${intensity.toFixed(2)}`} hint="Index 0–1, applied to every event"><input type="range" className="range" min={0.3} max={1} step={0.05} value={intensity} onChange={(e) => setIntensity(Number(e.target.value))} aria-label="Reference intensity" /></Field>
          <Field label="Uncertainty draws" hint="Re-rank the shortlist; 0 = skip">
            <select className="field" value={draws} onChange={(e) => setDraws(Number(e.target.value))} aria-label="Uncertainty draws">{[0, 200, 500, 1000].map((n) => <option key={n} value={n}>{n}</option>)}</select>
          </Field>
          <Field label="Seed"><input type="number" className="field" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} aria-label="Seed" /></Field>
        </div>
      </Panel>

      {err && <ErrorBox message={err} />}
      {!res ? <Loading label="Scoring the event library" /> : (
        <>
          <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${busy ? 'opacity-60' : ''}`}>
            <Kpi label="Events evaluated" value={res.n_events.toLocaleString()} sub={`${res.n_distinct_events} distinct after collapsing near-duplicates`} />
            <Kpi label="Hidden-only events" value={res.n_hidden_only} sub="No holding hit directly, yet the portfolio loses value" accent />
            <Kpi label="Ranking stability" value={res.stability?.kendall_tau_top20 != null ? `τ ${res.stability.kendall_tau_top20.toFixed(2)}` : '—'} sub={res.stability ? `Kendall τ of the top 20 across ${res.stability.n_draws} draws (seed ${res.stability.seed})` : 'Uncertainty draws switched off'} />
            <Kpi label="Runtime" value={`${res.runtime_seconds.toFixed(2)} s`} sub={`${res.n_node_events} single-node + ${res.n_footprint_events} footprint events`} />
          </div>

          <Panel title="Ranked events" subtitle="Portfolio impact = position-weighted share of the holdings' annual value added lost"
            right={<div className="flex flex-wrap gap-1">
              <button className={`btn ${tab === 'hidden' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('hidden')}>Hidden-only</button>
              <button className={`btn ${tab === 'all' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('all')}>All events</button>
              <select className="field !w-auto" aria-label="Sort events" value={sortBy} onChange={(e) => setSortBy(e.target.value as 'impact' | 'reach')}>
                <option value="impact">Sort by impact</option><option value="reach">Sort by holdings reached</option>
              </select>
            </div>}>
            <EventTable rows={showAll ? rows : rows.slice(0, 10)} onPromote={promote} busyId={promoting} hiddenList={tab === 'hidden'} explainId={explainId ?? res.hidden_only_events[0]?.id ?? null}
              onExplain={(e) => { setExplainId(e.id); setCopilotOn('event'); document.getElementById('copilot')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }} />
            {rows.length > 10 && <button className="btn btn-ghost mt-3" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show top 10' : `Show all ${rows.length}`}</button>}
            <p className="mt-3 text-xs text-warm">P(top 5) = share of uncertainty draws in which the event stays in the top 5 of this list. Fragile = in the deterministic top 5 but below 50%. Open as scenario stores the event as an ordinary scenario and opens it in Scenario results, where the propagation paths and graph are available.</p>
            <p className="mt-1 text-xs text-warm">Distinct events by hidden share: {res.hidden_share_curve.map((c) => <span key={c.threshold} className="num mr-3"><strong className="text-charcoal">{c.events}</strong> at ≥{fmtPct(c.threshold)}</span>)}</p>
          </Panel>

          <CompanyView res={res} selected={res.events.concat(res.hidden_only_events).find((e) => e.id === (explainId ?? res.hidden_only_events[0]?.id)) ?? null} />

          <div id="copilot" className="scroll-mt-20 space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-xs" role="group" aria-label="What to ask about">
              <span className="eyebrow">Ask about</span>
              <button className={`btn !py-1 ${copilotOn === 'event' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setCopilotOn('event')}>An event: {(res.events.concat(res.hidden_only_events).find((e) => e.id === (explainId ?? res.hidden_only_events[0]?.id))?.label ?? 'none').slice(0, 48)}</button>
              <button className={`btn !py-1 ${copilotOn === 'plan' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setCopilotOn('plan')}>The optimiser plan at ${budget}M a year</button>
            </div>
            <CopilotPanel focus={copilotFocus(copilotOn, explainId ?? res.hidden_only_events[0]?.id ?? null, body(), budget, exhaustive)} subtitle="Explains the selected event or plan from the deterministic results above; it never calculates them" />
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
            <Panel title="Who can hurt whom" subtitle="Upstream nodes the portfolio does not own × holdings: loss from each node's worst single-node event">
              {res.matrix.length === 0 ? <Empty>No upstream node reaches a holding.</Empty> : (
                <div className="overflow-x-auto">
                  <table className="tbl" data-testid="exposure-matrix">
                    <thead><tr><th>Upstream node</th>{cols.map((h) => <th key={h.entity_id} title={h.name} className="!px-1 text-center !text-[0.6rem]">{short(h.name)}</th>)}<th>Holdings</th></tr></thead>
                    <tbody>{res.matrix.slice(0, 12).map((m) => (
                      <tr key={m.entity_id}>
                        <td className="whitespace-nowrap"><Link className="underline decoration-taupe underline-offset-4" to={`/entity/${m.entity_id}`}>{m.name}</Link></td>
                        {cols.map((h) => {
                          const v = m.values[h.entity_id] ?? 0
                          return <td key={h.entity_id} className="!px-1" title={`${m.name} → ${h.name}: ${fmtPct(v, 3)} of annual value added`}>
                            <div className="mx-auto h-5 w-6 border border-taupe" style={{ background: v > 0 ? `rgba(154,123,23,${0.12 + 0.88 * Math.sqrt(v / maxCell)})` : 'transparent' }}><span className="sr-only">{fmtPct(v, 3)}</span></div>
                          </td>
                        })}
                        <td className="num">{m.holdings_reached}</td>
                      </tr>))}</tbody>
                  </table>
                </div>
              )}
              <p className="mt-2 text-xs text-warm">Darker cells carry more of a holding's loss (square-root scale). A row with several dark cells is a shared upstream dependency that no single holding's site check would reveal.</p>
            </Panel>
            <Panel title="Single points of failure" subtitle="Structural test: a full 60-day outage of one upstream node disrupts a holding by ≥20%">
              {res.single_points_of_failure.length === 0 ? <Empty>No single upstream node disrupts a holding by 20% or more.</Empty> : (
                <ul className="space-y-3 text-sm">{res.single_points_of_failure.slice(0, 8).map((s) => (
                  <li key={s.entity_id} className="border-b border-taupe pb-2">
                    <Link className="font-medium underline decoration-taupe underline-offset-4" to={`/entity/${s.entity_id}`}>{s.name}</Link> <span className="text-xs text-warm">({title(s.entity_type)})</span>
                    <p className="text-xs text-warm">{s.holdings.map((h) => `${h.name} ${fmtPct(h.network_disruption)}`).join(' · ')}</p>
                  </li>))}</ul>
              )}
              {res.structural_bound && (
                <div className="mt-5 border-l-2 border-gold pl-3 text-xs">
                  <p className="eyebrow">Structural bound · not a climate event</p>
                  <p className="mt-1">Worst pair of upstream outages: <strong>{res.structural_bound.top[0]?.entities.join(' + ')}</strong> ({pct2(res.structural_bound.top[0]?.impact ?? 0)} of annual value added).</p>
                  <p className="mt-1 text-warm">Exhaustive search over {res.structural_bound.n_pairs.toLocaleString()} pairs; greedy (best single node, then its best partner) {res.structural_bound.greedy_matches ? 'finds the same pair' : `reaches ${pct2(res.structural_bound.greedy.impact)}`}.</p>
                </div>
              )}
            </Panel>
          </div>

          <Panel title="Protect against these events" subtitle="Budget-constrained optimiser over the worst distinct events (placeholder costs)"
            right={<div className="flex flex-wrap items-end gap-2">
              <div><label className="lbl" htmlFor="budget">Budget, $M per year</label><input id="budget" type="number" className="field w-28" min={0.1} step={0.5} value={budget} onChange={(e) => setBudget(Math.max(0.1, Number(e.target.value)))} /></div>
              <label className="flex items-center gap-1.5 pb-2 text-xs"><input type="checkbox" checked={exhaustive} onChange={(e) => setExhaustive(e.target.checked)} />Check against brute force</label>
              <button className="btn btn-primary" disabled={optBusy} onClick={optimise}>{optBusy ? 'Optimising…' : 'Optimise'}</button>
            </div>}>
            {!opt ? <Empty>Choose a budget and run the optimiser. It picks interventions (one yes/no choice each) that minimise the mean portfolio impact of the 10 worst events, within the budget.</Empty> : (
              <div className="space-y-5" data-testid="optimiser-result">
                <div className="grid gap-3 md:grid-cols-4">
                  <Kpi label="Tail impact, before" value={pct2(opt.baseline_objective)} sub={`mean of the worst ${opt.tail_events} of ${opt.n_events} events`} />
                  <Kpi label="Tail impact, after" value={pct2(opt.plan_objective)} sub={`${opt.reduction_fraction != null ? fmtPct(opt.reduction_fraction, 1) : '—'} lower`} accent />
                  <Kpi label="Plan cost" value={fmtM(opt.plan_cost_musd, 2)} sub={`per year, of ${fmtM(opt.budget_musd, 1)} budget`} />
                  <Kpi label="Optimality gap" value={opt.exhaustive?.optimality_gap != null ? fmtPct(opt.exhaustive.optimality_gap, 1) : '—'} sub={opt.exhaustive ? `brute force over ${opt.exhaustive.n_feasible_plans} feasible plans (${opt.exhaustive.pool_note})` : 'brute-force check off'} />
                </div>
                {opt.plan.length === 0 ? <Empty>No affordable intervention reduces the tail impact at this budget.</Empty> : (
                  <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Intervention in the plan</th><th>Annualised cost</th><th>Reduction on its own</th></tr></thead>
                    <tbody>{opt.plan.map((p) => <tr key={p.label}><td>{p.label}</td><td className="num">{fmtM(p.annualised_cost_musd, 2)}</td><td className="num">{fmtPct(p.single_reduction / Math.max(opt.baseline_objective, 1e-12), 2)}</td></tr>)}</tbody></table></div>
                )}
                <div className="grid gap-4 text-xs md:grid-cols-2">
                  <div><p className="eyebrow mb-1">Cost sensitivity</p>{opt.cost_sensitivity.map((c) => <p key={c.cost_factor}>Costs ×{c.cost_factor}: {fmtPct(c.jaccard_with_base)} of the plan unchanged (Jaccard) · tail {pct2(c.objective)}</p>)}</div>
                  {opt.robustness && <div><p className="eyebrow mb-1">Robustness across {opt.robustness.n_draws} draws</p><p>Reduction positive in {fmtPct(opt.robustness.share_positive)} of draws; 5th–95th percentile {pct2(opt.robustness.p05)} to {pct2(opt.robustness.p95)} of annual value added.</p></div>}
                </div>
                <p className="text-xs text-warm">{opt.method} Greedy then local search{opt.local_search_improved ? ' (local search improved the greedy plan)' : ''}; {opt.evaluations} plans simulated in {opt.runtime_seconds} s.</p>
                <Caveat title="Not a recommendation">Costs, magnitudes and feasibility are synthetic placeholders and the events carry no probabilities, so this is the best plan under stated assumptions only. Nothing here has been implemented.</Caveat>
              </div>
            )}
          </Panel>

          {res.hazard_layer && (
            <Panel title="Real-data plausibility check" subtitle="The one real dataset in the finder: JRC / Copernicus river flood hazard, 100-year return period">
              <p className="text-sm">{res.hazard_layer.top20_flood_events_consistent} of the top {res.hazard_layer.top20_flood_events} flood events have modelled river flooding within 5 km of an entity they hit directly; {res.hazard_layer.flood_events_without_modelled_flooding} of {res.hazard_layer.flood_events_checked} flood events have none and are flagged in red.</p>
              {res.hazard_layer.entities_total != null && <p className="mt-2 text-sm"><strong>Read this against the base rate:</strong> {res.hazard_layer.entities_with_any_flooding} of {res.hazard_layer.entities_total} entities have some modelled flooding within 5 km, so this is a lenient filter that removes only clear misfits. It does not confirm or validate any simulated loss. {res.hazard_layer.entities_window_clipped} entities have their 5 km window truncated at a tile edge.</p>}
              <p className="mt-2 text-xs text-warm">{res.hazard_layer.caveat}</p>
              <p className="mt-1 text-xs text-warm">Source: {res.hazard_layer.citation} Licence: {res.hazard_layer.licence}. Retrieved {res.hazard_layer.retrieved}.</p>
            </Panel>
          )}

          <Panel title="Assumptions & limitations">
            <div className="grid gap-6 text-xs text-warm md:grid-cols-2">
              <ul className="list-disc space-y-1 pl-4">{res.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              <ul className="list-disc space-y-1 pl-4">{res.limitations.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
