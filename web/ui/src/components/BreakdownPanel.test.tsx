import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { BreakdownPanel } from './BreakdownPanel'

const PROPOSED = [
  { title: 'ADR', points: ['escrever'], depends_on_prev: false },
  { title: 'logger', points: ['mascarar PII'], depends_on_prev: true },
]

// mock de fetch que roteia por URL+método; `draftItems` é o que o GET do rascunho devolve.
function stub(draftItems: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      let body: unknown = { ok: true }
      if (url.endsWith('/breakdown/draft') && method === 'GET') body = { items: draftItems }
      else if (url.endsWith('/breakdown/apply'))
        body = { created: [{ number: 300, url: 'https://x/300', title: 'ADR' }] }
      else if (url.endsWith('/breakdown')) body = { question: null, items: PROPOSED }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
}

beforeEach(() => localStorage.setItem('rtok', 't'))
afterEach(() => vi.unstubAllGlobals())

test('propõe sub-issues (sem criar) e depois materializa', async () => {
  stub(null) // sem rascunho salvo
  render(<BreakdownPanel number={66} />)
  fireEvent.click(screen.getByText('Destrinchar épico'))
  expect(await screen.findByDisplayValue('ADR')).toBeInTheDocument()
  expect(screen.getByDisplayValue('logger')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Criar 2 sub-issue(s)'))
  expect(await screen.findByText('#300')).toBeInTheDocument()
})

test('restaura o rascunho salvo ao abrir (sobrevive ao F5)', async () => {
  stub([{ title: 'rascunho salvo', points: [], depends_on_prev: false }])
  render(<BreakdownPanel number={66} />)
  // sem clicar em nada: o rascunho durável volta do backend
  expect(await screen.findByDisplayValue('rascunho salvo')).toBeInTheDocument()
})
