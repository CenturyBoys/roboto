# Auditoria — Trilha M (Observabilidade operacional, Telegram e checkpoints)

> Fase: **PESQUISA**. Documento de auditoria externa. O auditor não escreveu a pesquisa e não
> edita os docs de trilha — apenas emite findings e recomendações. Vale a regra do projeto:
> quem gera não valida a si mesmo.
> Executado: 2026-10-18 · Épico: #13 · Issue da trilha: #17
> Escopo: `research/M-observabilidade-telegram-checkpoints.md` + consistência cross-trilha com
> A, B, G, H, J, K, L.

---

## (a) Sumário executivo

**Veredito:** a Trilha M está **mais fraca que as demais** e ainda não é um rascunho pronto para
refino no padrão do resto da pasta. Ela acerta o enquadramento conceitual (verdade na issue+git, não
no chat; aprovação = proposta + política determinística; escada "leve → engine durável") e amarra
corretamente nos tracks certos. Mas tem **três problemas de fundo**:

1. **Disciplina de fontes reprovada.** Todas as 5 fontes são blog/vendor (dev.to, OpenClaw,
   HackerNoon, zylos.ai, temporal.io). Zero fonte primária/acadêmica — num doc cujo tema central
   (loopjacking, rollback seguro, resume verificado) depende exatamente dos papers que a **H** já
   verificou (loopjacking 2609.21081, ACRFence 2603.20625). M invoca esses papers "(H)" mas não os
   lista e não marca um único número/afirmação de vendor como "indicativo", violando frontalmente o
   princípio de disciplina de fontes que a rodada-01 introduziu e que H/G/J/K/L já aplicam.

2. **Estrutura incompleta vs. o padrão da pasta.** O README define 6 seções obrigatórias por trilha
   (Pergunta · Estado da arte · Opções e trade-offs · **Recomendação** · **Impacto em token** ·
   Perguntas em aberto). M **não tem Recomendação, não tem Impacto em token, e não tem Opções/
   trade-offs explícitas**. Resultado: três decisões-chave ficam só como "perguntas em aberto"
   (canal canônico, escopo do MVP, dashboard), sem a trilha tomar posição — ao contrário de A/B/H/K
   que recomendam.

3. **Over-claim técnico + riscos de segurança de primeira classe ignorados.** "Checkpoint leve =
   issue + journal + git" é tratado como equivalente a **durable execution**, quando não é
   (ver F-02); e o Telegram como canal de aprovação herda uma superfície de ataque (autenticação do
   aprovador, exfiltração de contexto para um terceiro, token do bot) que a M menciona de raspão mas
   não fecha — justo num projeto onde K impõe egress deny-all e H trata prompt-injection como risco #1.

**Top riscos/fraquezas:**
- Fontes 100% vendor/blog num doc de segurança (viola-princípio) — **F-07**.
- Conflação "checkpoint leve (issue+git)" ≡ "durable execution" (claim-sem-evidência) — **F-02**.
- Autenticação do aprovador no Telegram ausente (quem pode tocar Approve?) (risco alto) — **F-03**.
- Exfiltração de contexto/código sensível para o Telegram colide com egress de K (contradição) — **F-04**.
- Doc sem Recomendação/Impacto-em-token/MVP (under-spec + viola-estrutura) — **F-01, F-10**.

---

## (b) Findings

