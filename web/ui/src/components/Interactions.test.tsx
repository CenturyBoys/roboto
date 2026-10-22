import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Interactions } from './Interactions'

beforeEach(() => {
  localStorage.setItem('rtok', 't')
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            interactions: [
              {
                id: 5,
                execution_id: 2,
                kind: 'decision',
                prompt: 'Redis ou DB?',
                options: ['Redis', 'DB'],
                status: 'pending',
                answer: null,
                answered_by: null,
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

test('mostra a pendência e os botões de opção', async () => {
  render(<Interactions />)
  expect(await screen.findByText('Redis ou DB?')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Redis' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'DB' })).toBeInTheDocument()
})
