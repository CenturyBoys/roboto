import { useEffect, useState } from 'react'
import { getToken } from '@/lib/api'
import type { FeedEvent } from '@/types'

// Feed ao vivo (Fatia 2): consome o SSE `/executions/:id/events` via fetch (EventSource não manda
// Authorization). Faz o parse de blocos "data: {...}\n\n" e acumula os eventos; aborta no unmount.
export function useEventStream(executionId: number): FeedEvent[] {
  const [events, setEvents] = useState<FeedEvent[]>([])

  useEffect(() => {
    const ctrl = new AbortController()
    setEvents([])
    void (async () => {
      try {
        const res = await fetch(`/executions/${executionId}/events`, {
          headers: { Authorization: `Bearer ${getToken()}` },
          signal: ctrl.signal,
        })
        if (!res.body) return
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const chunks = buf.split('\n\n')
          buf = chunks.pop() ?? '' // resto incompleto fica pro próximo read
          for (const chunk of chunks) {
            const line = chunk.split('\n').find((l) => l.startsWith('data: '))
            if (!line) continue // heartbeat (": ping") é ignorado
            try {
              const ev = JSON.parse(line.slice(6)) as FeedEvent
              setEvents((prev) => [...prev, ev])
            } catch {
              /* linha malformada: ignora */
            }
          }
        }
      } catch {
        /* abortado no unmount ou erro de rede: ok */
      }
    })()
    return () => ctrl.abort()
  }, [executionId])

  return events
}
