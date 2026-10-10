import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { BookOpen, FlaskConical, Gauge, LayoutDashboard, Menu, Network, ScanSearch, SlidersHorizontal, UserSearch, X } from 'lucide-react'
import { useApp } from '../state/AppState'
import { Badge } from './ui'
import { HoldingViewToggle } from './Holdings'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/finder', label: 'Hidden exposure finder', icon: ScanSearch },
  { to: '/network', label: 'Supply-chain graph', icon: Network },
  { to: '/scenario', label: 'Scenario builder', icon: SlidersHorizontal },
  { to: '/results', label: 'Scenario results', icon: Gauge },
  { to: '/entity', label: 'Entity intelligence', icon: UserSearch },
  { to: '/mitigation', label: 'Mitigation laboratory', icon: FlaskConical },
  { to: '/methodology', label: 'Data & methodology', icon: BookOpen },
]

export default function Shell() {
  const [open, setOpen] = useState(false)
  const { scenarios, activeId, setActive, active, run, loading, depthOverride, metadata } = useApp()
  const nav = (
    <nav aria-label="Primary" className="mt-8 flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
          className={({ isActive }) => `flex items-center gap-3 border-l-2 px-3 py-2.5 text-sm transition-colors ${isActive ? 'border-gold bg-white font-medium text-charcoal' : 'border-transparent text-warm hover:text-charcoal'}`}>
          <Icon size={15} strokeWidth={1.5} />{label}
        </NavLink>
      ))}
    </nav>
  )
  return (
    <div className="min-h-screen md:grid md:grid-cols-[250px_1fr]">
      <aside className="hidden border-r border-taupe bg-[#f4f1ec] p-6 md:block">
        <div className="sticky top-6">
          <p className="eyebrow">FIN-04</p>
          <p className="mt-1 font-serif text-xl leading-snug">Climate Exposure Graph</p>
          <div className="mt-4 flex items-center gap-2"><span className="h-px w-6 bg-gold" /><span className="text-[0.7rem] uppercase tracking-[0.16em] text-gold-dark">Food &amp; Beverage</span></div>
          {nav}
          <div className="mt-10 space-y-2 text-[0.7rem] leading-relaxed text-warm">
            <Badge tone="gold">Synthetic demo data</Badge>
            <p>{metadata?.model_status.validated === false ? 'Model not calibrated or validated against observed events.' : ''}</p>
          </div>
        </div>
      </aside>
      <div className="min-w-0">
        <div className="sticky top-0 z-30 border-b border-taupe bg-alabaster/95 backdrop-blur">
          <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 md:px-8">
            <button className="btn btn-ghost md:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu size={16} /></button>
            <span className="eyebrow hidden sm:inline">Active scenario</span>
            <select aria-label="Active scenario" className="field max-w-[22rem] flex-1 sm:flex-none" value={activeId ?? ''} onChange={(e) => setActive(e.target.value)}>
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}{s.builtin ? '' : ' (custom)'}</option>)}
            </select>
            <div className="ml-auto flex flex-wrap items-center gap-2 text-[0.7rem] text-warm">
              <HoldingViewToggle />
              {active && <span className="num">{active.hazards.map((h) => h.hazard_type).join(' + ')} · {run?.summary.max_depth_used ?? active.propagation_max_depth}-hop{depthOverride ? ' (override)' : ''} · {run ? `${run.summary.effective_duration_days.toFixed(0)} d` : ''}</span>}
              <Badge tone={loading ? 'gold' : 'neutral'}>{loading ? 'Running model' : 'Model idle'}</Badge>
              <Badge>Synthetic</Badge>
            </div>
          </div>
        </div>
        {open && (
          <div className="fixed inset-0 z-40 bg-charcoal/40 md:hidden" onClick={() => setOpen(false)}>
            <div className="h-full w-72 bg-[#f4f1ec] p-6" onClick={(e) => e.stopPropagation()}>
              <button className="btn btn-ghost" aria-label="Close navigation" onClick={() => setOpen(false)}><X size={16} /></button>
              <p className="mt-4 font-serif text-xl">Climate Exposure Graph</p>
              <p className="mt-1 text-[0.7rem] uppercase tracking-[0.16em] text-gold-dark">Food &amp; Beverage</p>
              {nav}
            </div>
          </div>
        )}
        <main className="px-4 py-8 md:px-8 lg:px-12"><Outlet /></main>
      </div>
    </div>
  )
}
