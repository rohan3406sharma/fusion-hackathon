import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Sparkles } from 'lucide-react'
import { api } from '../api/client'
import type { CopilotAnswer, CopilotFact, CopilotFocus, CopilotReport, CopilotSentence, CopilotStatus, Provenance } from '../api/types'
import { Badge, Caveat, ErrorBox, Panel } from './ui'
import { downloadText } from '../lib/export'

const PROV: Record<Provenance, { label: string; tone: 'neutral' | 'gold' | 'direct' | 'dark' }> = {
  synthetic_input: { label: 'Synthetic input', tone: 'neutral' },
  model_assumption: { label: 'Model assumption', tone: 'neutral' },
  real_hazard_context: { label: 'Real hazard context', tone: 'gold' },
  unvalidated_model_output: { label: 'Unvalidated model output', tone: 'direct' },
  model_robustness: { label: 'Ranking stability under draws', tone: 'dark' },
  empirically_validated: { label: 'Empirically validated', tone: 'gold' },
}
const SECTION_TITLES: Record<string, string> = {
  answer: 'Answer', why_it_matters: 'Why it matters', how_it_propagates: 'How it propagates', holdings_affected: 'Holdings affected',
  mitigations: 'Mitigations the model evaluated', uncertainty: 'What remains uncertain',
}
export const SECTION_ORDER = ['answer', 'why_it_matters', 'how_it_propagates', 'holdings_affected', 'mitigations', 'uncertainty']
export const DEFAULT_QUESTION = 'Explain why this matters, how it propagates, what could help and what is uncertain.'
const SUGGESTIONS = [DEFAULT_QUESTION, 'Which holdings are most exposed and why?', 'Summarise this for a board member in plain language.']

export function ProvenanceChips({ provenance }: { provenance: Provenance[] }) {
  return <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">{provenance.map((p) => <Badge key={p} tone={PROV[p].tone}>{PROV[p].label}</Badge>)}</span>
}

function Sentence({ s, facts }: { s: CopilotSentence; facts: Map<string, CopilotFact> }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="text-sm leading-relaxed" data-testid="copilot-sentence">
      {s.text}
      <ProvenanceChips provenance={s.provenance} />
      <button className="ml-2 text-[0.7rem] text-warm underline decoration-taupe underline-offset-4" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'hide evidence' : `evidence (${s.cites.length})`}</button>
      {s.template && <span className="ml-2 text-[0.65rem] uppercase tracking-[0.12em] text-warm">template</span>}
      {open && (
        <ul className="mt-1 space-y-0.5 border-l border-taupe pl-3 text-xs text-warm">
          {s.cites.map((c) => { const f = facts.get(c); return f && <li key={c}><span className="num text-charcoal">{f.rendered.length > 90 ? f.rendered.slice(0, 90) + '…' : f.rendered}</span> · {f.label} <code className="ml-1 text-[0.65rem]">{f.source}</code></li> })}
        </ul>
      )}
    </li>
  )
}

