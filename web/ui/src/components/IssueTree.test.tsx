import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { IssueTree } from './IssueTree'

// grafo: épico #1 → filhas #2 e #3; #3 depende de #2; #2 tem 1 xref nativa.
const GRAPH = {
  repo: 'acme/app',
  nodes: [
    { number: 1, title: 'Épico motor vivo', labels: ['epic'], is_epic: true, state: 'open' },
    { number: 2, title: 'sub A', labels: [], is_epic: false, state: 'open' },
    { number: 3, title: 'sub B', labels: [], is_epic: false, state: 'open' },
  ],
  edges: [
    { from: 1, to: 2, kind: 'epic-child' },
    { from: 1, to: 3, kind: 'epic-child' },
    { from: 3, to: 2, kind: 'depends-on' },
    { from: 2, to: 1, kind: 'xref' },
  ],
  has_cycle: false,
}

function stub(graph: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.endsWith('/issues/tree') ? graph : {}
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
}

beforeEach(() => localStorage.setItem('rtok', 't'))
afterEach(() => vi.unstubAllGlobals())

test('renderiza épico com filhas aninhadas e o bloqueio da dependência', async () => {
  stub(GRAPH)
  const onSelect = vi.fn()
  render(<IssueTree onSelect={onSelect} />)

  // épico aparece com o badge
  expect(await screen.findByText('📦 épico')).toBeInTheDocument()
  // as filhas estão ANINHADAS sob o épico (nó 1 contém os nós 2 e 3)
  const epic = screen.getByTestId('tree-node-1')
  expect(epic.querySelector('[data-testid="tree-node-2"]')).not.toBeNull()
  expect(epic.querySelector('[data-testid="tree-node-3"]')).not.toBeNull()
  // o bloqueio depends-on vira badge "depende de #2" no nó 3
  expect(screen.getByTestId('tree-blocked-3')).toHaveTextContent('depende de #2')

  // clicar no nº abre o refino daquela issue
  fireEvent.click(screen.getByText('#3'))
  expect(onSelect).toHaveBeenCalledWith(3)
})

test('avisa quando há ciclo de dependências', async () => {
  stub({ ...GRAPH, has_cycle: true })
  render(<IssueTree onSelect={vi.fn()} />)
  await waitFor(() => expect(screen.getByText(/ciclo de dependências/)).toBeInTheDocument())
})
