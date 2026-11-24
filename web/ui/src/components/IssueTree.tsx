import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { driveEpic, getIssueTree, graphAudit, type DoctorResult, type DriveResult } from '@/lib/api'
import { rootOpenBlockers, unblockCounts } from '@/lib/graph'
import type { IssueGraph } from '@/types'
import { Card } from './ui/card'
import { Button } from './ui/button'

// Mapa de issues (árvore/DAG): cruza as NOSSAS deps (épico→filha, depende-de) com as NATIVAS do
// GitHub (sub-issues/tracked/xref). Renderiza a HIERARQUIA indentada (épico → filha → folha) e, em
// cada nó, as arestas de DEPENDÊNCIA (bloqueios) + cross-references. Clicar num nó abre o refino.
//
// Hierarquia = arestas epic-child + subissue-native (pai → filha). Dependência = depends-on
// (filha → bloqueadora). Guard de ciclo: não revisita um nó já no caminho (DAG best-effort).
const HIERARCHY = new Set(['epic-child', 'subissue-native'])

function stateDot(isEpic: boolean, blocked: boolean, state: string | null): string {
  if (state === 'closed') return 'bg-border' // fechada (pode entrar como bloqueadora)
  if (blocked) return 'bg-orange-400' // tem bloqueio pendente
  if (isEpic) return 'bg-accent' // épico (guarda-chuva)
  return 'bg-green-400' // aberta e livre
}