export default function CopilotPanel({ focus, subtitle }: { focus: CopilotFocus | null; subtitle?: string }) {
  const [status, setStatus] = useState<CopilotStatus | null>(null)
  const [question, setQuestion] = useState(DEFAULT_QUESTION)
  const [ans, setAns] = useState<CopilotAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [report, setReport] = useState<CopilotReport | null>(null)
  const [repBusy, setRepBusy] = useState(false)
  const [useModel, setUseModel] = useState(false)
  const key = useMemo(() => JSON.stringify(focus), [focus])
  const seq = useRef(0)

  useEffect(() => { api.copilotStatus().then(setStatus).catch(() => setStatus(null)) }, [])
  useEffect(() => { setAns(null); setReport(null); setErr(null); seq.current++ }, [key])   // a new focus invalidates the old answer
  useEffect(() => {
    if (!busy) return
    setElapsed(0)
    const t = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(t)
  }, [busy])

  const facts = useMemo(() => new Map((ans?.facts ?? []).map((f) => [f.id, f])), [ans])
  const llmReady = !!status && status.configured_provider !== 'deterministic' && (status.configured_provider === 'ollama' ? status.ollama.reachable && status.ollama.model_present : status.anthropic.configured)

  const ask = async () => {
    if (!focus) return
    const my = ++seq.current
    setBusy(true); setErr(null)
    try { const a = await api.copilotAsk(focus, question); if (my === seq.current) setAns(a) }
    catch (e) { if (my === seq.current) setErr((e as Error).message) }
    finally { if (my === seq.current) setBusy(false) }
  }
  const makeReport = async () => {
    if (!focus) return
    setRepBusy(true); setErr(null)
    try { setReport(await api.copilotReport(focus, useModel)) } catch (e) { setErr((e as Error).message) } finally { setRepBusy(false) }
  }

  return (
    <Panel title="AI Climate Risk Copilot" subtitle={subtitle ?? 'Explains deterministic results; it never calculates them'}
      right={status && (
        <span className="text-[0.7rem] text-warm" data-testid="copilot-status">
          {llmReady ? <>Local model ready: <strong className="text-charcoal">{status.configured_provider === 'ollama' ? status.ollama.model : status.anthropic.model}</strong></> : <>Language model not available · deterministic templates in use</>}
        </span>
      )}>
      <div className="space-y-4" aria-live="polite">
        {!focus ? <p className="text-sm text-warm">Choose an event, scenario or plan to ask about.</p> : (
          <>
            <div>
              <label className="lbl" htmlFor="copilot-q">Your question</label>
              <div className="flex flex-wrap gap-2">
                <input id="copilot-q" className="field min-w-[16rem] flex-1" value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !busy && question.trim().length >= 3) ask() }} />
                <button className="btn btn-primary" disabled={busy || question.trim().length < 3} onClick={ask}><Sparkles size={14} />{busy ? 'Reading the evidence…' : 'Ask'}</button>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">{SUGGESTIONS.map((q) => <button key={q} className="btn btn-ghost !py-1 text-[0.7rem]" disabled={busy} onClick={() => setQuestion(q)}>{q.length > 44 ? q.slice(0, 42) + '…' : q}</button>)}</div>
            </div>

            {busy && (
              <div className="border border-dashed border-warm/40 p-4 text-sm text-warm" role="status" data-testid="copilot-loading">
                {llmReady ? <>The local model is reading the fact sheet ({elapsed}s). The first request can take up to about 90 seconds while the model loads; later ones take 10–40 seconds.</> : <>Building the answer from deterministic templates ({elapsed}s).</>}
              </div>
            )}
            {err && <ErrorBox message={err} onRetry={ask} />}

            {ans && !busy && (
              <div className="space-y-5 fade-in" data-testid="copilot-answer">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge tone={ans.mode === 'llm' ? 'gold' : 'neutral'}>{ans.mode === 'llm' ? `Language-model phrasing, validated (${ans.model})` : 'Deterministic template'}</Badge>
                  <span className="text-warm">{(ans.latency_ms / 1000).toFixed(1)} s</span>
                  {ans.fallback_reason && <span className="text-warm" data-testid="copilot-fallback">Why templates: {ans.fallback_reason}</span>}
                </div>
                {ans.unsupported.length > 0 && (
                  <Caveat title="Not answered">
                    <ul className="mt-1 list-disc pl-4" data-testid="copilot-unsupported">{ans.unsupported.map((u) => <li key={u}>{u}</li>)}</ul>
                  </Caveat>
                )}
                {SECTION_ORDER.filter((k) => ans.sections[k]?.length).map((k) => (
                  <section key={k}>
                    <h3 className="mb-1 text-base">{SECTION_TITLES[k]}</h3>
                    <ul className="space-y-2">{ans.sections[k].map((s, i) => <Sentence key={i} s={s} facts={facts} />)}</ul>
                  </section>
                ))}
                <Caveat title="How to read this">{ans.standing_notes[ans.standing_notes.length - 1]} Rankings that hold under the parameter draws are shown separately from loss amounts, which stay unvalidated.</Caveat>
                <details className="text-xs text-warm">
                  <summary className="cursor-pointer">Evidence: the {ans.facts.length} facts this answer may draw on</summary>
                  <div className="mt-2 max-h-80 overflow-auto">
                    <table className="tbl"><thead><tr><th>Fact</th><th>Value</th><th>Provenance</th><th>Source field</th></tr></thead>
                      <tbody>{ans.facts.map((f) => <tr key={f.id}><td>{f.label}</td><td className="num">{f.rendered.length > 70 ? f.rendered.slice(0, 70) + '…' : f.rendered}</td><td>{PROV[f.provenance].label}</td><td><code>{f.source}</code></td></tr>)}</tbody></table>
                  </div>
                </details>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3 border-t border-taupe pt-4">
              <button className="btn" disabled={repBusy} onClick={makeReport}><Download size={13} />{repBusy ? 'Preparing…' : 'Executive summary'}</button>
              <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={useModel} disabled={!llmReady} onChange={(e) => setUseModel(e.target.checked)} />Let the local model phrase it (validated; templates if it fails)</label>
              {report && <button className="btn btn-ghost" onClick={() => downloadText(`${report.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 60)}.md`, report.markdown, 'text/markdown')}><Download size={13} />Download .md</button>}
            </div>
            {report && (
              <div data-testid="copilot-report">
                <p className="mb-1 text-xs text-warm">{report.mode === 'llm' ? 'Phrased by the language model and validated.' : 'Deterministic template'}{report.fallback_reason ? ` · ${report.fallback_reason}` : ''}</p>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap bg-taupe/50 p-3 text-xs leading-relaxed">{report.markdown}</pre>
              </div>
            )}
          </>
        )}
      </div>
    </Panel>
  )
}
