import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ExecList } from './ExecList'

beforeEach(() => {
  localStorage.setItem('rtok', 't')
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            executions: [
              {
                id: 1,
                tenant: 'acme',
                repo: 'acme/app',
                issue_id: '7',
                agent: 'impl',
                state: 'running',
                attempt: 0,
                created_at: '',
                updated_at: '',
              },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

test('renderiza a execução (card no mobile + linha na tabela) com o estado', async () => {
  render(<ExecList auto={false} onSelect={() => {}} />)
  // o mesmo dado aparece nos dois layouts (um escondido por CSS) → >= 1 ocorrência.
  expect((await screen.findAllByText('impl')).length).toBeGreaterThan(0)
  expect(screen.getAllByText('running').length).toBeGreaterThan(0)
})
