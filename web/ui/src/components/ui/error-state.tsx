import { Button } from './button'

// Erro que RECUPERA (regra 5 / Nielsen #9): mensagem humana + "tentar de novo".
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-red-900/60 bg-surface px-6 py-10 text-center">
      <span className="text-2xl">⚠️</span>
      <p className="max-w-md text-sm text-red-200">{message}</p>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          Tentar de novo
        </Button>
      )}
    </div>
  )
}
