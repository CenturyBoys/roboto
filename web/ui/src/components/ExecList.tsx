import { useCallback, useEffect, useMemo, useState } from 'react'
import { listExecutions } from '@/lib/api'
import type { Execution } from '@/types'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Card } from './ui/card'
import { StatePill } from './ui/state-pill'
import { Stat } from './ui/stat'
import { Td, Th } from './ui/table'
import { TableSkeleton } from './ui/skeleton'
import { EmptyState } from './ui/empty-state'
import { ErrorState } from './ui/error-state'

// Buckets de estado (mais útil ao operador que o estado cru): o filtro opera sobre eles.
const BUCKETS: { key: string; label: string; states: string[] }[] = [
  { key: 'todos', label: 'Todos', states: [] },
  { key: 'ativos', label: 'Ativos', states: ['running', 'waiting', 'verifying'] },
  { key: 'fila', label: 'Na fila', states: ['queued'] },
  { key: 'done', label: 'Concluídos', states: ['done'] },
  { key: 'falhas', label: 'Falhas', states: ['failed', 'abandoned'] },
]

// Lista de execuções (torre de controle). Com `auto`, repõe a cada 4s sem recarregar a página.
export function ExecList({ auto, onSelect }: { auto: boolean; onSelect: (id: number) => void }) {
  const [rows, setRows] = useState<Execution[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [bucket, setBucket] = useState('todos')

  const load = useCallback(async () => {
    try {
      const d = await listExecutions()
      setRows(d.executions)
      setError(null)
    } catch {
      setError('Não consegui carregar as execuções. Verifique o token do console.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!auto) return
    const t = setInterval(() => void load(), 4000)
    return () => clearInterval(t)
  }, [auto, load])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const b of BUCKETS)
      c[b.key] = b.states.length ? rows.filter((r) => b.states.includes(r.state)).length : rows.length
    return c
  }, [rows])

  const active = BUCKETS.find((b) => b.key === bucket) ?? BUCKETS[0]
  const filtered = active.states.length ? rows.filter((r) => active.states.includes(r.state)) : rows

  if (loading) return <TableSkeleton rows={6} cols={5} />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (!rows.length)
    return (
      <EmptyState
        icon="⚡"
        title="Nenhuma execução ainda"
        hint="Abra uma issue e clique em Refinar ou Implementar — a execução aparece aqui ao vivo."
      />
    )

  return (
    <div className="space-y-4">
      {/* cards-resumo: número grande, contexto pequeno */}
      <div className="grid grid-cols-3 gap-2 sm:max-w-md" data-testid="exec-summary">
        <Stat label="Ativos" value={counts.ativos} accent={counts.ativos > 0} />
        <Stat label="Concluídos" value={counts.done} />
        <Stat label="Falhas" value={counts.falhas} />
      </div>

      {/* filtro por estado (chips) */}
      <div className="flex flex-wrap items-center gap-2" data-testid="exec-filters">
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            onClick={() => setBucket(b.key)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs transition-colors',
              bucket === b.key
                ? 'border-accent bg-accent/10 text-accent'
                : 'border-border text-muted hover:border-accent',
            )}
          >
            {b.label} <span className="tabular-nums opacity-70">{counts[b.key]}</span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title={`Nenhuma execução em "${active.label.toLowerCase()}"`}
          hint="Troque o filtro acima."
        />
      ) : (
        <>
          {/* Celular: cards tocáveis (a linha inteira abre o detalhe). */}
          <div className="flex flex-col gap-2 sm:hidden">
            {filtered.map((r) => (
              <button
                key={r.id}
                onClick={() => onSelect(r.id)}
                className="rounded-xl border border-border bg-surface p-3 text-left hover:border-accent"
              >
                <div className="flex items-center justify-between gap-2">
                  <StatePill state={r.state} />
                  <span className="text-xs text-muted">{timeAgo(r.updated_at)}</span>
                </div>
                <div className="mt-1.5 text-sm">
                  <span className="font-medium">#{r.issue_id}</span>{' '}
                  <span className="text-muted">
                    · {r.agent} · exec {r.id}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* Tablet/desktop: tabela — estado ANCORA a linha. */}
          <Card className="hidden overflow-hidden p-0 sm:block" data-testid="exec-table">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted">
                  <Th>estado</Th>
                  <Th>issue</Th>
                  <Th>agente</Th>
                  <Th>quando</Th>
                  <Th>exec</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => onSelect(r.id)}
                    className="cursor-pointer border-t border-border hover:bg-background/40"
                  >
                    <Td>
                      <StatePill state={r.state} />
                    </Td>
                    <Td>
                      <span className="font-medium">#{r.issue_id}</span>
                    </Td>
                    <Td>{r.agent}</Td>
                    <Td className="text-muted">{timeAgo(r.updated_at)}</Td>
                    <Td mono className="text-muted">
                      {r.id}
                      {r.attempt > 0 ? ` ·t${r.attempt}` : ''}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}
