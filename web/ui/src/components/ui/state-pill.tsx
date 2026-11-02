import { cn } from '@/lib/utils'

// Cores por estado do run (mesma semântica do viewer legado / máquina de estados do orquestrador).
// Fundo tênue por estado = a pill ANCORA a linha (regra 1). `abandoned` é NEUTRO (cinza), distinto
// de `failed` (vermelho) — não colidir dois significados na mesma cor (regra 6).
const STYLES: Record<string, string> = {
  running: 'text-sky-300 border-sky-800 bg-sky-950/40',
  verifying: 'text-sky-300 border-sky-800 bg-sky-950/40',
  waiting: 'text-accent border-yellow-800 bg-yellow-950/30',
  done: 'text-green-300 border-green-800 bg-green-950/30',
  failed: 'text-red-300 border-red-800 bg-red-950/30',
  abandoned: 'text-muted border-border bg-surface',
  queued: 'text-muted border-border',
}

export function StatePill({ state }: { state: string }) {
  return (
    <span
      className={cn(
        'inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-bold',
        STYLES[state] ?? 'text-muted border-border',
      )}
    >
      {state}
    </span>
  )
}
