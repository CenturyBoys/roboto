import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  applyBreakdown,
  deleteBreakdownDraft,
  getBreakdownDraft,
  proposeBreakdown,
  saveBreakdownDraft,
} from '@/lib/api'
import type { BreakdownItem, CreatedSubIssue } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel } from './ui/card'
import { useToast } from './ui/toast'

// Breakdown de épico (#203). Fluxo: PROPOR (o refiner destrincha, nada é criado) → o humano revisa/
// edita a lista → CRIAR (materializa as sub-issues encadeadas por dependência, linka no épico).
// O rascunho editado é salvo no BACKEND (durável): sobrevive a F5 e troca de dispositivo.
export function BreakdownPanel({ number }: { number: number }) {
  const [items, setItems] = useState<BreakdownItem[] | null>(null)
  const [question, setQuestion] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [created, setCreated] = useState<CreatedSubIssue[] | null>(null)
  const [busy, setBusy] = useState<null | 'propose' | 'apply'>(null)
  const toast = useToast()
  const hydrated = useRef(false) // evita re-salvar o rascunho que acabou de ser carregado

  // ao abrir: restaura o rascunho salvo (se houver) — é isso que sobrevive ao F5
  useEffect(() => {
    getBreakdownDraft(number)
      .then((d) => {
        if (d.items && d.items.length > 0) setItems(d.items)
      })
      .catch(() => {})
      .finally(() => {
        hydrated.current = true
      })
  }, [number])

  // autosave: toda edição da lista persiste no backend (não salva o estado inicial nem o "limpo")
  useEffect(() => {
    if (!hydrated.current || items === null) return
    void saveBreakdownDraft(number, items).catch(() => {})
  }, [number, items])

  async function propose() {
    if (busy) return
    setBusy('propose')
    setCreated(null)
    try {
      const step = await proposeBreakdown(number, [])
      setQuestion(step.question)
      setItems(step.items)
      setWarnings(step.warnings ?? [])
      if (step.question) toast('O refiner tem uma dúvida — veja abaixo.')
    } catch (e) {
      if (e instanceof ApiError && e.status === 409)
        toast('Esta issue não parece um épico (sem sinais para destrinchar).', 'error')
      else toast('Erro ao propor o breakdown (motor/token?).', 'error')
    } finally {
      setBusy(null)
    }
  }

  async function create() {
    if (busy || !items?.length) return
    setBusy('apply')
    try {
      const { created } = await applyBreakdown(number, items)
      setCreated(created)
      setItems(null)
      setWarnings([])
      toast(`${created.length} sub-issue(s) criada(s) e encadeada(s) ⚡`, 'success')
    } catch {
      toast('Erro ao criar as sub-issues.', 'error')
    } finally {
      setBusy(null)
    }
  }

  async function discard() {
    if (busy) return
    await deleteBreakdownDraft(number).catch(() => {})
    setItems(null)
    setQuestion(null)
    setCreated(null)
    setWarnings([])
    toast('Rascunho descartado.')
  }

  function patch(idx: number, next: Partial<BreakdownItem>) {
    setItems((cur) => cur?.map((it, i) => (i === idx ? { ...it, ...next } : it)) ?? cur)
  }
  function remove(idx: number) {
    setItems((cur) => cur?.filter((_, i) => i !== idx) ?? cur)
  }

  return (
    <Card>
      <CardLabel>Destrinchar épico → sub-issues (esqueleto, encadeadas por dependência)</CardLabel>
      <div className="flex flex-wrap gap-2">
        <Button variant="default" disabled={busy !== null} onClick={() => void propose()}>
          {busy === 'propose' ? 'destrinchando…' : 'Destrinchar épico'}
        </Button>
        {items && items.length > 0 && (
          <>
            <Button variant="outline" disabled={busy !== null} onClick={() => void create()}>
              {busy === 'apply' ? 'criando…' : `Criar ${items.length} sub-issue(s)`}
            </Button>
            <Button variant="ghost" disabled={busy !== null} onClick={() => void discard()}>
              descartar rascunho
            </Button>
          </>
        )}
      </div>

      {question && (
        <p className="mt-2 text-sm text-accent">
          <b>Pergunta do refiner:</b> {question}
        </p>
      )}

      {warnings.length > 0 && (
        <div className="mt-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2">
          <p className="text-xs font-semibold text-amber-600">
            Cobertura do destrinchamento — revise antes de criar:
          </p>
          <ul className="ml-4 mt-1 list-disc text-xs text-amber-700">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {items && items.length > 0 && (
        <ol className="mt-3 space-y-2">
          {items.map((it, idx) => (
            <li key={idx} className="rounded-lg border border-border p-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted">{idx + 1}.</span>
                <input
                  value={it.title}
                  onChange={(e) => patch(idx, { title: e.target.value })}
                  className="min-w-40 flex-1 rounded border border-border bg-background px-2 py-1 text-sm outline-none focus:border-accent"
                />
                <button
                  type="button"
                  onClick={() => remove(idx)}
                  className="text-xs text-red-300 hover:underline"
                >
                  remover
                </button>
              </div>
              {it.points.length > 0 && (
                <ul className="ml-6 mt-1 list-disc text-xs text-muted">
                  {it.points.map((p, j) => (
                    <li key={j}>{p}</li>
                  ))}
                </ul>
              )}
              {idx > 0 && (
                <label className="ml-6 mt-1 flex items-center gap-1 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={it.depends_on_prev}
                    onChange={(e) => patch(idx, { depends_on_prev: e.target.checked })}
                  />
                  depende da anterior (#{idx} → espera ela fechar)
                </label>
              )}
            </li>
          ))}
        </ol>
      )}

      {created && created.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {created.map((c) => (
            <li key={c.number}>
              <a href={c.url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">
                #{c.number}
              </a>{' '}
              — {c.title}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-2 text-xs text-muted">
        <b>Destrinchar</b> só propõe (nada é criado). Revise/edite e clique em <b>Criar</b> — cada
        sub-issue nasce com <i>Depende de #N</i> e é refinada a fundo 1-a-1 quando for a vez.
      </p>
    </Card>
  )
}
