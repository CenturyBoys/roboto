import { useEffect, useRef, useState } from 'react'
import { dispatchEngineRefine, getIssue, refineIssue } from '@/lib/api'
import type { IssueDetail } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel, CardTitle } from './ui/card'

type Bubble = { role: 'você' | 'refiner'; text: string }

// Painel de refino de uma issue (trilha O, Fatia 6). CAMINHO PRINCIPAL = o motor, que LÊ o repo
// (engine-scoped, D31). A "conversa rápida" é o modelo cego (sem repo) — secundária, NÃO auto-dispara.
export function IssueRefine({
  number,
  onBack,
  onOpenRun,
}: {
  number: number
  onBack: () => void
  onOpenRun: (runId: number) => void
}) {
  const [detail, setDetail] = useState<IssueDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const transcript = useRef<[string, string][]>([])

  // só carrega o detalhe da issue — NÃO dispara o chat cego (era isso que incomodava)
  useEffect(() => {
    getIssue(number)
      .then(setDetail)
      .catch(() => setError('erro ao carregar a issue (token/GitHub?)'))
  }, [number])

  async function runWithEngine() {
    try {
      const { run_id } = await dispatchEngineRefine(number)
      onOpenRun(run_id)
    } catch {
      setError('erro ao disparar o motor (engine ligado no stack do PoC?)')
    }
  }

  async function sendQuick() {
    const t = input.trim()
    if (!t || busy) return
    setBubbles((b) => [...b, { role: 'você', text: t }])
    transcript.current.push(['user', t])
    setInput('')
    setBusy(true)
    try {
      const step = await refineIssue(number, transcript.current)
      const reply = step.question ?? (step.draft ? `Rascunho: ${step.draft.title}` : '(sem resposta)')
      setBubbles((b) => [...b, { role: 'refiner', text: reply }])
      transcript.current.push(['assistant', reply])
    } catch {
      setBubbles((b) => [...b, { role: 'refiner', text: '(erro ao responder)' }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <Button variant="ghost" onClick={onBack}>
        ← issues
      </Button>

      <Card>
        <CardTitle>{detail ? `#${detail.number} ${detail.title}` : `Issue #${number}`}</CardTitle>
        {error && <p className="text-xs text-red-300">{error}</p>}
        {detail && (
          <>
            <span
              className={
                detail.dor.ready
                  ? 'text-xs font-bold text-green-300'
                  : 'text-xs font-bold text-accent'
              }
            >
              DoR: {detail.dor.ready ? 'pronta ✓' : `falta ${detail.dor.missing.join(', ')}`}
            </span>
            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-muted">
              {detail.body || '(sem corpo)'}
            </pre>
          </>
        )}
        <div className="mt-3">
          <Button variant="default" onClick={() => void runWithEngine()}>
            Refinar com o motor (lê o repo) ⚡
          </Button>
          <p className="mt-1 text-xs text-muted">
            O Claude Code lê o repositório (código, ADRs, arquivos citados) e propõe a issue
            fundamentada — você acompanha no feed ao vivo.
          </p>
        </div>
      </Card>

      <Card>
        <CardLabel>Conversa rápida — modelo cego, NÃO lê o repo (só pra ideias leves)</CardLabel>
        <div className="mb-2 flex max-h-[35vh] flex-col gap-2 overflow-y-auto">
          {bubbles.length === 0 && (
            <p className="text-xs text-muted">
              Pra issue técnica, use o motor acima. Esta caixa é um chat sem acesso ao código.
            </p>
          )}
          {bubbles.map((b, idx) => (
            <div key={idx} className="text-sm">
              <span className={b.role === 'você' ? 'text-accent' : 'text-sky-300'}>{b.role}:</span>{' '}
              <span className="whitespace-pre-wrap">{b.text}</span>
            </div>
          ))}
          {busy && <p className="text-xs text-muted">pensando…</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void sendQuick()
            }}
            placeholder="conversa rápida (sem repo)…"
            className="min-w-60 flex-1 rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
          />
          <Button variant="outline" disabled={busy} onClick={() => void sendQuick()}>
            enviar
          </Button>
        </div>
      </Card>
    </div>
  )
}
