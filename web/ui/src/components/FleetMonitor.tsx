import { useCallback, useEffect, useState } from 'react'
import { getOverview } from '@/lib/api'
import type { Overview } from '@/types'
import { Card } from './ui/card'
import { Stat } from './ui/stat'
import { Td, TableWrap, Th } from './ui/table'
import { TableSkeleton } from './ui/skeleton'
import { ErrorState } from './ui/error-state'

// Monitor da frota (trilha M): saúde operacional num golpe — runs por estado, dead-letters,
// orçamento. Determinístico (sem LLM); a verdade segue na issue+git.
export function FleetMonitor() {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    getOverview()
      .then(setData)
      .catch(() => setError('Não consegui carregar o monitor. Verifique o token do console.'))
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 5000) // auto-refresh: a frota viva
    return () => clearInterval(t)
  }, [load])

  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data) return <TableSkeleton rows={4} cols={2} />

  const b = data.budget
  return (
    <div className="space-y-4" data-testid="fleet-monitor">
      {/* saúde num golpe: ativos / fila / falhas / dead-letters */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:max-w-2xl">
        <Stat
          label="Ativos"
          value={data.wip_limit > 0 ? `${data.active}/${data.wip_limit}` : data.active}
          accent
        />
        <Stat label="Na fila" value={data.queued} />
        <Stat label="Falhas" value={data.failed} />
        <Stat label="Dead-letters" value={data.dead_letters} />
      </div>

      {b?.cap_usd > 0 && (
        <Card data-testid="monitor-budget">
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="font-bold">Orçamento do mês</span>
            <span className="font-mono text-muted">
              ${b.spent_usd.toFixed(2)} / ${b.cap_usd.toFixed(2)} · {Math.round(b.pct * 100)}%
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-border">
            <div
              className={b.over ? 'h-full bg-red-400' : b.alert ? 'h-full bg-accent' : 'h-full bg-green-400'}
              style={{ width: `${Math.round(Math.min(b.pct, 1) * 100)}%` }}
            />
          </div>
        </Card>
      )}

      <Card>
        <p className="mb-1 text-sm text-muted">Execuções por estado ({data.total} no total)</p>
        <TableWrap>
          <table className="w-full min-w-[280px] text-sm">
            <thead>
              <tr className="text-muted">
                <Th>estado</Th>
                <Th>qtd</Th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_state).map(([state, n]) => (
                <tr key={state} className="border-t border-border">
                  <Td>{state}</Td>
                  <Td mono>{n}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Card>
    </div>
  )
}