### F-01 — Doc não segue a estrutura obrigatória; sem Recomendação nem posição
```
[Trilha M] under-spec · severidade média · confiança 0.95
```
Evidência: README "Como cada doc de trilha é estruturado" lista 6 seções, incluindo
**Recomendação** e **Impacto em token**. M tem apenas Pergunta / 3 blocos descritivos / Amarrações /
Perguntas em aberto. As três decisões ("Checkpoint leve basta no MVP?", "Canal canônico?", "O que o
dashboard mostra no MVP?") estão **só** em "Perguntas em aberto".
Problema: ao contrário de A/B/H/J/K/L, a trilha não recomenda nada — vira levantamento, não decisão.
As amarrações afirmam "começar leve" e "Telegram é canal", mas isso não está consolidado numa
Recomendação com trade-offs.
Recomendação: adicionar seção **Recomendação** (posição default: checkpoint leve no MVP; GitHub como
canal canônico de gate, Telegram como notificação + atalho de aprovação espelhando o gate do GitHub;
dashboard MVP = GitHub + logs + custo de L) e seção **Impacto em token** (ver F-10). Mover as três
perguntas-decisão para a Recomendação com um default explícito, deixando em aberto só o que depende
do dono.

### F-02 — "Checkpoint leve = issue + journal + git" é tratado como durable execution (não é)
```
[Trilha M | cross H,B] claim-sem-evidência · severidade alta · confiança 0.8
```
Evidência: §3: "Durable execution mantém um run vivo através de crash/restart: checkpoint de
progresso, **replay de control flow determinístico**, retry de atividades e **preservação de wait
states**" e logo abaixo "Nossa escada ... começar **leve** — checkpoint = **estado na issue (A) +
run journal + git worktree/branch (K) + memória (G)**".
Problema: issue+git+journal persiste **estado/artefatos**, mas não dá replay determinístico de
control-flow nem preservação de wait-state de processo — que é a definição de durable execution que
o próprio parágrafo deu. A escada "leve → engine" apresenta os dois extremos como o **mesmo
mecanismo em tamanhos diferentes**, quando são mecanismos distintos (persistência de estado vs.
durabilidade de execução). Isso induz a crer que o resume pós-crash "sai de graça" do git.
Recomendação: separar explicitamente **(i) persistência de estado/artefato** (issue+git+journal —
suficiente para pausar-para-aprovação e para `git revert`/reabrir issue, que é o mecanismo de
recuperação já decidido em H) de **(ii) durable execution de verdade** (replay/wait-state — só com
engine). Afirmar que o MVP cobre (i), e que (ii) é exceção. Ajustar o texto para não chamar (i) de
"durable execution leve".

### F-03 — Autenticação do aprovador no Telegram ausente (quem pode tocar "Approve"?)
```
[Trilha M | cross H] risco · severidade alta · confiança 0.85
```
Evidência: §1 Segurança cita "verificar webhook (secret token do Telegram)", "defesa de loopjacking",
"double-approval (idempotência)", "timeout", "múltiplos aprovadores" — mas **nada sobre autorizar o
identity do aprovador** (allowlist de Telegram user IDs, o que acontece se a conta do aprovador for
comprometida / SIM-swap / sessão roubada, revogação).
Problema: o secret do webhook autentica o **Telegram→nosso servidor**, não **qual humano** clicou
Approve. Sem allowlist de user ID e sem política para conta comprometida, qualquer um num chat/grupo
mal-configurado — ou um atacante com a conta do aprovador — aprova merge/deploy. H define gate humano
justamente para ações **irreversíveis/alto impacto**; delegar isso a um toque de Telegram sem authz
do ator abre a brecha que H quer fechar.
Recomendação: exigir **allowlist explícita de Telegram user IDs** autorizados por tipo de ação;
tratar conta comprometida como risco nomeado (2FA obrigatório no Telegram, revogação, re-confirmação
em ação de altíssimo impacto); registrar **qual user ID** aprovou no estado da issue (trilha de
auditoria, amarra H §5). Para ações de maior impacto, confirmar no **canal canônico (GitHub)**, não
só no Telegram.

### F-04 — Enviar "contexto" ao Telegram colide com o egress deny-all de K e a superfície de dados
```
[Trilha M | cross K,H] risco · severidade alta · confiança 0.8
```
Evidência: §1: a mensagem de aprovação leva "**task id + resumo da ação + contexto**". K recomenda
"**egress deny-all (default) + allowlist**" e "filesystem containerizado por projeto"; H trata
prompt-injection/dados como risco de primeira classe.
Problema: Telegram é um terceiro (servidores da Telegram; bots **não** são E2E-encrypted). Mandar
"contexto" — que pode conter trechos de código, diffs, segredos acidentais, dados de issue privada —
para fora do perímetro é exatamente o tipo de egress que K controla. A M não define **o que pode e o
que não pode** ir para a notificação, nem inclui o domínio do Telegram na allowlist de egress de K
(inconsistência: K lista só GitHub/API-modelo/feeds).
Recomendação: definir **política de minimização de dados** na notificação (só task id + rótulo da
ação canônica + link para o GitHub onde vive o detalhe; **nunca** diff/código/segredo no corpo da
mensagem); adicionar o endpoint do Telegram à allowlist de egress de K de forma explícita; classificar
o canal Telegram como "baixa sensibilidade" e manter o conteúdo sensível só no GitHub/issue.

### F-05 — Canal canônico de aprovação indefinido enfraquece a defesa de loopjacking
```
[Trilha M | cross H] contradição · severidade média · confiança 0.75
```
Evidência: §1 "Telegram é **canal**; a verdade do gate vive na issue (A) + política (H). (Dois canais
de aprovação — Telegram e GitHub — = mais superfície; **decidir qual é o canônico**.)" + Pergunta em
aberto idêntica. A defesa de loopjacking de H exige **canonical rendering + comparação exata no
momento do uso**.
Problema: loopjacking depende de **uma** renderização canônica do que será executado. Dois canais de
aprovação (GitHub e Telegram) = **duas renderizações**, e nada garante que o que o inline-keyboard do
Telegram mostra == o que o GitHub mostra == o que executa. A M reconhece "mais superfície" mas deixa
sem decidir, o que mantém a contradição aberta com H em vez de resolvê-la.
Recomendação: eleger **GitHub como canal canônico** do gate (renderização canônica, auditável,
versionada); Telegram vira **espelho de notificação + atalho** cuja aprovação **referencia e revalida
o estado no GitHub** no momento do uso (comparação exata contra o gate canônico, não contra o texto
do Telegram). Assim some a segunda renderização de autoridade.

