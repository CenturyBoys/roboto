import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { endExecution, interruptExecution, steerExecution } from '@/lib/api'
import { useEventStream } from '@/lib/use-event-stream'
import { Button } from './ui/button'

// Chat estilo mensageiro com a sessão viva do motor (trilha O): suas mensagens de um lado, as do
// motor do outro, tool-calls como notas. A 1ª mensagem inicia a sessão; as próximas fazem steer.
export function Chat({ id, onClose }: { id: number; onClose: () => void }) {
  const events = useEventStream(id)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  async function send() {
    const t = input.trim()
    if (!t || busy) return
    setBusy(true)
    try {
      await steerExecution(id, t)
      setInput('')
    } catch {
      /* 409 se o run está ocupado pelo ciclo automático; silencioso */
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex flex-col bg-background">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <span className="text-lg">⚡</span>
        <div className="flex-1 text-sm font-bold">
          Chat com o motor <span className="font-normal text-muted">· execução #{id}</span>
        </div>
        <Button size="sm" variant="outline" onClick={() => void interruptExecution(id).catch(() => {})}>
          interromper
        </Button>
        <Button size="sm" variant="outline" onClick={() => void endExecution(id).catch(() => {})}>
          encerrar
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>
          ✕
        </Button>
      </header>

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-2 overflow-y-auto p-4">
        {events.length === 0 && (
          <p className="mt-6 text-center text-xs text-muted">
            Escreva abaixo pra iniciar — o motor lê o repo e responde aqui.
          </p>
        )}
        {events.map((e) =>
          e.kind === 'tool_call' ? (
            <div key={e.id} className="self-center font-mono text-[11px] text-muted">
              🔧 {e.tool}
            </div>
          ) : e.kind === 'user' ? (
            <div
              key={e.id}
              className="max-w-[80%] self-end whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent px-3 py-2 text-sm text-black"
            >
              {e.text}
            </div>
          ) : (
            <div
              key={e.id}
              className="md max-w-[85%] self-start rounded-2xl rounded-bl-sm border border-border bg-surface px-3 py-2 text-sm"
            >
              <Markdown remarkPlugins={[remarkGfm]}>{e.text}</Markdown>
            </div>
          ),
        )}
        <div ref={bottom} />
      </div>

      <div className="mx-auto flex w-full max-w-3xl gap-2 border-t border-border p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send()
          }}
          placeholder="mensagem…"
          className="flex-1 rounded-full border border-border bg-surface px-4 py-2 text-sm outline-none focus:border-accent"
        />
        <Button variant="default" disabled={busy} onClick={() => void send()}>
          enviar
        </Button>
      </div>
    </div>
  )
}
