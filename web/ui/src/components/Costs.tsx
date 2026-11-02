import { useCallback, useEffect, useState } from 'react'
import { getCosts } from '@/lib/api'
import type { Budget, Costs as CostsData } from '@/types'
import { timeAgo } from '@/lib/format'
import { Card } from './ui/card'
import { Stat } from './ui/stat'
import { Td, TableWrap, Th } from './ui/table'
import { TableSkeleton } from './ui/skeleton'
import { EmptyState } from './ui/empty-state'
import { ErrorState } from './ui/error-state'

export function Costs() {
  const [data, setData] = useState<CostsData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    getCosts()
      .then(setData)
      .catch(() => setError('Não consegui carregar os custos. Verifique o token do console.'))
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 5000) // auto-refresh: custos novos aparecem sem F5
    return () => clearInterval(t)
  }, [load])

  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data) return <TableSkeleton rows={5} cols={6} />
  if (!data.calls.length)
    return (
      <EmptyState
        icon="$"
        title="Sem custos ainda"
        hint="Cada chamada de modelo (refino, implementação, review) aparece aqui com tokens e $."
      />
    )

  return (
    <div className="space-y-4">
      {data.budget?.cap_usd > 0 && <BudgetBar budget={data.budget} />}

      {/* cards-resumo: métrica grande, contexto pequeno */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:max-w-lg">
        <Stat label="Custo total" value={`$${data.totals.cost_usd.toFixed(4)}`} accent />
        <Stat label="Tokens" value={data.totals.tokens.toLocaleString()} />
        <Stat label="Chamadas" value={data.calls.length} />
      </div>

      <Card>
        {data.by_execution.length > 0 && (
          <div className="mb-4">
            <p className="mb-1 text-sm text-muted">Por execução</p>
            <TableWrap>
              <table className="w-full min-w-[320px] text-sm">
                <thead>
                  <tr className="text-muted">
                    <Th>execução</Th>
                    <Th>tokens</Th>
                    <Th>$</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_execution.map((e) => (
                    <tr key={e.run_id} className="border-t border-border">
                      <Td mono>E-{e.run_id}</Td>
                      <Td mono>{e.tokens.toLocaleString()}</Td>
                      <Td mono>${e.cost_usd.toFixed(4)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </div>
        )}

        <p className="mb-1 text-sm text-muted">Chamadas</p>
        <TableWrap>
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-muted">
                <Th>run</Th>
                <Th>modelo</Th>
                <Th>tier</Th>
                <Th>in</Th>
                <Th>out</Th>
                <Th>$</Th>
                <Th>quando</Th>
              </tr>
            </thead>
            <tbody>
              {data.calls.map((c, idx) => (
                <tr key={idx} className="border-t border-border">
                  <Td mono>{c.run_id}</Td>
                  <Td>{c.model}</Td>
                  <Td>{c.tier}</Td>
                  <Td mono>{c.tokens_in.toLocaleString()}</Td>
                  <Td mono>{c.tokens_out.toLocaleString()}</Td>
                  <Td mono>${c.cost_usd.toFixed(4)}</Td>
                  <Td className="text-muted" title={c.at}>
                    {timeAgo(c.at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Card>
    </div>
  )
}

// Orçamento do mês (trilha L): gasto vs teto mensal. Verde <80% · âmbar ≥80% · vermelho ≥100%.
function BudgetBar({ budget }: { budget: Budget }) {
  const pct = Math.min(budget.pct, 1)
  const color = budget.over ? 'bg-red-400' : budget.alert ? 'bg-accent' : 'bg-green-400'
  const label = budget.over ? 'acima do teto' : budget.alert ? 'atenção (≥80%)' : 'dentro do teto'
  return (
    <Card data-testid="budget-bar">
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-bold">Orçamento do mês</span>
        <span className="font-mono text-muted">
          ${budget.spent_usd.toFixed(2)} / ${budget.cap_usd.toFixed(2)} ·{' '}
          {Math.round(budget.pct * 100)}% · {label}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-border">
        <div className={`h-full ${color}`} style={{ width: `${Math.round(pct * 100)}%` }} />
      </div>
    </Card>
  )
}
