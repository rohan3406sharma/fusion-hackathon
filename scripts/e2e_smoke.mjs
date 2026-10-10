// End-to-end smoke test: drives the real frontend (Vite dev server) against the real backend in headless Chrome.
// Usage: node scripts/e2e_smoke.mjs   (requires `npm i puppeteer-core` somewhere resolvable and CHROME_PATH or macOS Chrome)
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const URL_ = process.env.APP_URL ?? 'http://localhost:5173'
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const SHOTS = process.env.SHOT_DIR ?? fs.mkdtempSync(path.join(os.tmpdir(), 'fin04-shots-'))
const DL = fs.mkdtempSync(path.join(os.tmpdir(), 'fin04-dl-'))
const results = []
const step = async (name, fn) => {
  try { const note = await fn(); results.push([true, name, note ?? '']); console.log('PASS', name, note ?? '') }
  catch (e) { results.push([false, name, e.message]); console.log('FAIL', name, '-', e.message) }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], defaultViewport: { width: 1440, height: 1000 } })
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
const cdp = await page.createCDPSession()
await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DL })
const text = (sel) => page.$eval(sel, (e) => e.textContent)
const clickText = async (tag, label) => {
  const h = await page.evaluateHandle((t, l) => [...document.querySelectorAll(t)].find((e) => e.textContent.trim().includes(l)), tag, label)
  if (!h.asElement()) throw new Error(`no <${tag}> containing "${label}"`)
  await h.asElement().click()
}
const setVal = (sel, v) => page.$eval(sel, (e, val) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, val); e.dispatchEvent(new Event('input', { bubbles: true })) }, v)
const body = () => page.evaluate(() => document.body.innerText.toLowerCase())
const shot = (n) => page.screenshot({ path: path.join(SHOTS, `${n}.png`) })

