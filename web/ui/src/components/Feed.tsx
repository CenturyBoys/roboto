import { useEventStream } from '@/lib/use-event-stream'
import { Card, CardLabel } from './ui/card'

// Feed legível do motor (mensagens + tool-calls), ao vivo via SSE. Alternativa limpa ao terminal cru.
export function Feed({ id }: { id: number }) {
  const events = useEventStream(id)
  return (
    <Card>
      <CardLabel>Feed ao vivo — o que o motor está fazendo</CardLabel>
      {events.length === 0 ? (
        <p className="text-muted">sem eventos ainda…</p>
      ) : (
        <div className="flex max-h-[50vh] flex-col gap-1 overflow-y-auto font-mono text-xs">
          {events.map((e) => (
            <div key={e.id} className={e.kind === 'tool_call' ? 'text-sky-300' : 'text-foreground'}>
              {e.kind === 'tool_call' ? `🔧 ${e.tool}` : e.text}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
