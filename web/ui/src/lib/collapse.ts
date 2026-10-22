import type { FeedEvent } from '@/types'

// Transforma o stream cru em itens de exibição, controlando o "spam".
// - detalhado: agrupa só tool-calls CONSECUTIVAS; mostra todas as mensagens.
// - resumido (padrão): entre mensagens do humano, condensa o "burst" do motor em UMA pílula de
//   status (todas as ações) + SÓ a ÚLTIMA mensagem do motor (o resultado) — esconde a narração.
export type DisplayItem =
  | { type: 'msg'; kind: 'message' | 'user'; text: string }
  | { type: 'tools'; tools: string[] }

export function collapseEvents(events: FeedEvent[], summary = true): DisplayItem[] {
  const items: DisplayItem[] = []
  if (!summary) {
    for (const e of events) {
      if (e.kind === 'tool_call') {
        const last = items[items.length - 1]
        if (last && last.type === 'tools') last.tools.push(e.tool || '?')
        else items.push({ type: 'tools', tools: [e.tool || '?'] })
      } else {
        items.push({ type: 'msg', kind: e.kind, text: e.text })
      }
    }
    return items
  }
  // resumido: por "burst" do motor entre mensagens do humano
  let tools: string[] = []
  let lastMsg: string | null = null
  const flush = () => {
    if (tools.length) {
      items.push({ type: 'tools', tools })
      tools = []
    }
    if (lastMsg !== null) {
      items.push({ type: 'msg', kind: 'message', text: lastMsg })
      lastMsg = null
    }
  }
  for (const e of events) {
    if (e.kind === 'user') {
      flush()
      items.push({ type: 'msg', kind: 'user', text: e.text })
    } else if (e.kind === 'tool_call') {
      tools.push(e.tool || '?')
    } else {
      lastMsg = e.text // mantém só a última mensagem do motor no burst (o resultado)
    }
  }
  flush()
  return items
}
