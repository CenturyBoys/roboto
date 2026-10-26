import { useState } from 'react'
import { reviewPr } from '@/lib/api'
import { Button } from './ui/button'
import { Card, CardLabel, CardTitle } from './ui/card'

// Revisar QUALQUER PR aberto (do time/bot, não só os do fleet) com o revisor deepseek (JUDGE).
// Posta o parecer como comentário no PR e mostra aqui. reviewer≠autor (D28).
export function ReviewPr() {
  const [num, setNum] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ approved: boolean; issues: string[]; author: string } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)

  async function run() {
    const n = Number(num)
    if (!n || busy) return
    setBusy(true)
    setResult(null)
    setError(null)
    try {
      const r = await reviewPr(n)
      setResult({ approved: r.approved, issues: r.issues, author: r.author })
    } catch {
      setError('não deu p/ revisar — PR existe? (nº/repo). O parecer também vai como comentário no PR.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="space-y-3">
      <CardTitle>Revisar PR com o fleet (deepseek)</CardTitle>
      <p className="text-xs text-muted">
        Revisa qualquer PR aberto (time ou bot) e posta o parecer como comentário no PR.
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          value={num}
          onChange={(e) => setNum(e.target.value.replace(/\D/g, ''))}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void run()
          }}
          placeholder="nº do PR (ex.: 199)"
          className="w-40 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm outline-none focus:border-accent"
        />
        <Button variant="default" disabled={busy} onClick={() => void run()}>
          {busy ? 'revisando…' : 'revisar PR'}
        </Button>
      </div>
      {error && <p className="text-xs text-red-300">{error}</p>}
      {result && (
        <div className="space-y-1">
          <CardLabel>
            PR de <span className="text-accent">{result.author}</span> —{' '}
            {result.approved ? (
              <span className="font-bold text-green-300">✅ aprovado</span>
            ) : (
              <span className="font-bold text-accent">🔁 pediu correções</span>
            )}
          </CardLabel>
          {!result.approved && (
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {result.issues.map((it, i) => (
                <li key={i}>{it}</li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted">(o parecer também foi postado como comentário no PR)</p>
        </div>
      )}
    </Card>
  )
}
