import * as React from 'react'
import { cn } from '@/lib/utils'

// Métrica grande, contexto pequeno (Refactoring UI): o número ancora, o rótulo/hint é secundário.
export function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string
  value: React.ReactNode
  hint?: string
  accent?: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={cn('mt-0.5 text-2xl font-bold tabular-nums', accent && 'text-accent')}>
        {value}
      </div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  )
}