### F-06 — "run journal" é artefato novo sem definição nem lar (não existe em G)
```
[Trilha M | cross G,A] under-spec · severidade média · confiança 0.7
```
Evidência: §2 "mutações de estado" e §3 "checkpoint = estado na issue (A) + **run journal** + git
worktree/branch (K) + memória (G)". G define o formato de memória (`.md` com frontmatter
tipo=decisão|fato|handoff, em `memory/`) e A define o estado na issue — **nenhum dos dois menciona
"run journal"**.
Problema: o "run journal" é introduzido como primitiva central de checkpoint/observabilidade, mas não
está definido (formato? onde vive? é o event-history do dashboard? é `.md` de G? label/comment na
issue de A?). Sem isso, a amarração "A+G+K" é nominal e não operacional.
Recomendação: definir o run journal: **o quê** (sequência append-only de eventos de execução: início/
fim/erro de etapa, mutação de estado, decisão de gate, aprovação+aprovador), **onde** (proposta:
comentários estruturados na issue + opcional index derivado, coerente com A e G) e **relação** com o
event-history de um engine durável (quando/se adotado). Ou reconciliar com o formato de G em vez de
criar primitiva nova.

### F-07 — Fontes 100% blog/vendor; nenhuma primária; nada marcado como "indicativo"
```
[Trilha M] viola-princípio · severidade alta · confiança 0.9
```
Evidência: seção Fontes = dev.to, OpenClaw (openclawai.io), HackerNoon, temporal.io (vendor),
zylos.ai. Afirmações tratadas como fato sem ressalva: "há padrões estabelecidos", "**Padrão 2026:
'reasoning graph sobre runtime durável'**", lista de plataformas (Temporal/Restate/Inngest/DBOS/
Azure/Dagster/LangGraph) como se todas fossem equivalentes/validadas.
Problema: viola diretamente "Disciplina de fontes" do README (separar primária/acadêmica de número de
vendor; marcar vendor como "indicativo"). H/G/J/K/L fazem isso em quase todo claim; M não faz em
nenhum. "temporal.io" defendendo durable execution é a parte interessada clássica. "Padrão 2026" não
tem citação.
Recomendação: (1) puxar as fontes **primárias que H já verificou** (loopjacking 2609.21081, ACRFence
2603.20625, "Safe to Resume?") para a própria M, pois são a base dos claims de segurança de resume/
rollback; (2) marcar Temporal/temporal.io e a frase "Padrão 2026" como **indicativo de vendor/blog, a
verificar**; (3) não apresentar a lista de engines como equivalentes sem um critério.

