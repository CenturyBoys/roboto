import { useEffect, useMemo, useState } from 'react'
import { listIssues } from '@/lib/api'
import type { IssueList } from '@/types'
import { Card } from './ui/card'

// Issues abertas do repo (entry point do refino no cockpit, Fatia 6). Só `state=open` (closed não
// entra). Filtro client-side por nº/título/label. Clicar vai abrir a conversa de refino (próximo).
export function IssuesList() {
  const [data, setData] = useState<IssueList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    listIssues()
      .then(setData)
      .catch(() => setError('erro ao carregar (token correto?)'))
  }, [])

  const filtered = useMemo(() => {
    const issues = data?.issues ?? []
    const term = q.trim().toLowerCase()
    if (!term) return issues
    return issues.filter(
      (i) =>
        String(i.number).includes(term) ||
        i.title.toLowerCase().includes(term) ||
        i.labels.some((l) => l.toLowerCase().includes(term)),
    )
  }, [data, q])

  if (error) return <p className="text-muted">{error}</p>
  if (!data) return <p className="text-muted">carregando…</p>
  if (data.note || data.error) {
    return <p className="text-muted">{data.note ?? data.error} — configure o GitHub no setup.</p>
  }
  if (!data.issues.length) return <p className="text-muted">nenhuma issue aberta em {data.repo} 🎉</p>
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filtrar por nº, título ou label…"
          className="min-w-60 flex-1 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm outline-none focus:border-accent"
        />
        <span className="text-sm text-muted">
          {filtered.length}/{data.issues.length} aberta(s) · <span className="font-mono">{data.repo}</span>
        </span>
      </div>
      {filtered.map((i) => (
        <Card key={i.number} className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-mono text-sm text-accent">#{i.number}</span>
          <span className="min-w-0 flex-1 text-sm">{i.title}</span>
          {i.labels.map((l) => (
            <span
              key={l}
              className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted"
            >
              {l}
            </span>
          ))}
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
