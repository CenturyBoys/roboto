import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Setup } from './Setup'

beforeEach(() => {
  localStorage.setItem('rtok', 't')
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ configured: false, missing: ['ROBOTO_TENANT'], present: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

test('renderiza a tela de configuração com o botão de salvar', async () => {
  render(<Setup token="t" onReady={() => {}} />)
  expect(await screen.findByText('Configuração do fleet')).toBeInTheDocument()
  expect(screen.getByText('Salvar e iniciar')).toBeInTheDocument()
})