### F-08 — Engine durável (Temporal/Restate) conflita com o runtime efêmero de K, não reconciliado
```
[Trilha M | cross K,B] inconsistência-cross-trilha · severidade média · confiança 0.7
```
Evidência: §3 "adotar engine durável (Temporal/Restate) só se complexidade/escala justificar". K:
"container **não-root, efêmero, 1 por task + git worktree**", "container descartável por task". B:
runner JIT/efêmero.
Problema: durable execution engines pressupõem **workers persistentes + state store durável + fila**
(Temporal: histórico de eventos em servidor/cluster, workers de longa vida). Isso tensiona com o
modelo "efêmero 1-por-task" de K e o runner JIT de B. A M cita a adoção do engine como simples degrau
da escada, sem notar que ele muda o modelo de runtime (deixa de ser só harness efêmero + API).
Recomendação: nomear a tensão: adotar engine durável = introduzir **componente de longa vida**
(server/worker/state store), o que contradiz o "tudo efêmero" de K → se/quando adotado, decidir onde
esse estado persistente vive (fora do container efêmero) e como se isola. Reforça por que o MVP deve
ficar no checkpoint leve.

### F-09 — Plataforma de observabilidade deferida por 3 docs (H, L e M) — ninguém decide
```
[Trilha M | cross H,L] lacuna · severidade média · confiança 0.8
```
Evidência: M Pergunta em aberto "O que o dashboard mostra no MVP (GitHub + logs) vs. plataforma de
observabilidade dedicada?"; H Pergunta em aberto "Plataforma de observabilidade (self-host vs. SaaS)";
L Pergunta em aberto "Plataforma de medição (liga com a decisão de observabilidade da Trilha H)".
Problema: a mesma decisão (qual plataforma de observabilidade/custo) está em aberto em três trilhas
que apontam uma para a outra, sem dono. M é a trilha que amarra observabilidade+custo+dashboard —
é a candidata natural a consolidar, mas não o faz.
Recomendação: M assume a consolidação: propor **default MVP = GitHub + logs estruturados + custo via
L**, com gatilho explícito para adotar plataforma dedicada (ex.: quando volume de traces/custo passar
X) — e referenciar essa decisão única de H e L, em vez de três perguntas espelhadas.

### F-10 — Impacto em token da própria observabilidade não considerado
```
[Trilha M | cross L,F] ângulo-faltando · severidade média · confiança 0.7
```
Evidência: README torna "Impacto em token" seção obrigatória e objetivo de primeira classe. M não a
tem. §2 propõe capturar "prompts, completions, tool calls, reasoning, token counts" (via H) e enviar
notificações.
Problema: observabilidade de LLM (capturar prompts/completions/reasoning) e notificações têm custo
próprio (armazenamento, e no caso de qualquer resumo gerado por LLM, token). O doc que trata de
monitorar custo não orça o custo de monitorar. Também não diz se o "resumo da ação" enviado ao
Telegram é gerado por LLM (custo) ou determinístico (preferível, princípio-mãe).
Recomendação: adicionar Impacto em token: o resumo da notificação deve ser **determinístico**
(template sobre o estado da issue), não geração de LLM; captura de trace é storage, não token, mas
retê-la tem custo — definir retenção. Amarra com L.

### F-11 — "múltiplos aprovadores" e "timeout" sob-especificados (semântica indefinida)
```
[Trilha M] under-spec · severidade baixa · confiança 0.7
```
Evidência: §1 "evitar double-approval (idempotência, B); **timeout**; **múltiplos aprovadores**".
Problema: "múltiplos aprovadores" não diz se é quorum (N-de-M), qualquer-um-aprova, ou dois-homens
para alto impacto; "timeout" não diz o que acontece ao expirar (deny automático? re-notifica?
escala?). Default de expiração importa para segurança (expirar como **deny** é fail-closed; expirar
como nada é fail-open).
Recomendação: especificar: timeout → **fail-closed (deny + escala)**; "múltiplos aprovadores" →
definir se é notificação a vários com primeiro-a-responder, ou quorum para ações de alto impacto
(dois-homens). Amarra com a política de gate de H.

