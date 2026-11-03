import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { BreakdownPanel } from './BreakdownPanel'

beforeEach(() => {
  localStorage.setItem('rtok', 't')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.endsWith('/breakdown/apply')
        ? { created: [{ number: 300, url: 'https://x/300', title: 'ADR' }] }
        : {
            question: null,
            items: [
              { title: 'ADR', points: ['escrever'], depends_on_prev: false },
              { title: 'logger', points: ['mascarar PII'], depends_on_prev: true },
            ],
          }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

test('propõe sub-issues (sem criar) e depois materializa', async () => {
  render(<BreakdownPanel number={66} />)
  fireEvent.click(screen.getByText('Destrinchar épico'))
  // o item proposto aparece (editável) — nada foi criado ainda
  expect(await screen.findByDisplayValue('ADR')).toBeInTheDocument()
  expect(screen.getByDisplayValue('logger')).toBeInTheDocument()
  // botão de criar reflete a contagem
  fireEvent.click(screen.getByText('Criar 2 sub-issue(s)'))
  // após criar, mostra o link da sub-issue criada
  expect(await screen.findByText('#300')).toBeInTheDocument()
})
