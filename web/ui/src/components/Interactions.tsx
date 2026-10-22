import { useCallback, useEffect, useState } from 'react'
import { answerInteraction, listInteractions } from '@/lib/api'
import type { Interaction } from '@/types'
import { Button } from './ui/button'
import { Card } from './ui/card'

// Inbox de HITL (Fatia 3): responder as pendências do motor pelo cockpit — decisão (botões por
// opção) ou pergunta aberta (campo de texto). Mesmo backend do reply do Telegram (1ª válida vence).
export function Interactions() {
  const [rows, setRows] = useState<Interaction[]>([])
  const [error, setError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setRows((await listInteractions()).interactions)
      setError(null)
    } catch {
      setError('erro ao carregar (token correto?)')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function answer(id: number, text: string) {
    if (!text.trim()) return
    setBusy(id)
    try {
      await answerInteraction(id, text)
      await load()
    } catch {
      setError('erro ao responder')
    } finally {
      setBusy(null)
    }
  }

  if (error) return <p className="text-muted">{error}</p>
  if (!rows.length) return <p className="text-muted">nenhuma interação pendente 🎉</p>
  return (
    <div className="flex flex-col gap-3">
      {rows.map((i) => (
        <Card key={i.id}>
          <span className="text-xs text-muted">
            E-{i.execution_id} · {i.kind} · Q-{i.id}
          </span>
          <p className="mb-2 mt-1 text-sm">{i.prompt}</p>
          {i.options.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {i.options.map((opt) => (
                <Button
                  key={opt}
                  variant="outline"
                  disabled={busy === i.id}
                  onClick={() => void answer(i.id, opt)}
                >
                  {opt}
                </Button>
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <input
                value={drafts[i.id] ?? ''}
                onChange={(e) => setDrafts((d) => ({ ...d, [i.id]: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void answer(i.id, drafts[i.id] ?? '')
                }}
                placeholder="sua resposta…"
                className="min-w-60 flex-1 rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
              />
              <Button
                variant="default"
                disabled={busy === i.id}
                onClick={() => void answer(i.id, drafts[i.id] ?? '')}
              >
                {busy === i.id ? 'enviando…' : 'responder'}
              </Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}
