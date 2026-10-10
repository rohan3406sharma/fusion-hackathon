import { Link } from 'react-router-dom'
import type { CompanyStructure, SegmentRow } from '../api/types'
import { useApp } from '../state/AppState'
import { fmtPct } from '../lib/format'

const HATCH = 'repeating-linear-gradient(45deg, #ded6cb 0 3px, #f4f1ec 3px 6px)'

/** Global switch: a holding is a company made of business units (default) or each held unit on its own (v0.3). */
export function HoldingViewToggle() {
  const { holdingView, setHoldingView } = useApp()
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Holding view">
      <span className="eyebrow hidden 2xl:inline">Holdings as</span>
      {(['company', 'business_unit'] as const).map((v) => (
        <button key={v} className={`btn !px-2 !py-1 !text-[0.7rem] ${holdingView === v ? 'btn-primary' : 'btn-ghost'}`} aria-pressed={holdingView === v}
          title={v === 'company' ? 'A holding is a company: its disruption is the value-added-weighted average of its business units' : 'Each held business unit is its own holding (the v0.3 view)'}
          onClick={() => setHoldingView(v)}>{v === 'company' ? 'Companies' : 'Business units'}</button>
      ))}
    </div>
  )
}

/** Value-added bar: one block per business unit (width = its share of value added; gold fill from the left = its disruption)
 *  and a hatched block for the share outside F&B, which is not modelled. */
export function SegmentBar({ segments, other }: { segments: SegmentRow[]; other?: number | null }) {
  return (
    <div className="flex h-5 w-full overflow-hidden border border-taupe bg-paper" aria-hidden="true">
      {segments.map((s) => (
        <div key={s.entity_id} className="relative h-full border-r-2 border-paper bg-taupe" style={{ width: `${s.share * 100}%` }}
          title={`${s.segment}: ${fmtPct(s.share)} of value added, ${fmtPct(s.network_disruption, 1)} disrupted`}>
          <div className="absolute left-0 top-0 h-full bg-gold" style={{ width: `${Math.min(100, s.network_disruption * 100)}%` }} />
        </div>
      ))}
      {other ? <div className="h-full" style={{ width: `${other * 100}%`, background: HATCH }} title={`Outside food & beverage: ${fmtPct(other)} of value added, not modelled`} /> : null}
    </div>
  )
}

/** One company's business units and the three ways of reading its disruption (all modelled, synthetic structure). */
export function CompanyBreakdown({ h }: { h: CompanyStructure & { name: string; network_disruption: number; segments?: SegmentRow[] | null } }) {
  if (!h.segments?.length) return null
  return (
    <div className="space-y-2" data-testid="company-breakdown">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">{h.name}</p>
        <p className="num text-xs text-warm">company <strong className="text-charcoal">{fmtPct(h.network_disruption, 1)}</strong>
          {h.other_businesses_share ? <> · up to {fmtPct(h.network_disruption_if_other_hit, 1)} if its non-F&amp;B businesses were hit as hard</> : null}
          {h.network_disruption_one_node != null && <> · {fmtPct(h.network_disruption_one_node, 1)} as one node</>}</p>
      </div>
      <SegmentBar segments={h.segments} other={h.other_businesses_share} />
      <ul className="grid gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2">
        {h.segments.map((s) => (
          <li key={s.entity_id} className="num"><span className="mr-1 inline-block h-2 w-2 bg-gold align-middle" />
            <Link className="underline decoration-taupe underline-offset-4" to={`/entity/${s.entity_id}`}>{s.segment}</Link>: {fmtPct(s.share)} of value added · {fmtPct(s.network_disruption, 1)} disrupted</li>
        ))}
        {h.other_businesses_share ? <li className="num text-warm"><span className="mr-1 inline-block h-2 w-2 align-middle" style={{ background: HATCH }} />Outside food &amp; beverage: {fmtPct(h.other_businesses_share)} of value added · not modelled</li> : null}
      </ul>
    </div>
  )
}

/** Compact one-line summary of a company's units, for table cells. */
export const segmentSummary = (segments: SegmentRow[], other?: number | null) =>
  segments.map((s) => `${s.segment} ${fmtPct(s.network_disruption)}`).join(' · ') + (other ? ` · ${fmtPct(other)} outside F&B (not modelled)` : '')
