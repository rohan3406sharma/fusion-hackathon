// Browser check of the copilot with the language model deliberately UNREACHABLE (backend started with FIN04_OLLAMA_URL pointing at a dead port).
// Usage: APP_URL=http://localhost:5174 node e2e_copilot_fallback.mjs     (see docs/COPILOT.md for the two-line setup)
import puppeteer from 'puppeteer-core'
const URL_ = process.env.APP_URL ?? 'http://localhost:5174'
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], defaultViewport: { width: 1440, height: 1000 } })
const p = await b.newPage(); const errors = []
p.on('pageerror', (e) => errors.push(e.message))
let ok = true
const check = (name, cond, note = '') => { console.log(cond ? 'PASS' : 'FAIL', name, note); ok = ok && cond }
await p.goto(URL_ + '/finder', { waitUntil: 'networkidle0' }); await p.waitForSelector('[data-testid=hidden-table]', { timeout: 30000 })
await p.waitForSelector('[data-testid=copilot-status]')
check('status says the language model is unavailable', /not available · deterministic templates in use/.test(await p.$eval('[data-testid=copilot-status]', (e) => e.textContent)))
await p.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.textContent === 'Ask').click())
await p.waitForSelector('[data-testid=copilot-answer]', { timeout: 60000 })
const t = await p.$eval('[data-testid=copilot-answer]', (e) => e.innerText)
check('answer shown as deterministic template', /Deterministic template/i.test(t))
check('reason for the fallback is shown', /provider unavailable \(unreachable\)/.test(t), t.match(/Why templates:[^\n]*/)?.[0] ?? '')
check('engine value present', /1\.13%/.test(t))
check('validation statement present', /no empirical validation/i.test(t))
await p.evaluate(() => [...document.querySelectorAll('button')].find((x) => x.textContent === 'Executive summary').click())
await p.waitForSelector('[data-testid=copilot-report]', { timeout: 60000 })
check('report generated without a model', /Deterministic template/i.test(await p.$eval('[data-testid=copilot-report]', (e) => e.innerText)))
check('no page errors', errors.length === 0, errors.join('|'))
await b.close(); process.exit(ok ? 0 : 1)
