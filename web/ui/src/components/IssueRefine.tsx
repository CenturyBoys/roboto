import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, dispatchEngineRefine, getIssue, refineIssue } from '@/lib/api'
import type { IssueDetail, RefineStep } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel, CardTitle } from './ui/card'

type Bubble = { role: 'você' | 'refiner'; text: string }

// Conversa de refino sobre uma issue (Fatia 6): puxa o corpo + DoR, e conversa com o refiner
// (OpenRouter) até ele propor um rascunho. Aplicar na issue (GitHub) é o próximo incremento.
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
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  const [draft, setDraft] = useState<RefineStep | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const transcript = useRef<[string, string][]>([])

  const apply = useCallback((step: RefineStep) => {
    if (step.draft) {
      setDraft(step)
      transcript.current.push(['assistant', `PROPOSTA: ${step.draft.title}`])
    } else if (step.question) {
      setBubbles((b) => [...b, { role: 'refiner', text: step.question as string }])
      transcript.current.push(['assistant', step.question])
    }
  }, [])

  // ao abrir: carrega a issue e pede a 1ª pergunta do refiner (semeando o contexto da issue).
  useEffect(() => {
    let alive = true
    setBusy(true)
    getIssue(number)
      .then(async (d) => {
        if (!alive) return
        setDetail(d)
        const seed = `Quero refinar a issue #${d.number}: "${d.title}".\n\nCorpo atual:\n${d.body}`
        transcript.current = [['user', seed]]
        try {
          apply(await refineIssue(number, transcript.current))
        } catch (e) {
          setError(
            e instanceof ApiError && e.status === 409
              ? 'modelo (OpenRouter) não configurado'
              : 'erro ao falar com o refiner',
          )
        }
      })
      .catch(() => setError('erro ao carregar a issue (token/GitHub?)'))
      .finally(() => alive && setBusy(false))
    return () => {
      alive = false
    }
  }, [number, apply])

  async function send() {
    const t = input.trim()
    if (!t || busy) return
    setBubbles((b) => [...b, { role: 'você', text: t }])
    transcript.current.push(['user', t])
    setInput('')
    setBusy(true)
    setDraft(null)
    try {
      apply(await refineIssue(number, transcript.current))
    } catch {
      setError('erro ao falar com o refiner')
    } finally {
      setBusy(false)
    }
  }

  async function runWithEngine() {
    try {
      const { run_id } = await dispatchEngineRefine(number)
      onOpenRun(run_id)
    } catch {
      setError('erro ao disparar o motor (engine ligado?)')
    }
  }

  return (
    <div className="space-y-3">
      <Button variant="ghost" onClick={onBack}>
        ← issues
      </Button>

      <Card>
        <CardTitle>
          {detail ? `#${detail.number} ${detail.title}` : `Issue #${number}`}
        </CardTitle>
        <div className="mb-2">
          <Button variant="default" onClick={() => void runWithEngine()}>
            Refinar com o motor (lê o repo) ⚡
          </Button>
        </div>
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
      </Card>

      <Card>
        <CardLabel>Conversa de refino</CardLabel>
        <div className="mb-2 flex max-h-[45vh] flex-col gap-2 overflow-y-auto">
          {bubbles.map((b, idx) => (
            <div key={idx} className="text-sm">
              <span className={b.role === 'você' ? 'text-accent' : 'text-sky-300'}>{b.role}:</span>{' '}
              <span className="whitespace-pre-wrap">{b.text}</span>
            </div>
          ))}
          {busy && <p className="text-xs text-muted">refiner pensando…</p>}
          {error && <p className="text-xs text-red-300">{error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void send()
            }}
            placeholder="responda ao refiner…"
            className="min-w-60 flex-1 rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
          />
          <Button variant="default" disabled={busy} onClick={() => void send()}>
            enviar
          </Button>
        </div>
      </Card>

      {draft?.draft && (
        <Card>
          <CardLabel>
            Rascunho proposto{' '}
            {draft.dor && (
              <span className={draft.dor.ready ? 'text-green-300' : 'text-accent'}>
                · DoR {draft.dor.ready ? 'pronta ✓' : 'incompleta'}
              </span>
            )}
          </CardLabel>
          <p className="text-sm font-semibold">{draft.draft.title}</p>
          <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap text-xs">
            {draft.draft.body}
          </pre>
          <p className="mt-2 text-xs text-muted">
            (aplicar na issue do GitHub é o próximo incremento)
          </p>
        </Card>
      )}
    </div>
  )
}
