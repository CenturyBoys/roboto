import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ExecDetail } from './ExecDetail'

const DETAIL = {
  execution: {
    id: 21,
    issue_id: '231',
    agent: 'impl',
    state: 'failed',
    attempt: 1,
    repo: 'arenavalendo/main',
    created_at: '2026-11-03T12:00:00+00:00',
  },
  sessions: [],
  interactions: [],
  cost: { tokens: 1000, cost_usd: 0.045 },
  tool_usage: {
    total: 0,
    by_category: { semantic: 0, read_full: 0, search: 0, edit: 0, shell: 0, other: 0 },
    efficiency: null,
  },
  risk: { level: 'baixo', reasons: [] },
  live: false,
  secret_blocked: true,
}

let posted: string[] = []

beforeEach(() => {
  posted = []
  localStorage.setItem('rtok', 't')
  vi.stubGlobal('confirm', () => true)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') posted.push(url)
      const body = url.endsWith('/allow-secret')
        ? { id: 21, state: 'queued' }
        : DETAIL
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

test('mostra o override quando secret_blocked e chama allow-secret ao clicar', async () => {
  render(<ExecDetail id={21} onBack={() => {}} onOpenRun={() => {}} />)
  const btn = await screen.findByTestId('exec-allow-secret')
  fireEvent.click(btn)
  await waitFor(() => expect(posted.some((u) => u.endsWith('/executions/21/allow-secret'))).toBe(true))
})

test('não mostra o override quando não é secret_blocked', async () => {
  DETAIL.secret_blocked = false
  render(<ExecDetail id={21} onBack={() => {}} onOpenRun={() => {}} />)
  await screen.findByText(/voltar/) // montou
  expect(screen.queryByTestId('exec-allow-secret')).toBeNull()
  DETAIL.secret_blocked = true // restaura p/ outros testes
})
