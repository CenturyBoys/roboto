# Trilha H — Qualidade, segurança e recuperação (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/H-qualidade-seguranca-recuperacao.md`](https://github.com/CenturyBoys/roboto/blob/main/research/H-qualidade-seguranca-recuperacao.md).
> **Princípio unificador:** o output do modelo é uma **PROPOSTA, não um comando** — cada ação passa
> por uma camada determinística de política/validação antes de executar.
> **Status:** fundação no `main` (gates humanos, least-privilege, **secret-scan**, recuperação,
> observabilidade). git-revert e evals ficam como follow-up.

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
máquina), o run vai a `FAILED` e o motivo (redigido) aparece no feed pro humano.

| Peça | O que faz | Onde |
|---|---|---|
| scanner | formatos conhecidos (chave privada, AWS, GitHub, Slack, Google, Stripe, sk-*) nas linhas `+` | `app/secret_scan.scan_diff` |
| gate | varre o diff local nos **dois** pontos de push (impl e correção) e aborta se achar | `app/pr_cycle._guard_secrets` |

- **Alta precisão de propósito:** bloquear tem custo (trava PR legítimo), então só **formatos
  canônicos** de credencial — nada de heurística de entropia aqui (fica como follow-up). Varre só o
  que o PR **introduz** (linhas `+`), nunca contexto nem remoções.
- **Nunca vaza no log:** o finding mostra só um prefixo redigido (`ghp_…*** (40 chars)`).

## 4. Recuperação

- **Dead-letter + replay** (trilha B): run/efeito que falha após os retries vai pra dead-letter (com
  contexto e erro) e pode ser **replayado** pelo cockpit (`orchestrator/*`, endpoints em `web/console`).
- **Rollback default decidido:** `git revert` + reabrir a issue (git-first, determinístico) — **ainda
  não implementado** (follow-up). Checkpoint/time-travel sofisticado só como exceção justificada.

## 5. Observabilidade (serve a economia de token)

- **Custo por run/tier** medido de verdade (`llm_call`) — trilha F.
- **Comportamento** por run: eficiência semântica (code-intel vs ler arquivo inteiro) — trilha F,
  `app/tool_usage`. *Não dá pra otimizar nem orçar token sem medir token.*

## 6. Confiança e escalada

A validação de prontidão (DoR, trilha A) escala **JUDGE → FRONTIER** quando a confiança é baixa
(`agents/review.validar_issue_semantica`) — o mesmo fio de "proposta validada por camada
determinística". O veredito do review é determinístico (`aprovado_por_findings`, trilha D).

## 7. Follow-ups (backlog)

- **git-revert + reabrir issue** (mecanismo de rollback decidido).
- **Secret-scan: heurística de entropia** além dos formatos canônicos (hoje: alta precisão).
- **Evals / golden set** de falhas reais + LLM-as-judge calibrado como **CI gate** anti-regressão.
- **jev-guard**: allow/deny por confiança + risco pra ações de alto impacto.
- **Aprovação por ação** (tool-level) ligada ao SDK vivo, com *canonical rendering* anti-loopjacking.
