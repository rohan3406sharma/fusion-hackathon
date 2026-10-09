import type { RunResult } from '../api/types'

export function downloadText(filename: string, text: string, mime = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const runToJson = (r: RunResult) => JSON.stringify(r, null, 2)

export function runToCsv(r: RunResult): string {
  const cols = ['entity_id', 'name', 'entity_type', 'food_category', 'country', 'status', 'hop_order', 'direct_disruption', 'final_disruption', 'direct_loss_musd', 'indirect_loss_musd', 'total_loss_musd'] as const
  const esc = (v: unknown) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  const meta = ['scenario_id', 'scenario_name', 'data_status']
  const row = (e: RunResult['entities'][number]) => [r.scenario_id ?? '', r.scenario.name, e.synthetic ? 'synthetic' : 'observed', ...cols.map((c) => e[c])].map(esc).join(',')
  return [[...meta, ...cols].join(','), ...r.entities.map(row)].join('\n')
}
