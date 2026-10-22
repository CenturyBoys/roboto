import { useEffect, useState } from 'react'
import { getCosts } from '@/lib/api'
import type { Costs as CostsData } from '@/types'
import { Card } from './ui/card'
import { Td, TableWrap, Th } from './ui/table'

export function Costs() {
  const [data, setData] = useState<CostsData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCosts()
      .then(setData)
      .catch(() => setError('erro ao carregar (token correto?)'))
  }, [])

  if (error) return <p className="text-muted">{error}</p>
  if (!data) return <p className="text-muted">carregando…</p>
  return (
    <Card>
      <p className="mb-2 font-bold text-accent">
        Total: {data.totals.tokens} tokens · ${data.totals.cost_usd.toFixed(4)}
      </p>
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
              <Td mono>{c.tokens_in}</Td>
              <Td mono>{c.tokens_out}</Td>
              <Td mono>${c.cost_usd.toFixed(4)}</Td>
              <Td mono>{c.at}</Td>
            </tr>
          ))}
        </tbody>
      </table>
      </TableWrap>
    </Card>
  )
}