export function IssueTree({ onSelect }: { onSelect: (n: number) => void }) {
  const [graph, setGraph] = useState<IssueGraph | null>(null)
  const [error, setError] = useState<string | null>(null)
  // driver de épico: por épico, 'loading' enquanto roda, ou o resultado (prontas/despachadas/etc).
  const [drive, setDrive] = useState<Record<number, 'loading' | DriveResult>>({})
  // graph doctor (repo todo): 'loading', o relatório, ou null (não rodado).
  const [doctor, setDoctor] = useState<'loading' | DoctorResult | null>(null)

  async function doDoctor() {
    setDoctor('loading')
    try {
      const r = await graphAudit()
      setDoctor(r)
      getIssueTree().then(setGraph).catch(() => {}) // recarrega: o doctor pode ter reaberto issues
    } catch {
      setDoctor(null)
    }
  }

  async function doDrive(epic: number) {
    setDrive((d) => ({ ...d, [epic]: 'loading' }))
    try {
      const r = await driveEpic(epic)
      setDrive((d) => ({ ...d, [epic]: r }))
    } catch {
      setDrive((d) => {
        const { [epic]: _drop, ...rest } = d
        return rest
      })
    }
  }

  useEffect(() => {
    getIssueTree()
      .then(setGraph)
      .catch(() => setError('erro ao carregar (token correto?)'))
  }, [])

  // índices derivados do grafo (hierarquia, bloqueios, xref) — memoizados por grafo.
  const idx = useMemo(() => {
    const byNumber = new Map((graph?.nodes ?? []).map((n) => [n.number, n]))
    const children = new Map<number, number[]>()
    const hasParent = new Set<number>()
    const blockers = new Map<number, number[]>()
    const xref = new Map<number, number>()
    for (const e of graph?.edges ?? []) {
      if (HIERARCHY.has(e.kind)) {
        const arr = children.get(e.from) ?? []
        if (!arr.includes(e.to)) arr.push(e.to)
        children.set(e.from, arr)
        if (byNumber.has(e.to)) hasParent.add(e.to)
      } else if (e.kind === 'depends-on') {
        const arr = blockers.get(e.from) ?? []
        if (!arr.includes(e.to)) arr.push(e.to)
        blockers.set(e.from, arr)
      } else if (e.kind === 'xref') {
        xref.set(e.from, (xref.get(e.from) ?? 0) + 1)
        xref.set(e.to, (xref.get(e.to) ?? 0) + 1)
      }
    }
    // transitividade (derivada, não materializada): bloqueador-raiz aberto + quantas destrava.
    const isClosed = (n: number) => byNumber.get(n)?.state === 'closed'
    const rootBlockers = rootOpenBlockers(blockers, isClosed)
    const unblocks = unblockCounts(blockers, isClosed)
    return { byNumber, children, hasParent, blockers, xref, rootBlockers, unblocks }
  }, [graph])

  if (error) return <p className="text-muted">{error}</p>
  if (!graph) return <p className="text-muted">carregando…</p>
  if (graph.note || graph.error) {
    return <p className="text-muted">{graph.note ?? graph.error} — configure o GitHub no setup.</p>
  }
  if (!graph.nodes.length) {
    return <p className="text-muted">nenhuma issue aberta em {graph.repo} 🎉</p>
  }

  const repo = graph.repo // capturado: o closure renderNode perde o narrowing de `graph`
  // raízes = quem não é filha de ninguém; épicos primeiro, depois por número.
  const roots = graph.nodes
    .filter((n) => !idx.hasParent.has(n.number))
    .sort((a, b) => Number(b.is_epic) - Number(a.is_epic) || a.number - b.number)

  function renderNode(num: number, depth: number, path: Set<number>): ReactNode {
    const node = idx.byNumber.get(num)
    if (!node) return null
    const nextPath = new Set(path).add(num)
    const kids = (idx.children.get(num) ?? [])
      .filter((k) => idx.byNumber.has(k) && !path.has(k)) // guard de ciclo
      .sort((a, b) => a - b)
    const blockers = idx.blockers.get(num) ?? []
    const xrefs = idx.xref.get(num) ?? 0
    const roots = idx.rootBlockers.get(num) ?? []
    const unblocks = idx.unblocks.get(num) ?? 0
    // mostra a RAIZ só quando ela adiciona info (≠ do bloqueador direto já no badge ⛔)
    const directOpen = blockers.filter((b) => idx.byNumber.get(b)?.state !== 'closed')
    const showRoot = roots.length > 0 && roots.join(',') !== [...directOpen].sort((a, z) => a - z).join(',')
    return (
      <div
        key={`${depth}:${num}`}
        className={depth ? 'ml-4 border-l border-border pl-3' : ''}
        data-testid={`tree-node-${num}`}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 py-1">
          <span
            className={`inline-block h-2 w-2 shrink-0 rounded-full ${stateDot(node.is_epic, blockers.length > 0, node.state)}`}
          />
          <button
            type="button"
            onClick={() => onSelect(num)}
            className="font-mono text-sm text-accent hover:underline"
          >
            #{num}
          </button>
          {node.is_epic && (
            <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] text-accent">
              📦 épico
            </span>
          )}
          {node.is_epic && (
            <Button
              variant="outline"
              className="h-6 px-2 py-0 text-[11px]"
              disabled={drive[num] === 'loading'}
              onClick={() => void doDrive(num)}
              title="Driver: despacha as filhas prontas (ordem das deps), subdivide filha-épico, respeita o teto de budget"
            >
              {drive[num] === 'loading' ? '▶ rodando…' : '▶ driver'}
            </Button>
          )}
          <span className="min-w-0 text-sm">{node.title}</span>
          {node.labels.map((l) => (
            <span
              key={l}
              className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted"
            >
              {l}
            </span>
          ))}
          {blockers.length > 0 && (
            <span className="text-[11px] text-orange-400" data-testid={`tree-blocked-${num}`}>
              ⛔ depende de {blockers.map((b) => `#${b}`).join(', ')}
            </span>
          )}
          {showRoot && (
            <span
              className="text-[11px] text-red-400"
              data-testid={`tree-root-${num}`}
              title="bloqueador-raiz: a issue ABERTA no fundo da cadeia que de fato trava esta (transitivo)"
            >
              🔒 raiz: {roots.map((b) => `#${b}`).join(', ')}
            </span>
          )}
          {unblocks > 0 && (
            <span
              className="text-[11px] text-green-400"
              data-testid={`tree-unblocks-${num}`}
              title="quantas issues abertas esta destrava em cascata quando fechar (transitivo)"
            >
              🔓 destrava {unblocks}
            </span>
          )}
          {xrefs > 0 && (
            <span className="text-[11px] text-muted" title="cross-references nativas do GitHub">
              ↔ {xrefs}
            </span>
          )}
          <a
            className="text-xs text-muted hover:text-accent"
            href={`https://github.com/${repo}/issues/${num}`}
            target="_blank"
            rel="noopener"
          >
            ↗
          </a>
        </div>
        {(() => {
          const r = drive[num]
          if (!r || r === 'loading') return null
          return (
            <div className="mb-1 ml-4 rounded border border-border bg-surface/40 px-2 py-1 text-[11px] text-muted">
              {r.budget_blocked ? (
                <span className="text-orange-400">
                  ⛔ teto de budget estourado — gasto ${r.spent_usd.toFixed(2)} ≥ $
                  {r.budget_usd.toFixed(2)}. Não despachei (decisão humana).
                </span>
              ) : (
                <span>
                  {r.dispatched.length > 0 ? (
                    <span className="text-green-400">
                      ▶ despachei {r.dispatched.map((n) => `#${n}`).join(', ')}
                    </span>
                  ) : (
                    <span>nada pronto p/ despachar</span>
                  )}
                  {r.subdivided.length > 0 && (
                    <span className="text-accent">
                      {' · '}✂️ subdividi {r.subdivided.map((n) => `#${n}`).join(', ')}
                    </span>
                  )}
                  {r.waiting.length > 0 && <span>{' · '}⏳ esperando {r.waiting.length}</span>}
                  {r.budget_usd > 0 && (
                    <span>
                      {' · '}💲${r.spent_usd.toFixed(2)}/${r.budget_usd.toFixed(2)}
                    </span>
                  )}
                </span>
              )}
            </div>
          )
        })()}
        {kids.map((k) => renderNode(k, depth + 1, nextPath))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
        <span>
          mapa de <span className="font-mono">{graph.repo}</span> · {graph.nodes.length} issue(s)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-accent" /> épico
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-orange-400" /> bloqueada
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-green-400" /> livre
        </span>
        <Button
          variant="outline"
          className="ml-auto h-6 px-2 py-0 text-[11px]"
          disabled={doctor === 'loading'}
          onClick={() => void doDoctor()}
          title="Graph doctor: audita o grafo (deps, done confiável, redundância, órfãos, ciclos), reabre sozinho o que é seguro e lista o resto p/ você"
        >
          {doctor === 'loading' ? '🩺 auditando…' : '🩺 doctor'}
        </Button>
      </div>
      {doctor && doctor !== 'loading' && (
        <Card className="flex flex-col gap-2 text-xs">
          <span className="text-sm">
            🩺 Graph doctor — {doctor.findings.length} achado(s) ·{' '}
            <span className="text-green-400">{doctor.applied.length} curado(s)</span> ·{' '}
            <span className="text-orange-300">{doctor.pending.length} pendente(s)</span>
          </span>
          {doctor.applied.length > 0 && (
            <div className="text-green-400">
              ✅ reabri sozinho (protetor):{' '}
              {doctor.applied.map((a) => `#${a.issue}`).join(', ')}
            </div>
          )}
          {doctor.pending.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-orange-300">⚠️ precisa de você / do gerente:</span>
              {doctor.pending.map((a) => (
                <div key={`${a.kind}:${a.issue}`} className="ml-3 text-muted">
                  <span className="font-mono text-accent">#{a.issue}</span>{' '}
                  <span className="text-orange-300">[{a.action}]</span> {a.detail}
                </div>
              ))}
            </div>
          )}
          {doctor.findings.length === 0 && (
            <span className="text-green-400">grafo saudável — nenhuma inconsistência 🎉</span>
          )}
        </Card>
      )}
      {graph.has_cycle && (
        <p className="rounded-lg border border-orange-400/40 bg-orange-400/10 px-3 py-2 text-xs text-orange-300">
          ⚠️ há um ciclo de dependências — o mapa é best-effort e pode repetir um ramo.
        </p>
      )}
      <Card>{roots.map((r) => renderNode(r.number, 0, new Set()))}</Card>
    </div>
  )
}
