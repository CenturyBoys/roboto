import { cn } from '@/lib/utils'

// Cores por estado do run (mesma semântica do viewer legado / máquina de estados do orquestrador).
const STYLES: Record<string, string> = {
  running: 'text-sky-300 border-sky-800',
  verifying: 'text-sky-300 border-sky-800',
  waiting: 'text-accent border-yellow-800',
  done: 'text-green-300 border-green-800',
  failed: 'text-red-300 border-red-800',
  abandoned: 'text-red-300 border-red-800',
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
