import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IssuesList } from './IssuesList'

beforeEach(() => {
  localStorage.setItem('rtok', 't')
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            repo: 'arenavalendo/main',
            issues: [
              { number: 180, title: 'rate limit distribuído', labels: ['feat', 'roboto'] },
              { number: 112, title: 'targeting por parceiro', labels: ['feat'] },
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

test('lista as issues abertas do repo com labels', async () => {
  render(<IssuesList />)
  expect(await screen.findByText('rate limit distribuído')).toBeInTheDocument()
  expect(screen.getByText('#112')).toBeInTheDocument()
  expect(screen.getByText('roboto')).toBeInTheDocument() // chip de label
})
