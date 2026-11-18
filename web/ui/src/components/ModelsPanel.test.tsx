import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ModelsPanel } from './ModelsPanel'

const STAGES = [
  {
    key: 'CHEAP_MODEL',
    label: 'Breakdown / refino-conversa / chat',
    default: 'qwen/qwen-2.5-72b-instruct',
    value: '',
    effective: 'qwen/qwen-2.5-72b-instruct',
    live: true,
  },
  {
    key: 'JEV_MODEL',
    label: 'Decisor degrau-2',
    default: '',
    value: 'typesafe/jev-router',
    effective: 'typesafe/jev-router',
    live: false,
  },
]

function stub() {
  const put = vi.fn()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      let body: unknown = {}
      if (url.endsWith('/models') && method === 'GET') body = { stages: STAGES }
      else if (url.endsWith('/models') && method === 'PUT') {
        put(JSON.parse(String(init?.body)))
        body = {
          stages: STAGES.map((s) =>
            s.key === 'CHEAP_MODEL'
              ? { ...s, value: 'qwen/qwen3.8-flash', effective: 'qwen/qwen3.8-flash' }
              : s,
          ),
        }
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
  return put
}

beforeEach(() => localStorage.setItem('rtok', 't'))
afterEach(() => vi.unstubAllGlobals())

test('lista as etapas e aplica a troca ao vivo', async () => {
  const put = stub()
  render(<ModelsPanel />)
  // etapa carregada
  const input = (await screen.findByPlaceholderText(/qwen-2.5-72b-instruct/)) as HTMLInputElement
  // edita o modelo do tier cheap
  fireEvent.change(input, { target: { value: 'qwen/qwen3.8-flash' } })
  fireEvent.click(screen.getByText('Aplicar ao vivo'))
  // PUT enviou só a chave alterada
  await waitFor(() => expect(put).toHaveBeenCalledWith({ updates: { CHEAP_MODEL: 'qwen/qwen3.8-flash' } }))
  // reflete o efetivo novo
  expect(await screen.findByText('qwen/qwen3.8-flash')).toBeInTheDocument()
})
