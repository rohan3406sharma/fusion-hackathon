import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

export function PageHeader({ eyebrow, title, children, actions }: { eyebrow: string; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4 fade-in">
      <div className="max-w-3xl">
        <p className="eyebrow mb-2">{eyebrow}</p>
        <h1 className="text-3xl md:text-4xl leading-tight">{title}</h1>
        {children && <p className="mt-3 text-sm text-warm leading-relaxed">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

export function Panel({ title, subtitle, children, className = '', right, id }: { title?: string; subtitle?: string; children: ReactNode; className?: string; right?: ReactNode; id?: string }) {
  return (
    <section id={id} className={`min-w-0 scroll-mt-20 bg-paper hairline shadow-soft ${className}`}>
      {(title || right) && (
        <div className="flex items-start justify-between gap-3 border-b border-taupe px-5 py-3">
          <div>
            {title && <h2 className="text-lg">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-warm">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function Kpi({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean }) {
  return (
    <div className={`bg-paper hairline p-4 ${accent ? 'border-l-2 border-l-gold' : ''}`} data-testid="kpi">
      <p className="eyebrow">{label}</p>
      <p className="mt-2 font-serif text-3xl num">{value}</p>
      {sub && <p className="mt-1 text-xs text-warm">{sub}</p>}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'gold' | 'direct' | 'dark' }) {
  const t = { neutral: 'bg-taupe text-warm', gold: 'bg-gold-soft text-gold-ink', direct: 'bg-direct-soft text-direct', dark: 'bg-charcoal text-alabaster' }[tone]
  return <span className={`inline-block px-1.5 py-0.5 text-[0.62rem] font-medium uppercase tracking-[0.12em] ${t}`}>{children}</span>
}
export const SynBadge = () => <Badge>Synthetic</Badge>

export function Caveat({ children, title = 'Model-dependent' }: { children: ReactNode; title?: string }) {
  return (
    <div className="border-l-2 border-gold bg-callout px-4 py-3 text-xs leading-relaxed text-charcoal" role="note">
      <span className="eyebrow mr-2 text-gold-dark">{title}</span>{children}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return <div className="p-8 text-sm text-warm" role="status" aria-live="polite">{label}…</div>
}
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 border border-direct bg-direct-soft p-4 text-sm" role="alert">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-direct" />
      <div className="flex-1"><p className="font-medium text-direct">Something went wrong</p><p className="mt-1 text-charcoal">{message}</p></div>
      {onRetry && <button className="btn" onClick={onRetry}>Retry</button>}
    </div>
  )
}
export const Empty = ({ children }: { children: ReactNode }) => <div className="border border-dashed border-warm/40 p-8 text-center text-sm text-warm">{children}</div>

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <div><label className="lbl">{label}</label>{children}{hint && <p className="mt-1 text-[0.7rem] text-warm">{hint}</p>}</div>
}

export function Bar({ value, max = 1, color = '#1A1A1A' }: { value: number; max?: number; color?: string }) {
  return <div className="h-1.5 w-full bg-taupe"><div className="h-full" style={{ width: `${Math.min(100, (value / (max || 1)) * 100)}%`, background: color }} /></div>
}
