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

test('dep FECHADA (não é nó) não vira ⛔, e filho-épico não ganha badge de épico', async () => {
  // #5 depende de #9 (fechado, não é nó) e de #6 (aberto) → só o #6 aparece no ⛔.
  // #5 é is_epic=true MAS é filho do épico #1 → NÃO mostra 📦 épico (sem épico-dentro-de-épico).
  const g = {
    repo: 'acme/app',
    nodes: [
      { number: 1, title: 'Épico', labels: ['epic'], is_epic: true, state: 'open' },
      { number: 5, title: 'task refinada', labels: [], is_epic: true, state: 'open' },
      { number: 6, title: 'dep aberta', labels: [], is_epic: false, state: 'open' },
    ],
    edges: [
      { from: 1, to: 5, kind: 'epic-child' },
      { from: 5, to: 9, kind: 'depends-on' }, // #9 fechado (ausente)
      { from: 5, to: 6, kind: 'depends-on' }, // #6 aberto
    ],
    has_cycle: false,
  }
  stub(g)
  render(<IssueTree onSelect={vi.fn()} />)
  const blocked = await screen.findByTestId('tree-blocked-5')
  expect(blocked).toHaveTextContent('depende de #6') // só a aberta
  expect(blocked).not.toHaveTextContent('#9') // a fechada sumiu
  // #5 (filho de épico) NÃO é badgeado como épico; só o #1 (topo) é
  expect(screen.getAllByText('📦 épico')).toHaveLength(1)
})
