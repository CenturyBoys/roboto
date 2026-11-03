import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import App from './App'

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('rtok', 't')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.includes('/healthz')
        ? { ok: true, mode: 'running' }
        : { executions: [] } // ExecList carrega vazio
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

test('auto-refresh começa LIGADO por padrão (preferência persistida)', async () => {
  render(<App />)
  const btn = await screen.findByTestId('auto-refresh')
  expect(btn).toHaveTextContent('Auto-refresh on')
})

test('desligar persiste e sobrevive a remontar (nova aba)', async () => {
  const { unmount } = render(<App />)
  fireEvent.click(await screen.findByTestId('auto-refresh')) // liga -> desliga
  expect(localStorage.getItem('rt_auto')).toBe('0')
  unmount()
  render(<App />) // simula abrir de novo / outra aba (mesmo localStorage)
  expect(await screen.findByTestId('auto-refresh')).toHaveTextContent('Auto-refresh off')
})