await step('1-2 dashboard loads with backend KPIs', async () => {
  await page.goto(URL_, { waitUntil: 'networkidle0' })
  await page.waitForSelector('[data-testid=kpi]')
  const k = await page.$$eval('[data-testid=kpi]', (els) => els.map((e) => e.textContent))
  if (k.length < 6) throw new Error('expected >=6 KPIs')
  await shot('01-overview'); return k.slice(0, 4).join(' | ')
})
await step('3 graph renders actual backend nodes', async () => {
  await clickText('a', 'Supply-chain graph'); await page.waitForSelector('[data-testid=graph-canvas] canvas')
  await sleep(800)
  const n = await page.evaluate(() => window.__cy.nodes().length); if (n < 90) throw new Error(`only ${n} nodes`)
  await shot('02-graph'); return `${n} nodes, ${await page.evaluate(() => window.__cy.edges().length)} edges`
})
await step('4 select a facility -> detail panel updates', async () => {
  const pos = await page.evaluate(() => { const n = window.__cy.getElementById('mill_pb'); const r = document.querySelector('[data-testid=graph-canvas]').getBoundingClientRect(); const p = n.renderedPosition(); return { x: r.left + p.x, y: r.top + p.y } })
  await page.mouse.click(pos.x, pos.y); await page.waitForFunction(() => document.querySelector('[data-testid=detail-name]')?.textContent.includes('Ludhiana Flour'))
  await sleep(600); await page.screenshot({ path: path.join(SHOTS, '03-selected.png'), fullPage: true }); return await text('[data-testid=detail-name]')
})
await step('4b filters hide nodes', async () => {
  await page.type('#q', 'coffee'); await sleep(300)
  const shown = await text('[data-testid=visible-count]'); const hidden = await page.evaluate(() => window.__cy.nodes().filter((n) => n.style('display') === 'none').length)
  if (hidden < 80) throw new Error('filter did not hide nodes: ' + shown); await page.$eval('#q', (e) => (e.value = '')); return shown
})
await step('4c depth slider reruns model', async () => {
  await clickText('button', 'Reset filters')
  await page.$eval('#depth', (e) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, '1'); e.dispatchEvent(new Event('input', { bubbles: true })) })
  await page.waitForFunction(() => document.body.textContent.includes('Propagation depth: 1 hops')); await sleep(800)
  return await page.evaluate(() => [...document.querySelectorAll('span')].find((s) => s.textContent.includes('-hop'))?.textContent)
})
await step('J1 select Rotterdam Terminal Flood; results show hidden exposure + path to graph', async () => {
  await page.select('[aria-label="Active scenario"]', 'sc_rotterdam_port_flood'); await sleep(1200)
  await clickText('a', 'Scenario results')
  await page.waitForFunction(() => document.querySelector('h1')?.textContent.includes('Rotterdam Terminal Flood') && [...document.querySelectorAll('td span')].some((x) => x.textContent.trim().toLowerCase() === 'hidden exposure'), { timeout: 15000 })
  const t = await page.evaluate(() => document.body.innerText)
  if (!/▲\s*\d/.test(t)) throw new Error('no rank gain shown'); if (/▼\s*7/.test(t)) throw new Error('tie artefact: every tied holding shows a rank fall')
  await page.evaluate(() => [...document.querySelectorAll('a')].find((a) => a.textContent === 'View in graph').click())
  await page.waitForFunction(() => location.pathname === '/network' && location.search.includes('select='))
  await page.waitForFunction(() => document.querySelector('[data-testid=detail-name]')?.textContent.length > 0)
  const sel = await page.evaluate(() => window.__cy.nodes('.sel').length); if (sel !== 1) throw new Error('graph selection not applied: ' + sel)
  const hasPath = await page.evaluate(() => window.__cy.nodes('.pathn').length); await sleep(500); await shot('J1-path-in-graph'); return `selected + ${hasPath} path nodes`
})
await step('J2 Monte Carlo on Rotterdam + export contains scenario, assumptions, uncertainty', async () => {
  await clickText('a', 'Scenario results'); await page.waitForSelector('#mcn'); await clickText('button', 'Run uncertainty analysis')
  await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('median total loss'), { timeout: 30000 })
  fs.readdirSync(DL).forEach((f) => fs.unlinkSync(path.join(DL, f)))
  await clickText('button', 'Scenario report'); await clickText('button', 'CSV'); await sleep(1500)
  const md = fs.readdirSync(DL).find((f) => f.endsWith('.md')); const csv = fs.readdirSync(DL).find((f) => f.endsWith('.csv'))
  const m = fs.readFileSync(path.join(DL, md), 'utf8'); const c = fs.readFileSync(path.join(DL, csv), 'utf8')
  for (const k of ['Rotterdam Terminal Flood', '## Assumptions', '## Limitations', 'Monte Carlo', 'SYNTHETIC']) if (!m.includes(k)) throw new Error('report lacks ' + k)
  if (!c.split('\n')[1].includes('Rotterdam Terminal Flood')) throw new Error('csv lacks scenario'); return 'report + csv verified'
})
await step('C4 copilot on Scenario results (live local model)', async () => {
  await page.evaluate(() => document.getElementById('copilot').scrollIntoView()); await page.waitForSelector('#copilot-q'); await clickText('button', 'Ask')
  await page.waitForSelector('[data-testid=copilot-answer]', { timeout: 170000 })
  const t = await page.$eval('[data-testid=copilot-answer]', (e) => e.innerText)
  if (!/\$\d/.test(t) || !/Rotterdam/.test(t)) throw new Error('expected engine figures and the scenario in the answer'); await shot('C4-copilot-results'); return 'ok'
})
await step('J2b selection persists across reload; JSON export carries scenario, assumptions, uncertainty', async () => {
  await page.reload({ waitUntil: 'networkidle0' }); await page.waitForSelector('[aria-label="Active scenario"]'); await sleep(800)
  const v = await page.$eval('[aria-label="Active scenario"]', (e) => e.value); if (v !== 'sc_rotterdam_port_flood') throw new Error('scenario not persisted: ' + v)
  await clickText('a', 'Scenario results'); await page.waitForSelector('#mcn'); await clickText('button', 'Run uncertainty analysis')
  await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('median total loss'), { timeout: 30000 })
  fs.readdirSync(DL).forEach((f) => fs.unlinkSync(path.join(DL, f))); await clickText('button', 'JSON'); await sleep(1200)
  const j = JSON.parse(fs.readFileSync(path.join(DL, fs.readdirSync(DL).find((f) => f.endsWith('.json'))), 'utf8'))
  if (j.run.scenario.name !== 'Rotterdam Terminal Flood (single node)' || !j.run.assumptions.length || !j.run.limitations.length || !j.uncertainty?.interpretation || !j.exported_for.includes('synthetic')) throw new Error('json incomplete')
  return 'persisted + json verified'
})
await step('J3 mitigation: load a recommendation, compare with baseline', async () => {
  await clickText('a', 'Mitigation laboratory'); await page.waitForFunction(() => [...document.querySelectorAll('button')].some((b) => b.textContent === 'Load'), { timeout: 30000 })
  await clickText('button', 'Load'); await clickText('button', 'Compare with baseline'); await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('baseline vs mitigated'), { timeout: 20000 })
  await sleep(500); await shot('J3-mitigation'); return 'ok'
})
await step('F1 finder: search the event library, hidden-only ranking with stability', async () => {
  await clickText('a', 'Hidden exposure finder'); await page.waitForSelector('[data-testid=hidden-table]', { timeout: 30000 })
  const rows = await page.$$eval('[data-testid=hidden-table] tbody tr', (r) => r.length); if (rows < 5) throw new Error('few rows: ' + rows)
  const first = await page.$eval('[data-testid=hidden-table] tbody tr', (r) => r.textContent)
  if (!/Hidden only/i.test(first) || !/%/.test(first)) throw new Error('row content: ' + first.slice(0, 80))
  await page.select('select[aria-label="Sort events"]', 'reach'); await sleep(200)
  const reach = await page.$$eval('[data-testid=hidden-table] tbody tr td:nth-child(6)', (c) => c.map((x) => Number(x.textContent)))
  if (reach.some((v, i) => i && v > reach[i - 1])) throw new Error('not sorted by reach: ' + reach)
  await page.select('select[aria-label="Sort events"]', 'impact'); await sleep(200)
  await shot('F1-finder'); return `${rows} rows; top: ${first.slice(1, 50)}`
})
await step('F2 finder: open top hidden-only event as a scenario; Results reproduce its impact', async () => {
  const impact = await page.$eval('[data-testid=hidden-table] tbody tr td:nth-child(3)', (c) => c.textContent.trim())
  await page.evaluate(() => [...document.querySelectorAll('[data-testid=hidden-table] tbody tr:first-child button')].find((b) => b.textContent.includes('Open as scenario')).click())
  await page.waitForFunction(() => location.pathname === '/results', { timeout: 20000 })
  await page.waitForFunction(() => document.body.innerText.includes('Finder:'), { timeout: 20000 })
  await page.waitForFunction((v) => [...document.querySelectorAll('[data-testid=kpi]')].some((k) => k.textContent.includes(`0.00% → ${v}`)), { timeout: 20000 }, impact)
  return `finder ${impact} = results portfolio impact`
})
await step('F3 finder: optimiser plan within budget with brute-force gap', async () => {
  await clickText('a', 'Hidden exposure finder'); await page.waitForSelector('[data-testid=hidden-table]')
  await clickText('button', 'Optimise'); await page.waitForSelector('[data-testid=optimiser-result]', { timeout: 60000 })
  const t = await page.$eval('[data-testid=optimiser-result]', (e) => e.innerText)
  if (!/brute force over \d+ feasible plans/.test(t)) throw new Error('no gap check: ' + t.slice(0, 120))
  await shot('F3-optimiser'); return t.split('\n').slice(0, 4).join(' | ')
})
await step('F4 finder: holdings as companies vs business units (same events, different holding definition)', async () => {
  await clickText('a', 'Hidden exposure finder'); await page.waitForSelector('[data-testid=structure-table]', { timeout: 30000 })
  const kpi = () => page.evaluate(() => [...document.querySelectorAll('[data-testid=kpi]')].find((k) => k.textContent.includes('Hidden-only events'))?.querySelector('.font-serif')?.textContent)
  const company = await kpi()
  const rows = await page.$$eval('[data-testid=structure-table] tbody tr', (r) => r.map((x) => x.textContent))
  if (rows.length !== 4 || !rows[0].includes('Business units')) throw new Error('structure table: ' + rows.join(' | '))
  if (!(await page.$('[data-testid=company-breakdown]'))) throw new Error('no company breakdown shown')
  await clickText('button', 'Business units')
  await page.waitForFunction((c) => !document.querySelector('[data-testid=structure-table]') && [...document.querySelectorAll('[data-testid=kpi]')].some((k) => k.textContent.includes('Hidden-only events') && !k.textContent.includes(`Hidden-only events${c}`)), { timeout: 30000 }, company)
  const units = await kpi()
  if (!rows[0].includes(units)) throw new Error(`business-unit count ${units} not the table's ${rows[0]}`)
  await clickText('button', 'Companies'); await page.waitForSelector('[data-testid=structure-table]', { timeout: 30000 })
  await shot('F4-companies'); return `hidden-only: companies ${company}, business units ${units}`
})
await step('C1 copilot (live local model): explain the top hidden-only event; values come from the engine', async () => {
  await clickText('a', 'Hidden exposure finder'); await page.waitForSelector('[data-testid=hidden-table]', { timeout: 30000 })
  const impact = await page.$eval('[data-testid=hidden-table] tbody tr td:nth-child(3)', (c) => c.textContent.trim())
  await page.evaluate(() => document.querySelector('[data-testid=hidden-table] tbody tr button[aria-label^="Explain"]').click())
  await page.waitForSelector('#copilot-q'); await clickText('button', 'Ask')
  await page.waitForSelector('[data-testid=copilot-loading]', { timeout: 10000 })
  await page.waitForSelector('[data-testid=copilot-answer]', { timeout: 170000 })
  const t = await page.$eval('[data-testid=copilot-answer]', (e) => e.innerText)
  if (!t.includes(impact)) throw new Error('engine impact ' + impact + ' not in answer')
  for (const k of ['WHY IT MATTERS', 'WHAT REMAINS UNCERTAIN', 'No empirical validation']) if (!t.toUpperCase().includes(k.toUpperCase())) throw new Error('missing ' + k)
  if (/validated against|will happen|forecast of/i.test(t.replace(/not been validated against any observed event|not validated|no empirical validation|not a forecast|nothing here is a forecast/gi, ''))) throw new Error('overclaim in answer')
  const mode = await page.$eval('[data-testid=copilot-answer] .inline-block', (e) => e.textContent); await shot('C1-copilot-finder')
  return `mode: ${mode.trim()}; impact ${impact} present`
})
await step('C2 copilot: declines an unsupported question', async () => {
  await page.$eval('#copilot-q', (e) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, 'How likely is this and how much would we save?'); e.dispatchEvent(new Event('input', { bubbles: true })) })
  await clickText('button', 'Ask'); await page.waitForSelector('[data-testid=copilot-unsupported]', { timeout: 170000 })
  const u = await page.$eval('[data-testid=copilot-unsupported]', (e) => e.innerText)
  if (!/no event probabilities/.test(u) || !/no claim about real-world savings/.test(u)) throw new Error('not declined: ' + u)
  return 'declined: probability + savings'
})
await step('C3 copilot: executive summary downloads with evidence table and caveats', async () => {
  fs.readdirSync(DL).forEach((f) => fs.unlinkSync(path.join(DL, f)))
  await clickText('button', 'Executive summary'); await page.waitForSelector('[data-testid=copilot-report]', { timeout: 170000 })
  await clickText('button', 'Download .md'); await sleep(1200)
  const f = fs.readdirSync(DL).find((x) => x.endsWith('.md')); const m = fs.readFileSync(path.join(DL, f), 'utf8')
  for (const k of ['# Executive summary', '## Evidence table', '`events[].portfolio_network_impact`', '## Standing notes', 'not forecasts']) if (!m.includes(k)) throw new Error('report lacks ' + k)
  return f
})
await step('5-7 configure a shock and run propagation', async () => {
  await clickText('a', 'Scenario builder'); await page.waitForSelector('[aria-label="Scenario name"]')
  await page.select('[aria-label="Hazard type 1"]', 'drought')
  await setVal('[aria-label="Scenario name"]', 'E2E Brazil drought')
  await setVal('[aria-label="Duration 1"]', '90')
  await shot('04-builder')
  await clickText('button', 'Circular footprint')
  await page.evaluate(() => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; const ins = [...document.querySelectorAll('input[type=number]')].filter((e) => !e.getAttribute('aria-label')); const lbl = (t) => [...document.querySelectorAll('label')].find((l) => l.textContent.startsWith(t)).parentElement.querySelector('input'); for (const [t, v] of [['Centre latitude', '-21.5'], ['Centre longitude', '-47'], ['Radius', '350']]) { const e = lbl(t); set.call(e, v); e.dispatchEvent(new Event('input', { bubbles: true })) } })
  await clickText('button', 'Run analysis'); await page.waitForFunction(() => location.pathname === '/results', { timeout: 15000 })
  await page.waitForFunction(() => document.body.textContent.includes('E2E Brazil drought'))
  await sleep(500); return 'navigated to /results'
})
await step('8 inspect propagation orders + affected downstream', async () => {
  const t = await body()
  for (const k of ['first-order', 'second-order', 'third-order', 'critical propagation paths']) if (!t.includes(k)) throw new Error('missing ' + k)
  await shot('05-results'); return 'orders present'
})
await step('9 location-only vs network-aware', async () => {
  const t = await body(); if (!t.includes('location-only (whole network)') || !t.includes('network-aware (whole network)')) throw new Error('comparison missing')
  return 'comparison panel present'
})
await step('10 Monte Carlo uncertainty', async () => {
  await clickText('button', 'Run uncertainty analysis'); await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('median total loss'), { timeout: 30000 })
  const first = await page.evaluate(() => [...document.querySelectorAll('[data-testid=kpi]')].find((k) => k.textContent.includes('5th'))?.textContent)
  await clickText('button', 'Run uncertainty analysis'); await sleep(1500)
  const second = await page.evaluate(() => [...document.querySelectorAll('[data-testid=kpi]')].find((k) => k.textContent.includes('5th'))?.textContent)
  if (first !== second) throw new Error('not reproducible: ' + first + ' vs ' + second)
  await page.evaluate(() => document.querySelector('[aria-label="Loss distribution"]')?.scrollIntoView()); await shot('06-montecarlo'); return first
})
await step('13 exports download real files', async () => {
  await clickText('button', 'CSV'); await clickText('button', 'JSON'); await clickText('button', 'Scenario report'); await sleep(1500)
  const files = fs.readdirSync(DL); if (files.length < 3) throw new Error('downloads: ' + files.join(',')); 
  const csv = files.find((f) => f.endsWith('.csv')); if (!fs.readFileSync(path.join(DL, csv), 'utf8').startsWith('scenario_id')) throw new Error('bad csv'); return files.join(', ')
})
await step('11-12 mitigation compare vs baseline', async () => {
  await clickText('a', 'Mitigation laboratory'); await page.waitForSelector('select[aria-label="Add target"]')
  await page.select('select[aria-label="Add target"]', 'softdrink_br'); 
  await clickText('button', 'Compare with baseline'); await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('baseline vs mitigated'), { timeout: 20000 })
  await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('recommended interventions') && !document.body.innerText.includes('Evaluating candidate'), { timeout: 30000 })
  await sleep(600); await shot('07-mitigation'); return 'comparison + recommendations rendered'
})
await step('entity page + methodology', async () => {
  await page.goto(URL_ + '/entity/softdrink_br', { waitUntil: 'networkidle0' }); await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('systemic vulnerability score'), { timeout: 15000 })
  await shot('08-entity'); await page.goto(URL_ + '/methodology', { waitUntil: 'networkidle0' }); await page.waitForFunction(() => document.body.innerText.toLowerCase().includes('sectivia reference audit'))
  await shot('09-methodology'); return 'ok'
})
await step('responsive: no horizontal overflow on any screen at 390px', async () => {
  await page.setViewport({ width: 390, height: 844 }); const bad = []
  for (const p of ['/', '/finder', '/network', '/scenario', '/results', '/entity/port_rtm', '/mitigation', '/methodology']) {
    await page.goto(URL_ + p, { waitUntil: 'networkidle0' }); await sleep(p.startsWith('/mitigation') || p.startsWith('/entity') || p.startsWith('/finder') ? 4500 : 1500)
    const w = await page.evaluate(() => document.documentElement.scrollWidth); if (w > 392) bad.push(`${p}=${w}`)
  }
  if (bad.length) throw new Error('overflow: ' + bad.join(', ')); return '8 screens ok'
})
await step('responsive: mobile nav', async () => {
  await page.setViewport({ width: 390, height: 800 }); await page.goto(URL_, { waitUntil: 'networkidle0' }); await page.waitForSelector('[aria-label="Open navigation"]')
  await page.click('[aria-label="Open navigation"]'); await page.waitForSelector('nav[aria-label=Primary]'); const w = await page.evaluate(() => document.documentElement.scrollWidth); await shot('10-mobile')
  if (w > 400) throw new Error('horizontal overflow ' + w); return `scrollWidth ${w}`
})
const real = errors.filter((e) => !/favicon|Download the React DevTools/.test(e))
results.push([real.length === 0, 'no console/page errors', real.slice(0, 3).join(' || ')]); console.log(real.length ? 'FAIL console errors: ' + real.slice(0, 3) : 'PASS no console/page errors')
await browser.close()
console.log(`\nScreenshots: ${SHOTS}`)
const failed = results.filter((r) => !r[0]).length
console.log(`${results.length - failed}/${results.length} steps passed`)
process.exit(failed ? 1 : 0)
