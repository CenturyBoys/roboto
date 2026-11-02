import * as React from 'react'

// Vazio que ORIENTA (regra 5): diz por que não há dado + oferece a próxima ação.
export function EmptyState({
  icon = '∅',
  title,
  hint,
  action,
}: {
  icon?: string
  title: string
  hint?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface/40 px-6 py-12 text-center">
      <span className="text-3xl opacity-70">{icon}</span>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {hint && <p className="max-w-sm text-xs text-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
