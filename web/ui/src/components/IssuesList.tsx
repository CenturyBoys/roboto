import { useEffect, useState } from 'react'
import { listIssues } from '@/lib/api'
import type { IssueList } from '@/types'
import { Card } from './ui/card'

// Issues abertas do repo (entry point do refino no cockpit, Fatia 6). Clicar numa issue vai abrir a
// conversa de refino (próximo incremento); por ora, lista + link pro GitHub.
export function IssuesList() {
  const [data, setData] = useState<IssueList | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listIssues()
      .then(setData)
      .catch(() => setError('erro ao carregar (token correto?)'))
  }, [])

  if (error) return <p className="text-muted">{error}</p>
  if (!data) return <p className="text-muted">carregando…</p>
  if (data.note || data.error) {
    return <p className="text-muted">{data.note ?? data.error} — configure o GitHub no setup.</p>
  }
  if (!data.issues.length) return <p className="text-muted">nenhuma issue aberta em {data.repo} 🎉</p>
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted">
        {data.issues.length} issue(s) aberta(s) em <span className="font-mono">{data.repo}</span>
      </p>
      {data.issues.map((i) => (
        <Card key={i.number} className="flex items-center gap-3">
          <span className="font-mono text-sm text-accent">#{i.number}</span>
          <span className="flex-1 text-sm">{i.title}</span>
          <a
            className="text-xs text-muted hover:text-accent"
            href={`https://github.com/${data.repo}/issues/${i.number}`}
            target="_blank"
            rel="noopener"
          >
            ↗ GitHub
          </a>
        </Card>
      ))}
    </div>
  )
}
