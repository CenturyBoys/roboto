import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  cancelExecution,
  endExecution,
  getExecution,
  getPrDiff,
  getTerminal,
  interruptExecution,
  retryExecution,
  steerExecution,
} from '@/lib/api'
import type { ExecutionDetail, PrDiff, Terminal } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel, CardTitle } from './ui/card'
import { Feed } from './Feed'
import { StatePill } from './ui/state-pill'
import { Td, TableWrap, Th } from './ui/table'

export function ExecDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [data, setData] = useState<ExecutionDetail | null>(null)
  const [term, setTerm] = useState<Terminal | null>(null)
  const [diff, setDiff] = useState<PrDiff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [steerText, setSteerText] = useState('')
  const [steerMsg, setSteerMsg] = useState<string | null>(null)

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

  async function showDiff() {
    try {
      setDiff(await getPrDiff(id))
    } catch {
      /* ignore */
    }
  }

  async function steer() {
    const t = steerText.trim()
    if (!t) return
    try {
      await steerExecution(id, t)
      setSteerText('')
      setSteerMsg(data?.live ? 'enviado ✓' : 'sessão iniciada — o motor vai trabalhar ⚡')
      await load() // atualiza o "live" e o resto do detalhe
    } catch {
      setSteerMsg('erro ao enviar (motor interativo disponível?)')
    }
  }

  async function interrupt() {
    try {
      await interruptExecution(id)
      setSteerMsg('interrupção pedida')
    } catch (e) {
      setSteerMsg(e instanceof ApiError && e.status === 409 ? 'sessão não está viva' : 'erro')
    }
  }

  async function endSession() {
    try {
      await endExecution(id)
      setSteerMsg('sessão encerrada')
      await load()
    } catch (e) {
      setSteerMsg(e instanceof ApiError && e.status === 409 ? 'sessão não está viva' : 'erro')
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
        <Button onClick={() => void showDiff()}>Diff do PR</Button>
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
          <dt className="text-muted">custo</dt>
          <dd className="font-mono text-xs text-accent">
            {data.cost.tokens} tokens · ${data.cost.cost_usd.toFixed(4)}
          </dd>
        </dl>
      </Card>

      <Card>
        <CardLabel>
          Co-piloto — conversar com a sessão do motor{' '}
          <span className={data.live ? 'text-green-300' : 'text-muted'}>
            · {data.live ? 'sessão viva' : 'a 1ª mensagem inicia a sessão'}
          </span>
        </CardLabel>
        <div className="flex flex-wrap gap-2">
          <input
            value={steerText}
            onChange={(e) => setSteerText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void steer()
            }}
            placeholder={data.live ? 'responder/ajustar…' : 'inicie a conversa com o motor…'}
            className="min-w-60 flex-1 rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
          />
          <Button variant="default" onClick={() => void steer()}>
            enviar
          </Button>
          {data.live && (
            <>
              <Button variant="outline" onClick={() => void interrupt()}>
                interromper
              </Button>
              <Button variant="outline" onClick={() => void endSession()}>
                encerrar
              </Button>
            </>
          )}
        </div>
        {steerMsg && <p className="mt-1 text-xs text-muted">{steerMsg}</p>}
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

      <Feed id={id} />

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

      {diff && (
        <Card>
          <CardLabel>
            Diff do PR{' '}
            {diff.number != null && diff.url && (
              <a className="text-accent" href={diff.url} target="_blank" rel="noopener">
                ↗ #{diff.number}
              </a>
            )}
          </CardLabel>
          {diff.diff ? (
            <pre className="max-h-[60vh] overflow-auto rounded-lg border border-border bg-background p-3 text-xs leading-relaxed">
              {diff.diff.split('\n').map((line, idx) => (
                <div
                  key={idx}
                  className={
                    line.startsWith('+') && !line.startsWith('+++')
                      ? 'text-green-300'
                      : line.startsWith('-') && !line.startsWith('---')
                        ? 'text-red-300'
                        : line.startsWith('@@')
                          ? 'text-sky-300'
                          : 'text-muted'
                  }
                >
                  {line || ' '}
                </div>
              ))}
            </pre>
          ) : (
            <p className="text-muted">sem PR/diff ainda para esta execução</p>
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