---

## (c) Consistência cross-trilha

| Com | Situação | Veredito |
|-----|----------|----------|
| **A** (estado na issue) | M apoia "verdade na issue" ✔; mas introduz "run journal" que A não define (**F-06**) | parcial |
| **B** (idempotência) | double-approval via idempotência ✔ coerente; engine durável tensiona runner JIT (**F-08**) | ok / tensão |
| **G** (memória) | cita "memória (G)" como parte do checkpoint, mas "run journal" não existe em G (**F-06**) | parcial |
| **H** (gates/loopjacking/rollback) | loopjacking: comparação-no-uso ✔ **alinhado**; MAS canal canônico indefinido reabre a brecha (**F-05**); authz do aprovador ausente (**F-03**); "checkpoint leve" não é o `git revert`+reabrir issue que H fixou como default — M não cita esse default de H (**F-02**, lacuna) | tensão/lacuna |
| **J** (fila/duração) | métricas "runs em andamento/fila (J)" ✔ coerente | ok |
| **K** (runtime/worktree) | worktree como checkpoint ✔; mas egress-para-Telegram não consta na allowlist de K (**F-04**) e engine durável quebra "tudo efêmero" (**F-08**) | tensão |
| **L** (custo/latência) | "tokens/custo (L)" ✔; mas plataforma deferida em 3 docs (**F-09**) e custo da própria observabilidade não orçado (**F-10**) | parcial |

**Pontos de alinhamento genuíno (dar crédito):** a defesa de loopjacking de M ("ação canônica +
comparação exata no momento do uso") reproduz corretamente a de H; a serialização/idempotência de
aprovação amarra em B; a verdade-na-issue amarra em A; a recuperação via git/worktree amarra em K/H.
O enquadramento está certo; o problema é profundidade e disciplina, não direção.

**Lacuna cross-trilha mais importante:** H já **decidiu** o mecanismo de recuperação padrão
(`git revert` + reabrir issue; checkpoint sofisticado só como exceção). M fala de checkpoint/resume
**sem referenciar essa decisão** e sem dizer como "resume pós-crash" se relaciona com "reverter +
reabrir". Precisa amarrar explicitamente: resume (retomar de onde parou) ≠ rollback (desfazer) — e
dizer quando se usa cada um.

---

## (d) Lista priorizada de melhorias

**Endereçar primeiro (alto impacto / segurança):**
1. **F-03** — allowlist de Telegram user IDs + política de conta comprometida + registrar aprovador.
2. **F-04** — política de minimização de dados na notificação (nada sensível no corpo) + Telegram na
   allowlist de egress de K.
3. **F-02** — separar persistência-de-estado (issue+git, = MVP) de durable-execution-real (engine,
   exceção); parar de chamar issue+git de "durable execution leve".
4. **F-07** — aplicar disciplina de fontes: puxar os papers primários de H, marcar Temporal/"Padrão
   2026" como indicativo de vendor.

**Em seguida (coerência / completude):**
5. **F-05** — eleger GitHub como canal canônico; Telegram espelha e revalida contra ele.
6. **F-01** + **F-10** — adicionar Recomendação e Impacto em token; resolver as 3 perguntas-decisão
   com default explícito.
7. **F-09** — consolidar a decisão de plataforma de observabilidade em M (default GitHub+logs+L).
8. **F-06** — definir o "run journal" (formato/lar) ou reconciliar com G.

**Refino:**
9. **F-08** — nomear a tensão engine-durável × runtime-efêmero de K.
10. **F-11** — especificar semântica de timeout (fail-closed) e "múltiplos aprovadores" (quorum vs.
    primeiro-a-responder).

---

## Contagem por severidade

- **Alta:** 4 — F-02, F-03, F-04, F-07
- **Média:** 6 — F-01, F-05, F-06, F-08, F-09, F-10
- **Baixa:** 1 — F-11

Total: **11 findings**.
