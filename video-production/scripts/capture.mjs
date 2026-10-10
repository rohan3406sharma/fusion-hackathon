// Captures the REAL running app for the explainer: screen recordings of genuine interactions and
// high-resolution stills, plus the on-screen rectangle and text of every element the video annotates.
//
// Prerequisites (isolated from your normal dev servers and database; see README):
//   backend : cd backend && FIN04_DATABASE_URL=sqlite:////tmp/fin04-capture.db \
//             FIN04_CORS_ORIGINS=http://localhost:5174 ../.venv/bin/uvicorn app.main:app --port 8001
//   frontend: cd frontend && VITE_BACKEND_URL=http://127.0.0.1:8001 npx vite --port 5174 --strictPort
//   optional: `ollama serve` with qwen3:8b for the copilot shot (templates answer otherwise)
// Run: node scripts/capture.mjs        (APP_URL, CHROME_PATH, DPR, SKIP_COPILOT=1 to override)
//
// Outputs: captures/stills/*.png (1920x1080 CSS px at DPR 2 = 3840x2160), captures/rec/*.mp4
// (2880x1620, 30 fps CFR, real-time), captures/manifest.json (rects, texts, click times).
// A cursor overlay and hidden scrollbars are injected for legibility; nothing else on the page changes.
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const APP = process.env.APP_URL ?? 'http://localhost:5174'
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const DPR = Number(process.env.DPR ?? 2)
const VW = 1920, VH = 1080
const REC_W = 2880, REC_H = 1620
const OUT = path.join(ROOT, 'captures')
fs.mkdirSync(path.join(OUT, 'stills'), { recursive: true })
fs.mkdirSync(path.join(OUT, 'rec'), { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const manifest = { app: APP, viewport: { width: VW, height: VH, dpr: DPR }, captured_at: new Date().toISOString(), stills: {}, recordings: {} }
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

const OVERLAY = `(() => {
  if (window.__fin04overlay) return; window.__fin04overlay = true;
  const install = () => {
    const st = document.createElement('style');
    st.textContent = '::-webkit-scrollbar{width:0!important;height:0!important;display:none!important}html{scrollbar-width:none!important}' +
      '#__cur{position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:30px;height:30px;transform:translate(-200px,-200px)}' +
      '#__cur svg{display:block;transform-origin:4px 3px;transition:transform .08s ease-out;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}' +
      '#__cur.down svg{transform:scale(.84)}html.__nocur #__cur,html.__nocur .__rip{display:none!important}' +
      '.__rip{position:fixed;z-index:2147483646;pointer-events:none;width:52px;height:52px;margin:-26px 0 0 -26px;border-radius:50%;border:3px solid rgba(154,123,23,.95);animation:__rip .6s ease-out forwards}' +
      '@keyframes __rip{from{transform:scale(.15);opacity:1}to{transform:scale(1.2);opacity:0}}';
    document.documentElement.appendChild(st);
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 30 30"><path d="M4 3 L4 24 L9.6 18.8 L13.4 27 L17.3 25.2 L13.6 17.2 L21.4 16.9 Z" fill="#fff" stroke="#151515" stroke-width="1.7" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    addEventListener('mousemove', (e) => { c.style.transform = 'translate(' + (e.clientX - 4) + 'px,' + (e.clientY - 3) + 'px)' }, true);
    addEventListener('mousedown', (e) => { c.classList.add('down'); const r = document.createElement('div'); r.className = '__rip';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.documentElement.appendChild(r); setTimeout(() => r.remove(), 800) }, true);
    addEventListener('mouseup', () => c.classList.remove('down'), true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
})()`

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb', '--font-render-hinting=none'] })
const page = await browser.newPage()
await page.setViewport({ width: VW, height: VH, deviceScaleFactor: DPR })
await page.evaluateOnNewDocument(OVERLAY)
const pageErrors = []
page.on('pageerror', (e) => pageErrors.push(e.message))
page.on('console', (m) => m.type() === 'error' && pageErrors.push(m.text()))

// ---------- helpers ----------
let mouse = { x: VW * 0.62, y: VH * 0.62 }
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
async function moveTo(x, y, ms = 750) {
  const steps = Math.max(10, Math.round(ms / 16)), x0 = mouse.x, y0 = mouse.y
  const bow = Math.min(36, Math.hypot(x - x0, y - y0) * 0.07)
  for (let i = 1; i <= steps; i++) {
    const t = i / steps, e = ease(t)
    await page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e - Math.sin(Math.PI * t) * bow)
    await sleep(ms / steps)
  }
  mouse = { x, y }
}
async function center(handleOrSel) {
  const h = typeof handleOrSel === 'string' ? await page.waitForSelector(handleOrSel, { visible: true, timeout: 30000 }) : handleOrSel
  const b = await h.boundingBox()
  return { x: b.x + b.width / 2, y: b.y + b.height / 2, h }
}
let rec = null
const mark = (label) => { if (rec) rec.events.push({ wall: Date.now() / 1000, label }) }
async function click(handleOrSel, { ms = 750, hold = 110, label = 'click' } = {}) {
  const c = await center(handleOrSel)
  await moveTo(c.x, c.y, ms)
  await sleep(160)
  mark(label)
  await page.mouse.down(); await sleep(hold); await page.mouse.up()
}
async function scrollToY(y, ms = 1000) {
  await page.evaluate((y, ms) => new Promise((res) => {
    const y0 = window.scrollY, dy = Math.max(0, Math.min(y, document.documentElement.scrollHeight - innerHeight)) - y0, t0 = performance.now()
    const e = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
    const f = (now) => { const t = Math.min(1, (now - t0) / ms); window.scrollTo(0, y0 + dy * e(t)); t < 1 ? requestAnimationFrame(f) : res() }
    requestAnimationFrame(f)
  }), y, ms)
}
const docY = (sel, offset = 90) => page.$eval(sel, (el, o) => el.getBoundingClientRect().top + window.scrollY - o, offset)
async function spaNav(url) { await page.evaluate((u) => { history.pushState({}, '', u); dispatchEvent(new PopStateEvent('popstate')) }, url) }

// rectangles + text of named elements, in CSS px relative to the viewport (or document for full-page shots)
async function rects(specs, docRelative = false) {
  return page.evaluate((specs, docRelative) => {
    const pick = (spec) => {
      if (typeof spec === 'string') return document.querySelector(spec)
      let all = [...document.querySelectorAll(spec.sel)]
      if (spec.within) { const w = document.querySelector(spec.within); all = all.filter((e) => w && w.contains(e)) }
      let el = spec.text != null ? all.find((e) => e.textContent.replace(/\s+/g, ' ').includes(spec.text)) : all[spec.nth ?? 0]
      if (el && spec.closest) el = el.closest(spec.closest)
      return el
    }
    const out = {}
    for (const [name, spec] of Object.entries(specs)) {
      const el = pick(spec)
      if (!el) { out[name] = null; continue }
      const r = el.getBoundingClientRect(), oy = docRelative ? window.scrollY : 0
      out[name] = { x: +r.x.toFixed(1), y: +(r.y + oy).toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1), text: el.textContent.replace(/\s+/g, ' ').trim().slice(0, 200) }
    }
    return out
  }, specs, docRelative)
}
async function still(name, specs = {}, { full = false, extra = null } = {}) {
  await page.evaluate(() => document.documentElement.classList.add('__nocur'))
  await sleep(250)
  const file = path.join(OUT, 'stills', `${name}.png`)
  await page.screenshot({ path: file, fullPage: full })
  const r = await rects(specs, full)
  const meta = await page.evaluate(() => ({ url: location.pathname + location.search, scrollY: window.scrollY, docHeight: document.documentElement.scrollHeight }))
  manifest.stills[name] = { file: path.relative(ROOT, file), full, ...meta, rects: r, ...(extra ? { extra: await extra() } : {}) }
  await page.evaluate(() => document.documentElement.classList.remove('__nocur'))
  const missing = Object.entries(r).filter(([, v]) => !v).map(([k]) => k)
  log('still', name, missing.length ? `MISSING ${missing.join(',')}` : 'ok')
}

