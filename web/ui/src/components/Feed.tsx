import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useEventStream } from '@/lib/use-event-stream'
import { Card, CardLabel } from './ui/card'

// Feed legível do motor (mensagens em MARKDOWN + tool-calls), ao vivo via SSE. A proposta de issue
// vem em markdown (títulos/listas/checkboxes) — renderizamos de verdade pra ficar legível.
export function Feed({ id }: { id: number }) {
  const events = useEventStream(id)
  return (
    <Card>
      <CardLabel>Feed ao vivo — o que o motor está fazendo</CardLabel>
      {events.length === 0 ? (
        <p className="text-muted">sem eventos ainda…</p>
      ) : (
        <div className="flex max-h-[65vh] flex-col gap-2 overflow-y-auto">
          {events.map((e) =>
            e.kind === 'tool_call' ? (
              <div key={e.id} className="font-mono text-xs text-sky-300">
                🔧 {e.tool}
              </div>
            ) : e.kind === 'user' ? (
              <div key={e.id} className="self-end rounded-lg bg-accent/15 px-3 py-1.5 text-sm">
                <span className="text-accent">você:</span> {e.text}
              </div>
            ) : (
              <div key={e.id} className="md rounded-lg border border-border bg-background/40 p-3 text-sm">
                <Markdown remarkPlugins={[remarkGfm]}>{e.text}</Markdown>
              </div>
            ),
          )}
        </div>
      )}
    </Card>
  )
}
