import { useCallback, useEffect, useState } from 'react'
import {
  applyProposal,
  cancelExecution,
  dispatchImplement,
  getExecution,
  getPrDiff,
  getProposal,
  getTerminal,
  retryExecution,
  revertExecution,
} from '@/lib/api'
import type { ExecutionDetail, PrDiff, Risk, Terminal, ToolUsage } from '@/types'
import { Button } from './ui/button'
import { Card, CardLabel, CardTitle } from './ui/card'
import { Chat } from './Chat'
import { Feed } from './Feed'
import { StatePill } from './ui/state-pill'
import { Td, TableWrap, Th } from './ui/table'

export function ExecDetail({
  id,
  onBack,
  onOpenRun,
}: {
  id: number
  onBack: () => void
  onOpenRun: (runId: number) => void
}) {
  const [data, setData] = useState<ExecutionDetail | null>(null)
  const [term, setTerm] = useState<Terminal | null>(null)
  const [diff, setDiff] = useState<PrDiff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [applyBody, setApplyBody] = useState<string | null>(null) // null = overlay fechado
  const [applyMsg, setApplyMsg] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)

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
    // auto-refresh: o detalhe acompanha o run AO VIVO (estado/custo/risco), não só no F5.
    // Para de pollar quando o run chega num estado terminal (done/failed/abandoned).
    const t = setInterval(() => {
      const st = data?.execution.state
      if (st === 'done' || st === 'failed' || st === 'abandoned') return
      void load()
    }, 4000)
    return () => clearInterval(t)
  }, [load, data?.execution.state])

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

  async function openApply() {
    setApplyMsg(null)
    try {
      const p = await getProposal(id)
      setApplyBody(p.body || '') // pré-preenche com o rascunho; o humano edita antes de aplicar
    } catch {
      setApplyMsg('erro ao buscar a proposta')
    }
  }

  async function doApply() {
    if (applyBody === null || !applyBody.trim()) return
    setApplying(true)
    try {
      const r = await applyProposal(id, applyBody)
      setApplyMsg(`issue #${r.number} atualizada no GitHub ✓`)
      setApplyBody(null)
    } catch {
      setApplyMsg('erro ao aplicar na issue')
    } finally {
      setApplying(false)
    }
  }

  // H (recuperação): reverte o PR desta execução (abre um PR de revert) e reabre a issue. Ação
  // impactante -> confirma antes. Merge do revert continua humano.
  async function doRevert() {
    if (!window.confirm('Reverter este PR? Abre um PR de revert e reabre a issue (merge é humano).'))
      return
    setApplyMsg(null)
    try {
      const r = await revertExecution(id)
      setApplyMsg(`revert enfileirado (execução #${r.run_id}) — revertendo o PR #${r.reverting_pr}…`)
      onOpenRun(r.run_id)
    } catch {
      setApplyMsg('não deu p/ reverter — esta execução tem um PR aberto?')
    }
  }

  // Executar a issue daqui mesmo (refinar→aplicar→implementar numa tela só). Gate de DoR + guard de
  // impl ativo são no servidor; aqui só reporta. Abre a nova execução p/ acompanhar.
  async function doImplement(issueId: string) {
    setApplyMsg(null)
    try {
      const r = await dispatchImplement(Number(issueId))
      setApplyMsg(`execução #${r.run_id} criada — implementando…`)
      onOpenRun(r.run_id)
    } catch {
      setApplyMsg('não deu p/ implementar — a issue está pronta (DoR)? já há impl ativo?')
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
        <Button variant="outline" onClick={() => void openApply()}>
          📝 Aplicar na issue
        </Button>
        {e.issue_id && /^\d+$/.test(e.issue_id) && (
          <Button variant="outline" onClick={() => void doImplement(e.issue_id)}>
            ▶ Implementar
          </Button>
        )}
        <Button variant="outline" onClick={() => void act(retryExecution)}>
          Retentar
        </Button>
        <Button variant="outline" onClick={() => void act(cancelExecution)}>
          Cancelar
        </Button>
        <Button data-testid="exec-revert" variant="outline" onClick={() => void doRevert()}>
          ↩️ Reverter PR
        </Button>
      </div>
      {applyMsg && <p className="text-xs text-accent">{applyMsg}</p>}

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
          <dt className="text-muted">ferramentas</dt>
          <dd data-testid="exec-tool-usage" className="font-mono text-xs">
            <ToolUsageLine usage={data.tool_usage} />
          </dd>
          <dt className="text-muted">risco</dt>
          <dd data-testid="exec-risk" className="text-xs">
            <RiskBadge risk={data.risk} />
          </dd>
        </dl>
      </Card>

      <Card className="flex flex-wrap items-center gap-3">
        <CardLabel className="!m-0">
          Co-piloto{' '}
          <span className={data.live ? 'text-green-300' : 'text-muted'}>
            · {data.live ? 'sessão viva' : 'inicie pelo chat'}
          </span>
        </CardLabel>
        <Button variant="default" onClick={() => setChatOpen(true)}>
          💬 Chat com o motor
        </Button>
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

      {chatOpen && (
        <Chat
          id={id}
          onClose={() => {
            setChatOpen(false)
            void load()
          }}
        />
      )}

      {applyBody !== null && (
        <div className="fixed inset-0 z-20 flex flex-col bg-background p-4">
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-2">
            <div className="flex items-center gap-2">
              <div className="flex-1 text-sm font-bold">
                Aplicar na issue <span className="text-muted">· revise antes de salvar no GitHub</span>
              </div>
              <Button variant="default" disabled={applying} onClick={() => void doApply()}>
                {applying ? 'aplicando…' : 'confirmar e atualizar'}
              </Button>
              <Button variant="ghost" onClick={() => setApplyBody(null)}>
                cancelar
              </Button>
            </div>
            <textarea
              value={applyBody}
              onChange={(e) => setApplyBody(e.target.value)}
              className="flex-1 w-full resize-none rounded-lg border border-border bg-surface p-3 font-mono text-xs outline-none focus:border-accent"
            />
          </div>
        </div>
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

// Risco determinístico (jev-guard, H) pelos arquivos tocados. Chama atenção do humano no merge —
// não bloqueia. Verde = baixo; âmbar = médio (mudança ampla); vermelho = alto (caminho sensível).
function RiskBadge({ risk }: { risk: Risk }) {
  if (!risk) return <span className="text-muted">—</span>
  const color =
    risk.level === 'alto' ? 'text-red-300' : risk.level === 'medio' ? 'text-accent' : 'text-green-300'
  const dot = risk.level === 'alto' ? '🔴' : risk.level === 'medio' ? '🟡' : '🟢'
  return (
    <span>
      <span className={`font-mono font-bold ${color}`}>
        {dot} {risk.level}
      </span>
      {risk.reasons.length > 0 && (
        <span className="text-muted"> · {risk.reasons.join(' · ')}</span>
      )}
    </span>
  )
}

// Sinal comportamental da Trilha F: entre as ops de "olhar código", quanto foi pelo caminho barato
// (code-intel) vs ler arquivo inteiro (Read). Verde = econômico; vermelho = lendo arquivo inteiro.
function ToolUsageLine({ usage }: { usage: ToolUsage }) {
  if (!usage || usage.total === 0) return <span className="text-muted">sem chamadas ainda</span>
  const c = usage.by_category
  const eff = usage.efficiency
  const effColor =
    eff === null ? 'text-muted' : eff >= 0.7 ? 'text-green-300' : eff >= 0.4 ? 'text-accent' : 'text-red-300'
  return (
    <>
      <span className={effColor}>
        {eff === null ? 'sem navegação' : `${Math.round(eff * 100)}% semântico`}
      </span>{' '}
      <span className="text-muted">
        · code-intel {c.semantic ?? 0} · Read {c.read_full ?? 0} · busca {c.search ?? 0} · edit{' '}
        {c.edit ?? 0} · shell {c.shell ?? 0}
      </span>
    </>
  )
}
