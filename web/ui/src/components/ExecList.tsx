import { useCallback, useEffect, useState } from 'react'
import { listExecutions } from '@/lib/api'
import type { Execution } from '@/types'
import { Card } from './ui/card'
import { StatePill } from './ui/state-pill'
import { Td, Th } from './ui/table'

// Lista de execuções (torre de controle). Com `auto`, repõe a cada 4s sem recarregar a página.
export function ExecList({ auto, onSelect }: { auto: boolean; onSelect: (id: number) => void }) {
  const [rows, setRows] = useState<Execution[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await listExecutions()
      setRows(d.executions)
      setError(null)
    } catch {
      setError('erro ao carregar (token correto?)')
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

  if (error) return <p className="text-muted">{error}</p>
  if (!rows.length) return <p className="text-muted">sem execuções ainda</p>
  return (
    <>
      {/* Celular: cards tocáveis (a linha inteira abre o detalhe). */}
      <div className="flex flex-col gap-2 sm:hidden">
        {rows.map((r) => (
          <button
            key={r.id}
            onClick={() => onSelect(r.id)}
            className="rounded-xl border border-border bg-surface p-3 text-left hover:border-accent"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs text-muted">
                #{r.id} · {r.issue_id}
              </span>
              <StatePill state={r.state} />
            </div>
            <div className="mt-1 text-sm">
              {r.agent} <span className="text-muted">· tentativa {r.attempt}</span>
            </div>
          </button>
        ))}
      </div>

      {/* Tablet/desktop: tabela. */}
      <Card className="hidden overflow-hidden p-0 sm:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-muted">
              <Th>id</Th>
              <Th>issue</Th>
              <Th>agente</Th>
              <Th>estado</Th>
              <Th>tent.</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                onClick={() => onSelect(r.id)}
                className="cursor-pointer border-t border-border hover:bg-background/40"
              >
                <Td mono>{r.id}</Td>
                <Td mono>{r.issue_id}</Td>
                <Td>{r.agent}</Td>
                <Td>
                  <StatePill state={r.state} />
                </Td>
                <Td mono>{r.attempt}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
