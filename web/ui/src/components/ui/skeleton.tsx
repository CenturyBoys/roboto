import { cn } from '@/lib/utils'

// Carregando que ESPELHA o layout (regra 5): skeleton, não spinner cego.
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-border/60', className)} />
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-col gap-3">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4">
            {Array.from({ length: cols }).map((_, c) => (
              <Skeleton key={c} className={cn('h-4', c === 0 ? 'w-12' : 'flex-1')} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
