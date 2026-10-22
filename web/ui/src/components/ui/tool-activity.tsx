// Pílula de status: resume as ações do motor (tool-calls) em vez de uma linha por ação.
export function ToolActivity({ tools }: { tools: string[] }) {
  const counts: Record<string, number> = {}
  for (const t of tools) counts[t] = (counts[t] ?? 0) + 1
  const summary = Object.entries(counts)
    .map(([t, n]) => (n > 1 ? `${t}×${n}` : t))
    .join(', ')
  return (
    <div className="self-center rounded-full border border-border px-2.5 py-0.5 font-mono text-[11px] text-muted">
      🔧 {tools.length} {tools.length === 1 ? 'ação' : 'ações'} · {summary}
    </div>
  )
}