async function startRec(name) {
  const client = await page.createCDPSession()
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `fin04-rec-${name}-`))
  const frames = []
  client.on('Page.screencastFrame', async (ev) => {
    const file = path.join(dir, `f${String(frames.length).padStart(5, '0')}.jpg`)
    fs.writeFileSync(file, Buffer.from(ev.data, 'base64'))
    frames.push({ file, t: ev.metadata.timestamp })
    client.send('Page.screencastFrameAck', { sessionId: ev.sessionId }).catch(() => {})
  })
  await client.send('Page.startScreencast', { format: 'jpeg', quality: 93, everyNthFrame: 1, maxWidth: VW * DPR, maxHeight: VH * DPR })
  rec = { name, client, dir, frames, events: [], t0: Date.now() / 1000 }
  await sleep(300)
  return rec
}
async function stopRec() {
  const r = rec; rec = null
  await sleep(150)
  await r.client.send('Page.stopScreencast')
  await sleep(200)
  const end = Date.now() / 1000 // CDP frame timestamps are wall-clock epoch seconds, same clock
  const f = r.frames
  if (!f.length) throw new Error(`no frames for ${r.name}`)
  // Resample to exact constant 30 fps: output frame k shows the latest capture at or before k/30 s.
  const dur = end - f[0].t
  const seq = path.join(r.dir, 'cfr'); fs.mkdirSync(seq)
  for (let k = 0, j = 0; k < Math.round(dur * 30); k++) {
    while (j + 1 < f.length && f[j + 1].t - f[0].t <= k / 30) j++
    fs.symlinkSync(f[j].file, path.join(seq, `o${String(k).padStart(5, '0')}.jpg`))
  }
  const out = path.join(OUT, 'rec', `${r.name}.mp4`)
  const res = spawnSync('ffmpeg', ['-v', 'error', '-y', '-framerate', '30', '-i', path.join(seq, 'o%05d.jpg'),
    '-vf', `scale=${REC_W}:${REC_H}:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-preset', 'slow', '-crf', '14',
    '-r', '30', '-movflags', '+faststart', '-an', out], { encoding: 'utf8' })
  if (res.status !== 0) throw new Error(res.stderr)
  const fpsIn = f.length / Math.max(0.001, f[f.length - 1].t - f[0].t)
  const events = r.events.map((e) => ({ t: +(e.wall - f[0].t).toFixed(3), label: e.label })) // seconds into the video
  manifest.recordings[r.name] = { file: path.relative(ROOT, out), duration: +dur.toFixed(3), frames_captured: f.length, capture_fps: +fpsIn.toFixed(1), events }
  fs.rmSync(r.dir, { recursive: true, force: true })
  log('rec', r.name, `${dur.toFixed(1)}s`, `${f.length} frames (${fpsIn.toFixed(1)} fps)`, events.map((e) => `${e.label}@${e.t}`).join(' '))
}

const GRAPH_NODES = ['grid_nl', 'dairy_pack_nl', 'retail_eu', 'cold_nl', 'dairy_proc_fr', 'oilblend_nl', 'readymeal_uk', 'bakery_uk', 'retail_uk', 'choc_be', 'port_rtm']
const graphNodes = () => page.evaluate((ids) => {
  const box = document.querySelector('[data-testid="graph-canvas"]')
  const cy = box && box._cyreg && box._cyreg.cy
  if (!cy) return null
  const b = box.getBoundingClientRect(), out = {}
  for (const id of ids) {
    const n = cy.getElementById(id)
    if (!n || n.empty()) continue
    const p = n.renderedPosition(), bb = n.renderedBoundingBox({ includeLabels: false })
    out[id] = { x: +(b.x + p.x).toFixed(1), y: +(b.y + p.y).toFixed(1), w: +bb.w.toFixed(1), h: +bb.h.toFixed(1), label: n.data('label') ?? n.data('name') ?? id, classes: n.classes().join(' ') }
  }
  return { zoom: cy.zoom(), nodes: out }
}, GRAPH_NODES)
const ROW = (n, td) => ({ sel: `[data-testid="hidden-table"] tbody tr:nth-child(${n}) td:nth-child(${td})` })

// ---------- 1. overview ----------
log('open', APP)
await page.goto(APP, { waitUntil: 'networkidle0' })
await page.waitForSelector('[data-testid="finder-card"]', { timeout: 90000 })
await sleep(1500)
await page.mouse.move(mouse.x, mouse.y)
await still('overview', {
  title: 'main h1', finderCard: '[data-testid="finder-card"]', kpis: '.grid', synthBadge: { sel: 'aside span', text: 'Synthetic demo data' },
  navFinder: { sel: 'nav[aria-label="Primary"] a', text: 'Hidden exposure finder' },
})

// ---------- 2. REC: open the finder and search ----------
await startRec('rec-01-finder')
await sleep(700)
await click(await page.waitForSelector('nav[aria-label="Primary"] a[href="/finder"]', { visible: true }), { label: 'nav-finder', ms: 900 })
await page.waitForSelector('[data-testid="hidden-table"]', { timeout: 90000 })
mark('results-visible')
await sleep(1100)
await click(await page.waitForSelector('button.btn-primary::-p-text(Search)', { visible: true }), { label: 'search', ms: 850 })
await page.waitForFunction(() => ![...document.querySelectorAll('button')].some((b) => b.textContent.includes('Searching')), { timeout: 60000 })
mark('search-done')
await sleep(900)
await moveTo(1180, 760, 900)
await sleep(900)
await stopRec()

// ---------- 3. finder stills ----------
await scrollToY(0, 10); await sleep(400)
await still('finder-top', {
  kpiEvents: { sel: '[data-testid="kpi"]', nth: 0 }, kpiHidden: { sel: '[data-testid="kpi"]', nth: 1 },
  kpiTau: { sel: '[data-testid="kpi"]', nth: 2 }, kpiRuntime: { sel: '[data-testid="kpi"]', nth: 3 },
  searchBtn: { sel: 'button.btn-primary', text: 'Search' }, title: 'main h1', settings: { sel: 'section', text: 'Search settings' },
})
await scrollToY(await docY('[data-testid="hidden-table"]', 230), 10); await sleep(500)
await still('finder-table', {
  table: '[data-testid="hidden-table"]', header: '[data-testid="hidden-table"] thead',
  r1: { sel: '[data-testid="hidden-table"] tbody tr', nth: 0 }, r1event: ROW(1, 2), r1impact: ROW(1, 3), r1loc: ROW(1, 4), r1hidden: ROW(1, 5),
  r1reach: ROW(1, 6), r1p5: ROW(1, 7), r1promote: { sel: '[data-testid="hidden-table"] tbody tr:nth-child(1) button', text: 'Open as scenario' },
  r2: { sel: '[data-testid="hidden-table"] tbody tr', nth: 1 }, r3: { sel: '[data-testid="hidden-table"] tbody tr', nth: 2 },
  r4: { sel: '[data-testid="hidden-table"] tbody tr', nth: 3 }, r5: { sel: '[data-testid="hidden-table"] tbody tr', nth: 4 },
  r4p5: ROW(4, 7), r5p5: ROW(5, 7), tabs: { sel: 'button', text: 'Hidden-only' },
})
await scrollToY(await docY('[data-testid="exposure-matrix"]', 170), 10); await sleep(500)
await still('finder-matrix', {
  matrix: '[data-testid="exposure-matrix"]', m1: { sel: '[data-testid="exposure-matrix"] tbody tr', nth: 0 },
  m2: { sel: '[data-testid="exposure-matrix"] tbody tr', nth: 1 }, m3: { sel: '[data-testid="exposure-matrix"] tbody tr', nth: 2 },
  spofPanel: { sel: 'section h2', text: 'Single points of failure', closest: 'section' },
  spof1: { sel: 'section li', text: 'Rotterdam Terminal Operator' }, matrixPanel: { sel: 'section h2', text: 'Who can hurt whom', closest: 'section' },
})
await scrollToY(0, 10); await sleep(300)
await still('finder-full', { table: '[data-testid="hidden-table"]', matrix: '[data-testid="exposure-matrix"]' }, { full: true })

// ---------- 4. optimiser (on the finder page) ----------
const optY = await docY('#budget', 330)
await scrollToY(optY, 10); await sleep(500)
await page.mouse.move(mouse.x, mouse.y)
await startRec('rec-02-optimise')
await sleep(600)
await click('#budget', { label: 'budget', ms: 800 })
await page.$eval('#budget', (el) => el.value) .then((v) => log('budget field =', v))
await sleep(350)
await click(await page.waitForSelector('button.btn-primary::-p-text(Optimise)', { visible: true }), { label: 'optimise', ms: 700 })
await page.waitForSelector('[data-testid="optimiser-result"]', { timeout: 120000 })
mark('optimiser-result')
await sleep(1400)
await moveTo(mouse.x - 260, mouse.y + 200, 900)
await sleep(800)
await stopRec()
await still('optimiser', {
  result: '[data-testid="optimiser-result"]',
  kBefore: { sel: '[data-testid="optimiser-result"] [data-testid="kpi"]', nth: 0 }, kAfter: { sel: '[data-testid="optimiser-result"] [data-testid="kpi"]', nth: 1 },
  kCost: { sel: '[data-testid="optimiser-result"] [data-testid="kpi"]', nth: 2 }, kGap: { sel: '[data-testid="optimiser-result"] [data-testid="kpi"]', nth: 3 },
  plan: { sel: '[data-testid="optimiser-result"] table' }, panel: { sel: 'section h2', text: 'Protect against these events', closest: 'section' },
  robustness: { sel: '[data-testid="optimiser-result"] p', text: 'Reduction positive' },
})

// ---------- 5. copilot (optional, real local model) ----------
if (!process.env.SKIP_COPILOT) {
  await scrollToY(await docY('#copilot', 110), 10); await sleep(400)
  await click(await page.waitForSelector('#copilot button.btn-primary::-p-text(Ask)', { visible: true }), { label: 'ask', ms: 500 })
  log('copilot: waiting for the local model (first request can take ~90 s)')
  await page.waitForSelector('[data-testid="copilot-answer"]', { timeout: 300000 })
  await sleep(800)
  await scrollToY(await docY('#copilot', 110), 10); await sleep(400)
  await still('copilot', {
    panel: { sel: '#copilot section' }, answer: '[data-testid="copilot-answer"]',
    mode: { sel: '[data-testid="copilot-answer"] span', nth: 0 }, s1: { sel: '[data-testid="copilot-sentence"]', nth: 0 },
    s2: { sel: '[data-testid="copilot-sentence"]', nth: 1 }, s3: { sel: '[data-testid="copilot-sentence"]', nth: 2 },
  })
  await still('copilot-full', { answer: '[data-testid="copilot-answer"]' }, { full: true })
}

// ---------- 6. REC: open the top hidden-only event as a scenario ----------
await scrollToY(await docY('[data-testid="hidden-table"]', 230), 10); await sleep(500)
await page.mouse.move(mouse.x, mouse.y)
await startRec('rec-03-promote')
await sleep(600)
await click(await page.waitForSelector('[data-testid="hidden-table"] tbody tr:nth-child(1) button::-p-text(Open as scenario)', { visible: true }), { label: 'promote', ms: 900 })
await page.waitForFunction(() => location.pathname === '/results' && document.querySelector('main h1')?.textContent.includes('Finder: Drought at Dutch Regional Grid Operator') && document.querySelector('#paths li'), { timeout: 90000 })
mark('results-visible')
await sleep(1500)
await scrollToY(await docY('#paths', 120), 1300)
mark('paths-visible')
await sleep(1600)
await stopRec()

// ---------- 7. results stills ----------
await scrollToY(0, 10); await sleep(400)
await still('results-top', {
  title: 'main h1', kDirect: { sel: '[data-testid="kpi"]', nth: 0 }, kIndirect: { sel: '[data-testid="kpi"]', nth: 1 },
  kTotal: { sel: '[data-testid="kpi"]', nth: 2 }, kWindow: { sel: '[data-testid="kpi"]', nth: 3 }, activeScenario: '[aria-label="Active scenario"]',
})
await scrollToY(await docY('#orders', 110), 10); await sleep(400)
await still('results-orders', { orders: '#orders' })
await scrollToY(await docY('#paths', 120), 10); await sleep(400)
await still('results-paths', {
  panel: '#paths', p1: { sel: '#paths li', nth: 0 }, p1view: { sel: '#paths li:nth-child(1) a', text: 'View in graph' },
  p1grid: { sel: '#paths li:nth-child(1) a', text: 'Dutch Regional Grid Operator' }, p1dairy: { sel: '#paths li:nth-child(1) a', text: 'Utrecht Cheese and Yogurt Maker' },
  p1retail: { sel: '#paths li:nth-child(1) a', text: 'Rhineland Grocery Group' }, p1meta: { sel: '#paths li:nth-child(1) p', nth: 1, within: '#paths li:nth-child(1)' },
  p2: { sel: '#paths li', nth: 1 }, p3: { sel: '#paths li', nth: 2 },
})
await scrollToY(await docY('#compare', 110), 10); await sleep(400)
await still('results-compare', {
  panel: '#compare', kLoc: { sel: '#compare [data-testid="kpi"]', nth: 0 }, kNet: { sel: '#compare [data-testid="kpi"]', nth: 1 },
  kPort: { sel: '#compare [data-testid="kpi"]', nth: 2 }, curve: '[data-testid="hidden-curve"]', table: '#compare table',
  rowUtrecht: { sel: '#compare tbody tr', text: 'Utrecht Cheese and Yogurt Maker' }, rowRhine: { sel: '#compare tbody tr', text: 'Rhineland Grocery Group' },
  rowManch: { sel: '#compare tbody tr', text: 'Manchester Ready-Meal Maker' }, colDirect: { sel: '#compare thead th', nth: 2 }, colNet: { sel: '#compare thead th', nth: 3 },
  colChange: { sel: '#compare thead th', nth: 6 },
})
await scrollToY(0, 10); await sleep(300)
await still('results-full', { paths: '#paths', compare: '#compare', orders: '#orders' }, { full: true })

// ---------- 8. REC: view the path in the graph ----------
await scrollToY(await docY('#paths', 120), 10); await sleep(400)
await page.mouse.move(mouse.x, mouse.y)
await startRec('rec-04-graph')
await sleep(500)
await click(await page.waitForSelector('#paths li:nth-child(1) a::-p-text(View in graph)', { visible: true }), { label: 'view-in-graph', ms: 800 })
await page.waitForSelector('[data-testid="graph-canvas"] canvas', { timeout: 60000 })
mark('graph-visible')
await sleep(3200)
await moveTo(1500, 980, 900)
await sleep(700)
await stopRec()
await still('graph-path', {
  canvas: '[data-testid="graph-canvas"]', title: 'main h1', pathText: { sel: 'main p', text: 'Cumulative transmission' },
  pathLabel: { sel: 'main label, main p, main span', text: 'Highlight propagation path' }, legend: '[aria-label="Legend"]',
}, { extra: graphNodes })

// ---------- 9. network overview (active scenario = the promoted grid drought) ----------
await spaNav('/network'); await page.waitForSelector('[data-testid="graph-canvas"] canvas', { timeout: 60000 }); await sleep(3000)
await scrollToY(await docY('[data-testid="graph-canvas"]', 40), 10); await sleep(1200)
await still('network', { canvas: '[data-testid="graph-canvas"]', legend: '[aria-label="Legend"]' }, { extra: graphNodes })
await scrollToY(0, 10); await sleep(500)
await still('network-top', { title: 'main h1', canvas: '[data-testid="graph-canvas"]' })

// ---------- 10. methodology + entity (honesty and real data) ----------
await spaNav('/methodology'); await page.waitForSelector('main h1', { timeout: 30000 }); await sleep(1800)
await still('methodology', {
  title: 'main h1', readFirst: { sel: '[role="note"]', nth: 0 }, kEntities: { sel: '[data-testid="kpi"]', nth: 0 }, kRelations: { sel: '[data-testid="kpi"]', nth: 1 },
  jrcRow: { sel: 'tr', text: 'jrc_flood_rp100' }, inventory: { sel: 'section h2', text: 'Dataset inventory', closest: 'section' },
})
await spaNav('/entity/grid_nl'); await page.waitForSelector('main h1', { timeout: 30000 }); await sleep(1800)
await still('entity-grid', {
  title: 'main h1', profile: { sel: 'section h2', text: 'Profile', closest: 'section' }, jrc: { sel: 'p', text: 'Real hazard context', closest: 'div' },
  customers: { sel: 'section h2', text: 'Customers', closest: 'section' },
})
await spaNav('/'); await page.waitForSelector('[data-testid="finder-card"]', { timeout: 90000 }); await sleep(1800)
await still('overview-promoted', { finderCard: '[data-testid="finder-card"]', title: 'main h1', kpis: '.grid' })

manifest.page_errors = pageErrors
fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 1))
log('done; page errors:', pageErrors.length ? pageErrors : 'none')
await browser.close()
