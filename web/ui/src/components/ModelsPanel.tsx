import { useEffect, useState } from 'react'
import { getModels, saveModels } from '@/lib/api'
import type { StageModel } from '@/types'
import { Button } from './ui/button'
import { Card, CardTitle } from './ui/card'
import { useToast } from './ui/toast'

// Switcher de modelo por ETAPA (trilha I): troca sem restart. Edita o override de cada etapa,
// aplica ao vivo (persiste no app_config). Em branco = volta ao default. JEV só vale no restart.
export function ModelsPanel() {
  const [stages, setStages] = useState<StageModel[] | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  async function load() {
    try {
      const { stages } = await getModels()
      setStages(stages)
      setDraft(Object.fromEntries(stages.map((s) => [s.key, s.value])))
    } catch {
      toast('Erro ao carregar os modelos (token?).', 'error')
    }
  }
  useEffect(() => {
    void load()
  }, [])

  const dirty = stages?.some((s) => (draft[s.key] ?? '') !== s.value) ?? false

  async function save() {
    if (!stages) return
    const updates: Record<string, string> = {}
    for (const s of stages) {
      const v = draft[s.key] ?? ''
      if (v !== s.value) updates[s.key] = v
    }
    if (Object.keys(updates).length === 0) return
    setBusy(true)
    try {
      const res = await saveModels(updates)
      setStages(res.stages)
      setDraft(Object.fromEntries(res.stages.map((s) => [s.key, s.value])))
      const restart = Object.keys(updates).some(
        (k) => res.stages.find((s) => s.key === k)?.live === false,
      )
      toast(restart ? 'Aplicado — JEV só vale no próximo restart.' : 'Modelos aplicados ao vivo ⚡', 'success')
    } catch {
      toast('Erro ao aplicar os modelos.', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardTitle>Modelos por etapa — troca sem restart</CardTitle>
      <p className="mb-3 text-sm text-muted">
        Cada etapa do pipeline usa um modelo. Edite e <b>aplique ao vivo</b> (persiste no banco). Em
        branco = volta ao default. <span className="text-accent">JEV</span> só vale no próximo restart.
      </p>

      {stages === null && <p className="text-muted">carregando…</p>}

      <div className="flex flex-col gap-3">
        {stages?.map((s) => (
          <div key={s.key} className="rounded-lg border border-border p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{s.label}</span>
              <span className={s.live ? 'text-xs text-green-300' : 'text-xs text-accent'}>
                {s.live ? 'ao vivo' : 'restart'}
              </span>
            </div>
            <input
              value={draft[s.key] ?? ''}
              placeholder={`default: ${s.default || '(do motor)'}`}
              onChange={(e) => setDraft((d) => ({ ...d, [s.key]: e.target.value }))}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1 font-mono text-xs outline-none focus:border-accent"
            />
            <div className="mt-1 text-xs text-muted">
              efetivo: <span className="font-mono text-foreground">{s.effective}</span>
              <span className="ml-2 font-mono opacity-60">{s.key}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4">
        <Button variant="default" disabled={busy || !dirty} onClick={() => void save()}>
          {busy ? 'aplicando…' : 'Aplicar ao vivo'}
        </Button>
      </div>
    </Card>
  )
}
