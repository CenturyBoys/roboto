import { useEffect, useState } from 'react'
import { listInteractions } from '@/lib/api'
import type { Interaction } from '@/types'
import { Card } from './ui/card'
import { Td, Th } from './ui/table'

// Inbox de HITL (pendências que esperam o humano). Responder pelo front é a Fatia 3.
export function Interactions() {
  const [rows, setRows] = useState<Interaction[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listInteractions()
      .then((d) => setRows(d.interactions))
      .catch(() => setError('erro ao carregar (token correto?)'))
  }, [])

  if (error) return <p className="text-muted">{error}</p>
  if (!rows.length) return <p className="text-muted">nenhuma interação pendente</p>
  return (
    <Card>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted">
            <Th>id</Th>
            <Th>tipo</Th>
            <Th>pergunta</Th>
            <Th>status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i.id} className="border-t border-border">
              <Td mono>{i.id}</Td>
              <Td>{i.kind}</Td>
              <Td>{i.prompt}</Td>
              <Td>{i.status}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
