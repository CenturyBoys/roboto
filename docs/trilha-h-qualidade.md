# Trilha H — Qualidade, segurança e recuperação (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/H-qualidade-seguranca-recuperacao.md`](https://github.com/CenturyBoys/roboto/blob/main/research/H-qualidade-seguranca-recuperacao.md).
> **Princípio unificador:** o output do modelo é uma **PROPOSTA, não um comando** — cada ação passa
> por uma camada determinística de política/validação antes de executar.
> **Status:** fundação no `main` (gates humanos, least-privilege, **secret-scan**, recuperação via
> **revert**, **risk-tiering**, **evals gate**, observabilidade). LLM-as-judge e escalada automática
> ficam como follow-up.

## 1. Gates humanos — ações irreversíveis não são automáticas

- **Merge é humano** (D7): o ciclo para em "PR aprovado, aguardando merge humano"; não há auto-merge
  (`app/pr_cycle.py`).
- **Aprovação da issue refinada:** o rascunho vai pro humano (interaction `APPROVAL`, estado
  `WAITING`) e só edita o corpo no GitHub com OK (`app/human.py`, `app/refine.py`) — ver trilha A/B.
- **Calibração:** só irreversível/alto impacto vai ao humano; o resto é determinístico — senão recria
  o gargalo humano (trilha J). Aprovação por ação (tool-level) está **esboçada** (TODO no PoC vivo).

## 2. Least privilege de ferramentas por task (novo)

O output é proposta → o agente recebe **só as ferramentas que a task exige**, não o toolbox inteiro
(OWASP Agentic, segurança):

| Agente | Pode mutar? | Ferramentas negadas |
|---|---|---|
| **refine / scope / review** | não (LÊ e PROPÕE) | `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Bash` |
| **implement / correct** | sim (edita o repo) | — (sem restrição) |

- Política **pura e determinística** em `app/tool_policy.disallowed_tools_for`; aplicada na
  instanciação do motor (`runtime.py` → `ClaudeCodeEngine(disallowed_tools=...)`).
- **Navegação continua liberada a todos:** `Read`/`Grep`/`Glob` e o **code-intel** (MCP) não entram na
  lista de negados — least privilege sem quebrar a economia de token (trilha F).
- Fecha a brecha por **política**, não só pelo prompt "read-only por prompt" (que o modelo pode ignorar).

## 3. Secret-scan do diff antes do push (novo)

Gate determinístico de segurança: antes de **empurrar** um PR, o harness varre as linhas
**adicionadas** do diff atrás de credenciais. Achou → **bloqueia o push** (o segredo nem sai da
máquina) e o motivo (redigido) aparece no feed pro humano.

| Peça | O que faz | Onde |
|---|---|---|
| scanner | formatos conhecidos (chave privada, AWS, GitHub, Slack, Google, Stripe, sk-*) nas linhas `+` | `app/secret_scan.scan_diff` |
| gate | varre o diff local nos **dois** pontos de push (impl e correção) e bloqueia se achar | `app/pr_cycle._guard_secrets` |

### Auto-correção (guarda robusta, não rígida)

Bloquear está certo; terminar seco não. No ciclo de **implementação**, em vez de ir direto a
`FAILED`, o bloqueio é **devolvido ao motor**: ele recebe o resumo (redigido) e é instruído a trocar
o literal por um **placeholder/env** (um teste de redação de PII não precisa de token real) e
re-escaneia — até `ROBOTO_…`/`_SECRET_FIX_ATTEMPTS` tentativas. Só vira `FAILED` se **persistir**
após a auto-correção (último recurso). O push **nunca** sai antes de a varredura voltar limpa. (A
correção de PR — `process_correct_tick` — mantém o bloqueio terminal.)

### Override humano (falso-positivo legítimo)

Quando o literal PRECISA existir (raro), o operador resolve pelo cockpit, sem editar código do fleet:
no detalhe de uma execução barrada (`secret_blocked`), o botão **"🔓 Liberar push (falso-positivo)"**
(`POST /executions/{id}/allow-secret`) grava um **override durável** (tabela `secret_override`, por
run) e reenfileira. No próximo tick, `run_pr_cycle(allow_secret=True)` **não aborta** — faz o push e
**audita** no feed (`⚠️ secret-scan OVERRIDE humano…`). Confirmação na UI (ação impactante). Assim o
guard é **robusto** (bloqueia por padrão, auto-corrige) sem ser **rígido** (tem escape auditado).

- **Duas camadas:** (1) **formatos canônicos** de credencial (baixíssimo falso-positivo); (2)
  **heurística keyed + entropia** — identificador com cara de segredo (`DB_PASSWORD`, `api_key`…)
  atribuído a um valor de **alta entropia** (≥3.5 bits/char, ≥16 chars). Exigir os **dois** sinais
  (nome + aleatoriedade) mantém o falso-positivo baixo: placeholder (`changeme`), valor curto ou chave
  não-secreta **não** bloqueiam.
- Varre só o que o PR **introduz** (linhas `+`), nunca contexto nem remoções.
- **Nunca vaza no log:** o finding mostra só um prefixo redigido (`ghp_…*** (40 chars)`).

## 4. Recuperação

