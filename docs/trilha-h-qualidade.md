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
  o gargalo humano (trilha J). **Aprovação por ação** (tool-level) agora é **enforcement de verdade**
  via callback `can_use_tool` (§9); o binding com o SDK vivo valida no PoC.

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
- **Camada fina (runtime):** este least-privilege é a camada **grosseira** (na instanciação do motor);
  a decisão **por chamada** (ex.: liberar `git status`, gatear `git push`) é a **policy de 2 eixos**
  (`verdict`/`classify`, §9).

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

## 4. Porta de CI local antes do push (novo)

**Problema (2026-11-08):** o fleet abria PR sem rodar a **própria porta de CI do repo** — só um
type-check best-effort via code-intel que, em monorepo, **se auto-desligava**. Resultado: PR com
`lint`/`tsc` vermelho chegava ao GitHub, o CI reprovava e isso vinha **invisível** ao operador (só
"failed" seco). Contradizia o princípio-mãe ("o CI é o juiz do pronto").

**Correção (determinismo 1º):** antes do push, o harness roda a **MESMA porta que o CI aplica** —
`lint` + `typecheck` + `build` + `test` (os scripts reais do `package.json`, via `pnpm`), na ordem
barato→caro. Vermelho de **código** volta ao motor como feedback autoritativo (bounded, última
tentativa no **forte**) + re-commit; só abre o PR quando **verde**. Igual ao guard de hook, mas é a
porta do próprio CI.

| Peça | O que faz | Onde |
|---|---|---|
| descoberta | lê `package.json` → `lint/typecheck/build/test` na ordem barato→caro (`pnpm -s <script>`) | `app/repo_ci.discover_ci_commands` |
| execução | **estáticos (`lint`+`typecheck`) juntos** → acumula os vermelhos num feedback só (1 turno, mata o ping-pong lint↔typecheck); `build`/`test` param no 1º vermelho; trima a saída pelo fim | `app/repo_ci.run_ci` |
| gate | antes do push: vermelho → corrige (bounded) → re-commita → re-roda; verde → segue | `app/pr_cycle` (bloco pré-`push`) |

