import { useCallback, useEffect, useState } from 'react'
import { cancelExecution, getExecution, getTerminal, retryExecution } from '@/lib/api'
import type { ExecutionDetail, Terminal } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel, CardTitle } from './ui/card'
import { StatePill } from './ui/state-pill'
import { Td, TableWrap, Th } from './ui/table'

export function ExecDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [data, setData] = useState<ExecutionDetail | null>(null)
  const [term, setTerm] = useState<Terminal | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await getExecution(id))
      setError(null)
    } catch {
      setError('erro ao carregar (token correto?)')
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  async function act(fn: (id: number) => Promise<unknown>) {
    try {
      await fn(id)
      await load()
    } catch {
      /* feedback silencioso: o estado recarrega */
    }
  }

  async function showTerminal() {
    try {
      setTerm(await getTerminal(id))
    } catch {
      /* ignore */
    }
  }

  if (error) return <p className="text-muted">{error}</p>
  if (!data) return <p className="text-muted">carregando…</p>
  const e = data.execution
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" onClick={onBack}>
          ← voltar
        </Button>
        <Button onClick={() => void showTerminal()}>Terminal</Button>
        <Button variant="outline" onClick={() => void act(retryExecution)}>
          Retentar
        </Button>
        <Button variant="outline" onClick={() => void act(cancelExecution)}>
          Cancelar
        </Button>
      </div>

      <Card>
        <CardTitle>Execução #{e.id}</CardTitle>
        <dl className="grid grid-cols-[120px_1fr] gap-y-1 text-sm">
          <Row k="repo" v={e.repo} />
          <Row k="issue" v={e.issue_id} />
          <Row k="agente" v={e.agent} />
          <dt className="text-muted">estado</dt>
          <dd>
            <StatePill state={e.state} />
          </dd>
          <Row k="tentativa" v={String(e.attempt)} />
          <Row k="criado" v={e.created_at} />
        </dl>
      </Card>

      <Card>
        <CardLabel>Sessões do motor (Claude Code)</CardLabel>
        {data.sessions.length ? (
          <TableWrap>
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="text-muted">
                <Th>id</Th>
                <Th>engine</Th>
                <Th>sessão nativa</Th>
                <Th>estado</Th>
              </tr>
            </thead>
            <tbody>
              {data.sessions.map((s) => (
                <tr key={s.id} className="border-t border-border">
                  <Td mono>{s.id}</Td>
                  <Td>{s.engine}</Td>
                  <Td mono>{s.native_session_id ?? '—'}</Td>
                  <Td>{s.state}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          </TableWrap>
        ) : (
          <p className="text-muted">nenhuma</p>
        )}
      </Card>

      <Card>
        <CardLabel>Conversa / interações</CardLabel>
        {data.interactions.length ? (
          <TableWrap>
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="text-muted">
                <Th>id</Th>
                <Th>tipo</Th>
                <Th>pergunta</Th>
                <Th>status</Th>
                <Th>resposta</Th>
              </tr>
            </thead>
            <tbody>
              {data.interactions.map((i) => (
                <tr key={i.id} className="border-t border-border">
                  <Td mono>{i.id}</Td>
                  <Td>{i.kind}</Td>
                  <Td>{i.prompt}</Td>
                  <Td>{i.status}</Td>
                  <Td>{i.answer ?? '—'}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          </TableWrap>
        ) : (
          <p className="text-muted">nenhuma</p>
        )}
      </Card>

      {term && (
        <Card>
          <CardLabel>
            Terminal da sessão{' '}
            {term.terminal_url && (
              <a className="text-accent" href={term.terminal_url} target="_blank" rel="noopener">
                ↗ nova aba
              </a>
            )}
          </CardLabel>
          {term.terminal_url ? (
            <iframe
              title="terminal da sessão"
              src={term.terminal_url}
              className="h-[70vh] w-full rounded-lg border border-border bg-black"
            />
          ) : (
            <p className="text-muted">{term.note ?? 'terminal off'}</p>
          )}
        </Card>
      )}
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-muted">{k}</dt>
      <dd className="font-mono text-xs">{v}</dd>
    </>
  )
}
