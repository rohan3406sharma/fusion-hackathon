export const fmtM = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? '—' : `$${v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}M`
export const fmtPct = (v: number | null | undefined, digits = 0) => (v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`)
export const fmtNum = (v: number | null | undefined, digits = 2) => (v == null || Number.isNaN(v) ? '—' : v.toFixed(digits))
export const fmtRank = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1))
export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
export const title = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
export const ORDER_LABEL: Record<number, string> = { 0: 'Direct', 1: 'First-order', 2: 'Second-order', 3: 'Third-order' }
export const orderLabel = (hop: number | null | undefined) => (hop == null ? 'Unaffected' : hop >= 4 ? `Order ${hop} (deep)` : ORDER_LABEL[hop])