- **Dead-letter + replay** (trilha B): run/efeito que falha após os retries vai pra dead-letter (com
  contexto e erro) e pode ser **replayado** pelo cockpit (`orchestrator/*`, endpoints em `web/console`).
- **Reverter PR (git-first, novo):** o botão **↩️ Reverter PR** no detalhe da execução enfileira um
  run `revert`; o daemon cria uma branch de revert a partir da base, **reverte os commits do PR**,
  empurra e abre um **PR de revert**, e **reabre a issue** pra o fleet refazer (`app/revert`).

| Peça | O que faz | Onde |
|---|---|---|
| ação no cockpit | botão confirma e enfileira o revert (liga o PR ao run) | `web/console` `/executions/{id}/revert`, `ExecDetail` |
| processador | `git revert` dos commits + PR de revert + reabre issue | `app/revert.process_revert_tick` |
| git | cria a branch de revert e reverte o range; **False** se conflitar | `git_ops.revert_range` |

- **Merge do revert continua humano** (D7): o revert é uma **proposta** (um PR), não um push
  destrutivo. Conflito no `git revert` → run `FAILED` + aviso no feed, **nada é empurrado**.
- Checkpoint/time-travel sofisticado só como exceção justificada (não implementado).

## 5. Observabilidade (serve a economia de token)

- **Custo por run/tier** medido de verdade (`llm_call`) — trilha F.
- **Comportamento** por run: eficiência semântica (code-intel vs ler arquivo inteiro) — trilha F,
  `app/tool_usage`. *Não dá pra otimizar nem orçar token sem medir token.*

## 6. Risk-tiering (jev-guard, novo)

Antes do gate humano (merge), o fleet **classifica o risco** da mudança pelos **arquivos tocados** —
determinístico, sem LLM (`app/jev_guard`). O nível é **surfado**, não bloqueia:

| Nível | Quando | Sinal |
|---|---|---|
| 🔴 **alto** | toca caminho sensível: migrations, CI/CD, infra (IaC), deploy, auth/segurança, lockfile | `escalate=True` (candidato a gate) |
| 🟡 **medio** | mudança ampla (> 8 arquivos) sem caminho sensível | — |
| 🟢 **baixo** | o resto | — |

- **Onde aparece:** seção de risco no **corpo do PR** (o revisor vê onde olhar) e **badge no cockpit**
  (detalhe da execução, `data-testid=exec-risk`) — calculado do diff **já cacheado**, sem recomputar git.
- **Conservador:** não adiciona atrito ao fluxo normal — só chama atenção. A **escalada automática**
  (alto → esperar OK humano antes de abrir PR) fica como **toggle de follow-up**, pra evitar
  *approval fatigue* enquanto a régua não está calibrada.

## 7. Evals — gate anti-regressão (novo)

Golden set **versionado** (`evals/golden/*.json`) de casos `input → expect` rodados como **gate de
CI**: regressão numa das decisões **determinísticas** de segurança barra o merge. **Sem LLM no CI**
(sem custo/flakiness) — os evals de LLM-as-judge (qualidade de refino/review) ficam como follow-up
**agendado**, não contínuo.

| Peça | O que faz | Onde |
|---|---|---|
| golden set | casos curados (crescem com **falhas reais**) | `evals/golden/*.json` |
| runner | roda os graders e conta falhas | `app/evals.run_evals` |
| graders | DoR, classificação de task, risk-tiering, secret-scan | `app/evals` (dispatch) |
| gate CI | falha o build em regressão | `scripts/evals_gate.py` no job `tier1` |

Cobre os graders que **são** a camada de segurança (determinismo primeiro). Cada caso que escapou em
produção vira um caso no golden — o gate impede que volte.

## 8. Anti-loopjacking (aprovação por ação — primitivo)

*Loopjacking* = fazer o humano aprovar uma ação enquanto o sistema executa **outra** (troca de estado
entre aprovar e usar). Defesa verificada (pesquisa H): **canonical rendering** + **comparação EXATA
no uso** — o que foi aprovado tem de ser idêntico ao que executa.

| Peça | O que faz | Onde |
|---|---|---|
| canonical_action | renderização determinística (chaves ordenadas) da tool + args | `app/approval_guard` |
| action_digest / sign | digest sha256 assinado no momento da aprovação | `app/approval_guard` |
| matches | recomputa no uso e compara por digest; divergiu → **nega** | `app/approval_guard` |

**Entregue:** o primitivo puro + testes (rejeita argumento trocado, tool trocada, argumento extra).
**Sliver:** o *enforcement* real (gatear a tool via callback `can_use_tool`) depende do **SDK vivo**
(TODO em `engines/claude_code`); o primitivo já está pronto pra plugar quando o callback existir.

## 9. Confiança e escalada

A validação de prontidão (DoR, trilha A) escala **JUDGE → FRONTIER** quando a confiança é baixa
(`agents/review.validar_issue_semantica`) — o mesmo fio de "proposta validada por camada
determinística". O veredito do review é determinístico (`aprovado_por_findings`, trilha D).

## 10. Follow-ups (backlog)

- **evals — LLM-as-judge** (dimensões subjetivas: qualidade de refino/review), em run **agendado**.
- **jev-guard — escalada automática**: alto risco → esperar OK humano (hoje só surfa o nível).
- **Aprovação por ação — enforcement**: plugar o primitivo anti-loopjacking no callback do SDK vivo.
