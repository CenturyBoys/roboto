import * as React from 'react'
import { cn } from '@/lib/utils'

// Feedback de ação (Nielsen #1 / regra 4): toda ação dispara um toast visível e auto-some.
type Variant = 'default' | 'success' | 'error'
type Toast = { id: number; msg: string; variant: Variant }

const ToastCtx = React.createContext<(msg: string, variant?: Variant) => void>(() => {})
export const useToast = () => React.useContext(ToastCtx)

let _id = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([])
  const toast = React.useCallback((msg: string, variant: Variant = 'default') => {
    const id = ++_id
    setToasts((t) => [...t, { id, msg, variant }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000)
  }, [])
  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              'pointer-events-auto max-w-sm rounded-lg border bg-surface px-3 py-2 text-sm shadow-lg',
              t.variant === 'success' && 'border-green-800 text-green-200',
              t.variant === 'error' && 'border-red-800 text-red-200',
              t.variant === 'default' && 'border-border text-foreground',
            )}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
