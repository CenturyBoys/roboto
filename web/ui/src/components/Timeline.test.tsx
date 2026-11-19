import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Timeline, parseAction } from './Timeline'
import type { Interaction } from '@/types'

let calls: string[] = []

beforeEach(() => {
  localStorage.setItem('rtok', 't')
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      calls.push(String(url))
      if (String(url).includes('/answer')) {
        return new Response(JSON.stringify({ id: 7, accepted: true, status: 'answered' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
      return new Response(null, { status: 200 }) // SSE /events sem corpo no teste
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

const approval: Interaction = {
  id: 7,
  execution_id: 2,
  kind: 'approval',
  prompt: 'Bash\n{"command":"git push origin main"}',
  options: ['allow', 'deny'],
  status: 'pending',
  answer: null,
  answered_by: null,
}

test('parseAction separa a tool dos args (json formatado)', () => {
  const { tool, args } = parseAction('Bash\n{"command":"git push"}')
  expect(tool).toBe('Bash')
  expect(args).toContain('git push')
})

test('mostra o cartão de aprovação inline com tool, args e botões', async () => {
  render(<Timeline id={2} interactions={[approval]} live onChange={() => {}} />)
  expect(await screen.findByText('Bash')).toBeInTheDocument()
  expect(screen.getByText(/git push origin main/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '✓ aprovar' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '✕ recusar' })).toBeInTheDocument()
})

test('aprovar resolve a interação (POST /interactions/:id/answer)', async () => {
  render(<Timeline id={2} interactions={[approval]} live onChange={() => {}} />)
  fireEvent.click(await screen.findByRole('button', { name: '✓ aprovar' }))
  await vi.waitFor(() => expect(calls.some((u) => u.includes('/interactions/7/answer'))).toBe(true))
})

test('tem caixa de steer e botão de interromper quando ao vivo', () => {
  render(<Timeline id={2} interactions={[]} live onChange={() => {}} />)
  expect(screen.getByTestId('timeline-steer')).toBeInTheDocument()
  expect(screen.getByTestId('timeline-interrupt')).toBeInTheDocument()
})

test('sessão parada: sem botão de interromper', () => {
  render(<Timeline id={2} interactions={[]} live={false} onChange={() => {}} />)
  expect(screen.queryByTestId('timeline-interrupt')).not.toBeInTheDocument()
})
