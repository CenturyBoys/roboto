import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { collapseEvents } from '@/lib/collapse'
import { useEventStream } from '@/lib/use-event-stream'
import { Card, CardLabel } from './ui/card'
import { ToolActivity } from './ui/tool-activity'

// Feed legível do motor (mensagens em MARKDOWN + tool-calls), ao vivo via SSE. A proposta de issue
// vem em markdown (títulos/listas/checkboxes) — renderizamos de verdade pra ficar legível.
export function Feed({ id }: { id: number }) {
  const events = useEventStream(id)
  const items = collapseEvents(events, true) // resumido: status + resultado (sem spam do stream)
  return (
    <Card>
      <CardLabel>Feed — resultado e status (resumido)</CardLabel>
      {items.length === 0 ? (
        <p className="text-muted">sem eventos ainda…</p>
      ) : (
        <div className="flex max-h-[65vh] flex-col gap-2 overflow-y-auto">
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
        </div>
      )}
    </Card>
  )
}