- **`build` pega o que o `typecheck` não vê:** compilar expõe erro que a checagem de tipos deixa
  passar — ex.: Next detecta `middleware.ts` + `proxy.ts` juntos e o **build quebra** (migração
  middleware→proxy do Next 16). Validado ao vivo: o modelo caro (480b) só viu isso no CI do GitHub
  (run #117, PR vermelho); com `build` no gate, o **30b local** pegou localmente, corrigiu e saiu
  **verde** (run #118). `build` roda **antes** do `test` (sem compilar, nem adianta testar).
- **Infra ≠ código — `test` e `build`:** `lint` e `typecheck` são análise **estática pura** — qualquer
  vermelho ali é **código** (ex.: `TS2307 Cannot find module` = import errado) e **sempre** volta ao
  motor. Os passos **`test`** (DB/serviços) e **`build`** (pode faltar env/serviço) ganham o benefício
  da dúvida: vermelho que casa padrão de infra (`ECONNREFUSED`, DB fora, **banco de teste não migrado**
  — Prisma `table does not exist`/`P2021`) **não** realimenta o motor — é **surfado** e o ciclo
  **segue** (o CI do GitHub, com DB migrado, é o juiz desses). Validado ao vivo: run #103 pegou o
  vermelho e não abriu PR; run #104 mostrou que waving-through de `typecheck` reabre PR vermelho → por
  isso infra fica restrita a `test`/`build`. Em ambiente sem o DB de teste,
  `ROBOTO_LOCAL_CI_CMDS=lint,typecheck,build` evita rodar a suíte de integração que só o CI julga.
- **Esgotou e segue vermelho:** **não abre PR vermelho** — escala p/ humano (feed + Telegram).
- **Honestidade do "infra" (#280):** quando o `test` degrada p/ infra, a mensagem **não** diz "ok, o
  CI do GitHub é juiz" (parecia aprovação) — diz **"NÃO validado localmente — o CI do GitHub é
  OBRIGATÓRIO antes do merge"**. Não valida teste não pode parecer que validou.
- **Validar o committado, não a árvore suja (#281):** antes do `push`, um `commit_all` defensivo
  (`git add -A`, no-op se limpo) garante que o PUSH inclui **tudo que o CI local validou** — fecha o
  *false-green* de um arquivo deixado fora do commit (o import órfão `region-lock` do #310: verde
  local na árvore, vermelho no CI no commit).
- **Visibilidade:** cada passo vai pro feed (`🔴 CI local lint reprovou…`, `✅ CI local verde…`) —
  a falha de CI deixa de ser invisível. O mesmo vale para o **review**: cada tentativa deixa o veredito
  no feed (`🔍 Review: aprovado/reprovou (N)`) e, ao esgotar sem aprovação, o motivo (`🚩 Encerrado
  sem aprovação após N tentativas` + pendências) — antes o run virava `failed` **mudo**. E todo finding
  do review carrega uma **recomendação acionável** (nunca vazia): o impl recebe o *como corrigir*, não
  só o *o quê*.
- **Configurável:** `ROBOTO_LOCAL_CI=0` desliga; `ROBOTO_LOCAL_CI_CMDS=lint,typecheck` restringe.

## 5. Recuperação

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

## 6. Observabilidade (serve a economia de token)

- **Custo por run/tier** medido de verdade (`llm_call`) — trilha F.
- **Comportamento** por run: eficiência semântica (code-intel vs ler arquivo inteiro) — trilha F,
  `app/tool_usage`. *Não dá pra otimizar nem orçar token sem medir token.*

## 7. Risk-tiering (jev-guard, novo)

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

## 8. Evals — gate anti-regressão (novo)

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

## 9. Anti-loopjacking (aprovação por ação — primitivo)

*Loopjacking* = fazer o humano aprovar uma ação enquanto o sistema executa **outra** (troca de estado
entre aprovar e usar). Defesa verificada (pesquisa H): **canonical rendering** + **comparação EXATA
no uso** — o que foi aprovado tem de ser idêntico ao que executa.

| Peça | O que faz | Onde |
|---|---|---|
| canonical_action | renderização determinística (chaves ordenadas) da tool + args | `app/approval_guard` |
| action_digest / sign | digest sha256 assinado no momento da aprovação | `app/approval_guard` |
| matches | recomputa no uso e compara por digest; divergiu → **nega** | `app/approval_guard` |

**Entregue:** o primitivo puro + testes (rejeita argumento trocado, tool trocada, argumento extra).

### Enforcement — o callback `can_use_tool` (#265)

O primitivo acima virou **gate de verdade**: em `permission_mode="default"`, o motor chama
`can_use_tool` ANTES de cada ação que pede permissão, e a decisão passa pela política determinística
antes de executar. Derivado do modelo "harness executa o call aprovado, ligado por hash" do Tucano
(Apache-2.0; ver [`research/tucano-reuso.md`](https://github.com/CenturyBoys/roboto/blob/main/research/tucano-reuso.md)).

| Peça | O que faz | Onde |
|---|---|---|
| decide_tool_use | cria a `interaction` de aprovação, espera o humano pelo `SessionHub` e verifica por digest antes de liberar | `app/approval_gate` |
| verify_and_decide | decisão **pura**: libera só se aprovado **e** `matches` (anti-loopjacking); senão nega com motivo | `app/approval_gate` |
| can_use_tool | seam no motor: mapeia `GateDecision` → `PermissionResultAllow/Deny` do SDK (lazy) | `engines/claude_code._build_can_use_tool` |

- **Binding anti-loopjacking:** cada ação cria a SUA `interaction` — só se aprova a ação exata
  pendente; a recusa volta ao motor como contexto do próximo turno (ele sugere outro caminho).
- **Interrupção:** `interrupt()` corta o run de forma **cooperativa** (entre mensagens); o abortar
  HARD de uma ação em curso é o caminho `ClaudeSDKClient.interrupt` do co-piloto.
- **Entregue:** núcleo puro de SDK + testes (`tests/test_approval_gate`). O binding com o SDK vivo
  (`can_use_tool` no `query()`) e o wiring no loop orquestrado validam no **PoC** (padrão do co-piloto).

### Política de 2 eixos — quando o gate dispara (#267)

O `can_use_tool` não pergunta para tudo: uma **política determinística** decide **auto/ask/off** por
chamada, antes do humano. Dois eixos (derivado do `verdict()` do Tucano, Apache-2.0):

- **classe** (`ToolClass` read/write/sensitive) — o que a ferramenta faz;
- **autonomia** (`ActionMode` ask/auto/off por `ActionKind` commit/push/pr/merge/delete), graduada por
  nível (`Autonomy` careful/normal/free), resolvida most-specific-first (regra do agente → nível).

| Peça | O que faz | Onde |
|---|---|---|
| classify | `(tool, args)` → classe + ações + high_risk; **parsing de `Bash` por subcomando** (`git status` lê, `git push` é push) | `app/classify` |
| verdict | decisão pura auto/ask/off a partir de classe/ações/nível | `app/policy` |
| make_policy_callback | liga tudo ao `can_use_tool`: `run`→libera, `off`→nega, `ask`→gate humano (§9) | `app/approval_gate` |

**Invariantes (independem do nível):** **high-risk sempre pede humano** (caminho sensível via
`jev_guard`, §7); **merge/delete nunca viram auto** (D7/irreversível); **outside-guard** — ação
*outbound* depois de ler conteúdo externo volta a pedir (anti prompt-injection). Resolve a fraqueza do
least-privilege estático (§2, `Bash` tudo-ou-nada). **Entregue:** `verdict`/`classify` puros e testados
(`tests/test_policy`, `tests/test_classify`); o sinal de *outside* por turno e o wiring no loop
validam no PoC.

## 10. Confiança e escalada

A validação de prontidão (DoR, trilha A) escala **JUDGE → FRONTIER** quando a confiança é baixa
(`agents/review.validar_issue_semantica`) — o mesmo fio de "proposta validada por camada
determinística". O veredito do review é determinístico (`aprovado_por_findings`, trilha D).

## 12. Higiene de commit — sem atribuição de IA (#279, novo)

A org **proíbe** `Co-Authored-By: Claude` e rodapés "Generated with …" em commit ou PR — *mesmo que o
harness sugira*. O setting `includeCoAuthoredBy:false` do Claude Code **não basta**: o modelo escreve
o trailer **à mão** no `git commit -m`. A garantia é **determinística**:

| Peça | O que faz | Onde |
|---|---|---|
| strip_ai_trailers | remove linhas de co-autor de IA / rodapé de ferramenta; preserva co-autor humano | `app/commit_hygiene` (puro, testado) |
| install_hook | instala um `commit-msg` global (`core.hooksPath`) que roda o strip em TODO commit, no boot | `app/commit_hygiene` + `runtime` |

Pega o commit **manual** do modelo (que o setting não barra) e vale pro motor no repo-alvo. Incidente
que motivou: `arenavalendo/main#310` nasceu com o trailer (remediado por `--amend`).

## 11. Follow-ups (backlog)

- **evals — LLM-as-judge** (dimensões subjetivas: qualidade de refino/review), em run **agendado**.
- **jev-guard — escalada automática**: alto risco → esperar OK humano (hoje só surfa o nível).
- **Aprovação por ação — ligada no loop (#271, opt-in)**: `process_pr_run_tick` passa
  `approval=make_policy_callback(...)` ao motor quando `ROBOTO_APPROVAL=1` (nível por `ROBOTO_AUTONOMY`,
  default `free`). Default OFF → fluxo autônomo (bypassPermissions) intacto. Falta só **validar o
  `can_use_tool` no SDK vivo** no PoC.
- **Policy de 2 eixos (#267)**: trocar o least-privilege estático (§2) por `verdict()` puro —
  tool-class × autonomia por ação + outside-guard (derivado do Tucano; ver `research/tucano-reuso.md`).
