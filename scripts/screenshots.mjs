// Captures full-page screenshots of all seven screens (desktop + mobile) for visual review.
// Usage: SHOT_DIR=/tmp/shots node screenshots.mjs   (servers running; scenario via SCENARIO env, default Rotterdam)
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
const URL_ = process.env.APP_URL ?? 'http://localhost:5173'
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.SHOT_DIR ?? '/tmp/fin04-shots'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const errors = []
for (const [tag, vp] of [['d', { width: 1440, height: 1000 }], ['m', { width: 390, height: 844 }]]) {
  const page = await browser.newPage(); await page.setViewport(vp)
  page.on('console', (m) => m.type() === 'error' && errors.push(`${tag}: ${m.text()}`)); page.on('pageerror', (e) => errors.push(`${tag}: ${e.message}`))
  await page.goto(URL_, { waitUntil: 'networkidle0' })
  await page.waitForSelector('[aria-label="Active scenario"]')
  await page.select('[aria-label="Active scenario"]', process.env.SCENARIO ?? 'sc_rotterdam_port_flood'); await new Promise((r) => setTimeout(r, 1200))
  for (const [name, p, wait] of [['1-overview', '/'], ['2-graph', '/network'], ['3-builder', '/scenario'], ['4-results', '/results'], ['5-entity', '/entity/port_rtm'], ['6-mitigation', '/mitigation'], ['7-method', '/methodology']]) {
    await page.evaluate((u) => { history.pushState({}, '', u); dispatchEvent(new PopStateEvent('popstate')) }, p)
    await new Promise((r) => setTimeout(r, 2500))
    await page.screenshot({ path: path.join(OUT, `${tag}-${name}.png`), fullPage: true })
  }
  await page.close()
}
await browser.close(); console.log('errors:', errors.length ? errors : 'none'); console.log('saved to', OUT)
