import { useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { answerInteraction, interruptExecution, steerExecution } from '@/lib/api'
import { collapseEvents } from '@/lib/collapse'
import { useEventStream } from '@/lib/use-event-stream'
import type { Interaction } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel } from './ui/card'
import { ToolActivity } from './ui/tool-activity'

// "Conversar com o agente" (#274): UMA linha do tempo por execução — feed ao vivo (mensagens +
// tool-calls) + cartão de APROVAÇÃO inline (pendências do gate, #265/#267) + caixa de steer +
// interromper. Substitui a tabela de interações crua + o feed separado: tudo no mesmo lugar, na ordem.

// palavras que o backend trata como "aprovar" (o resto = recusar; o texto vira o motivo).
const _APPROVE = new Set(['allow', 'aprovar', 'approve', 'sim', 'yes', 'ok'])

// o prompt de uma aprovação é o canonical_action: "<tool>\n<json dos args>". Separa p/ exibir bonito.
export function parseAction(prompt: string): { tool: string; args: string } {
  const nl = prompt.indexOf('\n')
  if (nl === -1) return { tool: prompt, args: '' }
  const tool = prompt.slice(0, nl)
  const raw = prompt.slice(nl + 1)
  try {
    return { tool, args: JSON.stringify(JSON.parse(raw), null, 2) }
  } catch {
    return { tool, args: raw }
  }
}

export function Timeline({
  id,
  interactions,
  live,
  onChange,
}: {
  id: number
  interactions: Interaction[]
  live: boolean
  onChange: () => void
}) {
  const events = useEventStream(id)
  const items = collapseEvents(events, true)
  const pending = interactions.filter((i) => i.status === 'pending')
  const [steer, setSteer] = useState('')
  const [reason, setReason] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [sending, setSending] = useState(false)

  async function decide(i: Interaction, answer: string) {
    if (!answer.trim()) return
    setBusy(i.id)
    try {
      await answerInteraction(i.id, answer)
      onChange()
    } finally {
      setBusy(null)
    }
  }

  async function sendSteer() {
    const text = steer.trim()
    if (!text) return
    setSending(true)
    try {
      await steerExecution(id, text)
      setSteer('')
    } catch {
      /* 409 = sessão não está viva; feedback silencioso */
    } finally {
      setSending(false)
    }
  }

  async function stop() {
    try {
      await interruptExecution(id)
    } catch {
      /* sem sessão viva: ignora */
    }
    onChange()
  }

  return (
    <Card data-testid="timeline">
      <div className="flex items-center gap-2">
        <CardLabel className="!m-0 flex-1">
          Conversa com o agente{' '}
          {live ? (
            <span className="text-green-300">· ao vivo</span>
          ) : (
            <span className="text-muted">· sessão parada</span>
          )}
        </CardLabel>
        {live && (
          <Button variant="outline" size="sm" data-testid="timeline-interrupt" onClick={() => void stop()}>
            ⛔ interromper
          </Button>
        )}
      </div>

      <div className="mt-2 flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
        {items.length === 0 && pending.length === 0 && (
          <p className="text-muted">sem eventos ainda…</p>
        )}
        {items.map((it, idx) =>
          it.type === 'tools' ? (
            <ToolActivity key={idx} tools={it.tools} />
          ) : it.kind === 'user' ? (
            <div key={idx} className="self-end rounded-lg bg-accent/15 px-3 py-1.5 text-sm">
              <span className="text-accent">você:</span> {it.text}
            </div>
          ) : (
            <div key={idx} className="md rounded-lg border border-border bg-background/40 p-3 text-sm">
              <Markdown remarkPlugins={[remarkGfm]}>{it.text}</Markdown>
            </div>
          ),
        )}

        {pending.map((i) => {
          const isApproval =
            i.kind === 'approval' || i.options.some((o) => _APPROVE.has(o.toLowerCase()))
          const { tool, args } = parseAction(i.prompt)
          if (!isApproval && i.options.length === 0) {
            return (
              <div key={i.id} data-testid={`interaction-${i.id}`} className="rounded-lg border border-accent/60 bg-accent/5 p-3 text-sm">
                <p className="mb-2">{i.prompt}</p>
                <div className="flex gap-2">
                  <input
                    value={reason[i.id] ?? ''}
                    onChange={(e) => setReason((r) => ({ ...r, [i.id]: e.target.value }))}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void decide(i, reason[i.id] ?? '')
                    }}
                    placeholder="sua resposta…"
                    className="min-w-48 flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-accent"
                  />
                  <Button size="sm" variant="default" disabled={busy === i.id} onClick={() => void decide(i, reason[i.id] ?? '')}>
                    responder
                  </Button>
                </div>
              </div>
            )
          }
          return (
            <div key={i.id} data-testid={`approval-${i.id}`} className="rounded-lg border border-accent/60 bg-accent/5 p-3 text-sm">
              <div className="mb-1 flex items-center gap-2">
                <span className="rounded bg-accent/20 px-1.5 py-0.5 text-xs font-bold text-accent">
                  ⏳ aprovação
                </span>
                <span className="font-mono text-xs font-bold">{tool}</span>
              </div>
              {args && (
                <pre className="mb-2 max-h-40 overflow-auto rounded border border-border bg-background/60 p-2 text-xs">
                  {args}
                </pre>
              )}
              <div className="flex flex-wrap items-center gap-2">
                {(i.options.length ? i.options : ['allow', 'deny']).map((opt) => {
                  const approve = _APPROVE.has(opt.toLowerCase())
                  return (
                    <Button
                      key={opt}
                      size="sm"
                      variant={approve ? 'default' : 'outline'}
                      disabled={busy === i.id}
                      onClick={() => void decide(i, approve ? opt : reason[i.id]?.trim() || opt)}
                    >
                      {approve ? '✓ aprovar' : '✕ recusar'}
                    </Button>
                  )
                })}
                <input
                  value={reason[i.id] ?? ''}
                  onChange={(e) => setReason((r) => ({ ...r, [i.id]: e.target.value }))}
                  placeholder="motivo da recusa (opcional)…"
                  className="min-w-48 flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-accent"
                />
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-2 flex items-center gap-2 border-t border-border pt-2">
        <input
          data-testid="timeline-steer"
          value={steer}
          onChange={(e) => setSteer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void sendSteer()
          }}
          placeholder={live ? 'orienta o agente (steer)…' : 'envie uma mensagem…'}
          className="flex-1 rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
        />
        <Button variant="default" disabled={sending} onClick={() => void sendSteer()}>
          {sending ? '…' : 'Enviar'}
        </Button>
      </div>
    </Card>
  )
}
