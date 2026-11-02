// Documentação VIVA: gera os screenshots das telas do cockpit em docs/assets/screens/.
// Processo repetível (CONFORMIDADE: a doc reflete a UI real). Requer o cockpit RODANDO.
// Highlight por `data-testid` — os elementos têm id estável, então a doc aponta exatamente a peça.
//
// Uso:
//   cd web/ui && npm ci && npx playwright install chromium
//   COCKPIT_URL=http://localhost:8090 CONSOLE_TOKEN=<token> node scripts/screenshots.mjs

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const URL = process.env.COCKPIT_URL || 'http://localhost:8090'
const TOKEN = process.env.CONSOLE_TOKEN || 'troque-isto'
// scripts -> ui -> web -> raiz do repo -> docs/
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../docs/assets/screens')
mkdirSync(OUT, { recursive: true })

// name = arquivo; nav = data-testid do botão de aba; highlight = data-testid a destacar (opcional)
const SCREENS = [
  { name: 'execucoes', nav: 'nav-execs', highlight: 'exec-summary' },
  { name: 'issues', nav: 'nav-issues' },
  { name: 'custos', nav: 'nav-costs' },
  { name: 'revisar-pr', nav: 'nav-reviewpr' },
  { name: 'interacoes', nav: 'nav-interactions' },
]

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } })
await page.goto(URL, { waitUntil: 'domcontentloaded' })
await page.evaluate((t) => localStorage.setItem('rtok', t), TOKEN)
await page.goto(URL, { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)

async function setOutline(id, on) {
  await page.evaluate(
    ({ id, on }) => {
      const el = document.querySelector(`[data-testid="${id}"]`)
      if (!el) return
      el.style.outline = on ? '3px solid #ffd21e' : ''
      el.style.outlineOffset = on ? '4px' : ''
      el.style.borderRadius = on ? '12px' : ''
    },
    { id, on },
  )
}

for (const s of SCREENS) {
  try {
    await page.getByTestId(s.nav).click()
    await page.waitForTimeout(1200)
  } catch {
    console.warn('aba não encontrada:', s.nav)
  }
  if (s.highlight) await setOutline(s.highlight, true)
  await page.waitForTimeout(150)
  await page.screenshot({ path: `${OUT}/${s.name}.png` })
  console.log('shot:', s.name)
  if (s.highlight) await setOutline(s.highlight, false)
}

await browser.close()
console.log('ok ->', OUT)
