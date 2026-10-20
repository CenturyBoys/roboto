# Decisões a fechar (para sair da pesquisa → build)

> Revisão final. Cada item tem **pergunta**, **pontos de vista** (trade-offs) e uma **proposta**
> (recomendação). O dono verifica e marca a **Decisão**. Fechar a §1 destrava o build; a §2 eu
> escrevo como design; a §3 pode ser decidida ao implementar.

Legenda da decisão: ⬜ em aberto · ✅ aceita a proposta · ✏️ outra (anotar).

---

## §1 · Fundação (bloqueiam o build)

### D1 · Stack do `roboto` (o que construímos)
- **Pontos de vista:** *Python* (ecossistema de agentes/LLM, SDKs anthropic + typesafe/Jev, FastAPI,
  casa com ADK — foi o do exemplo viva-agent) · *TypeScript* (bom se houver muito web/BFF; um SDK só
  no front e back) · *Poliglota* (orquestrador numa, bot noutra — mais superfície).
- **Proposta:** **Python** para orquestrador + agentes + gateway + bot (um runtime só); TS só se/quando
  surgir front dedicado.
- **Decisão:** ✅ **Python total**, **async**, **containerizado**, e **retorno estilo Rust
  `Result<Ok, Error>`** — ok/erro explícito no retorno, **não exceções para fluxo de controle**
  (vira convenção no E/`AGENTS.md`).

### D2 · Escopo e ordem do MVP
- **Pontos de vista:** *Loop núcleo primeiro* (Refinamento→Implementação→Review+CI) entrega valor cedo
  e valida o circuito · *Fleet completo de uma vez* cobre tudo mas atrasa o primeiro valor e multiplica decisões.
- **Proposta:** MVP = **Refinamento (+gate de prontidão) · Implementação · Review (≠autor) · CI**;
  depois **Planejamento**; **Segurança(ambiente)** e **Docs** em seguida; **SRE/Incidente** só com produção.
- **Decisão:** ✅ MVP = loop núcleo **com Telegram desde já**: **Refinamento conversacional via
  Telegram** (refino pelo chat → materializa a issue) · Implementação · Review(≠autor) · CI.
  Planejamento/Segurança/Docs depois.

### D3 · Plataforma de observabilidade
- **Pontos de vista:** *GitHub + logs estruturados* (zero custo, mas sem trace de LLM/custo) ·
  *Self-host (Langfuse/Phoenix)* (trace+custo de LLM, dado em casa, algum ops) · *SaaS* (rápido, mas
  custo recorrente + código/trace em terceiro).
- **Proposta:** **GitHub + logs + self-host leve (Langfuse/Phoenix)** para trace/custo de LLM; evitar SaaS no início.
- **Decisão:** ✅ **Subir um Docker com o ambiente de dev inteiro** (self-host) rodando a
  observabilidade, com **checks periódicos** (health + métricas em periodicidade). SaaS fica fora.

### D4 · Secrets
- **Pontos de vista:** *OIDC curto do GitHub Actions* (sem segredo longo guardado; simples) ·
  *Vault/OpenBao* (secrets dinâmicos/rotação; mais poderoso, mais ops) · *SOPS* (config cifrada no git).
- **Proposta:** **OIDC curto + secret store mínimo** no MVP; **Vault/OpenBao** só quando houver
  vários segredos de vida longa; SOPS para config estática.
- **Decisão:** ✅ **Ansible + ansible-vault** para senhas; **uma única variável no GitHub** (a senha
  do vault, como secret `ANSIBLE_VAULT_PASSWORD`). Local: a senha fica em **`.ansible.vault_pass`
  (gitignored)**. Arquivo + `.gitignore` criados agora; falta setar o secret no GitHub.

### D5 · Checkpoint / continuidade
- **Pontos de vista:** *Leve* (issue + git worktree + run journal) — simples, determinístico, cobre
  resume de alto nível · *Durable execution engine* (Temporal/Restate) — replay/wait-state robusto, mas infra nova.
- **Proposta:** **Leve no MVP**; engine durável só se escala/replay exigir (reavaliar com dados).
- **Decisão:** ✅ **Leve (issue + git worktree + run journal)** no MVP; engine durável só se escala/replay exigir.

### D6 · Orçamento (token/$)
- **Pontos de vista:** *Teto global* (R$550/mês de API) simples de controlar · *Budget por issue*
  exige baseline medido (ainda não existe).
- **Proposta:** **Teto global = R$550/mês**, roteamento barato-primeiro (Jev/chineses) + alerta em 80%;
  **budget por issue** entra depois da 1ª medição (fica como "medir no build").
- **Decisão:** ✅ **Teto global R$550/mês + alerta em 80%**, barato-primeiro; budget por issue após a 1ª medição.

### D7 · Catálogo de ações com gate humano obrigatório
- **Pontos de vista:** *Lista curta* (só irreversível) = mais autonomia, mais risco · *Lista longa* =
  seguro, mas recria gargalo humano.
- **Proposta (lista inicial):** **merge, deploy, mudança de credencial, decisão arquitetural,
  resolução de conflito de merge, ação destrutiva.** O resto é `allow`/`deny` determinístico
  (jev-guard), com amostragem dos `allow` de baixo risco.
- **Decisão:** ✅ **Lista proposta aceita** (merge · deploy · credencial · arquitetura · conflito de
  merge · destrutivo); resto `allow`/`deny` (jev-guard) + amostragem.

### D17 · Tenancy e empacotamento (multi-empresa, N repos) — Docker image
- **Pergunta:** o `roboto` é empacotado como **Docker image** e sobe **uma instância por empresa**,
  atendendo **N repos** daquela empresa?
- **Pontos de vista:** *Uma instância por empresa (single-tenant por deploy)* → isolamento forte de
  dados/segredos/orçamento, casa com jurisdição/sensibilidade (I/H); custo = mais deploys · *Multi-tenant
  compartilhado* → menos infra, mas isolamento só lógico e risco de vazamento entre empresas (pior).
  Acesso a N repos: *GitHub App* (instala na org, webhooks de todos, token por-repo escopo mínimo) vs
  *machine-user/PAT* (não escala para muitos repos).
- **Proposta:** **Sim, Docker image(s); uma instância por empresa; um orquestrador atende N repos via
  GitHub App.** Estado keyed por `repo+issue`; **WIP e orçamento por-repo e por-empresa**. Config,
  **vault por empresa** (D4) e teto (L) por tenant.
- **Decisão:** ✅ (dono) **Docker image · 1 instância por empresa · N repos via GitHub App**.

### D18 · Agente(s) sênior persistente(s) — persona consultiva por empresa/projeto *(interpretação a confirmar)*
- **Ideia (do dono):** além dos agentes efêmeros por task, um **"engenheiro sênior"** por
  empresa/projeto — persona **conversável** (via Telegram), **responsável por entregas**, com quem o
  humano **tira dúvidas e planeja**, e que **persiste** (lembra do contexto da empresa/projetos).
- **Reconciliação / pontos de vista:**
  - *Persistência = memória + identidade, instanciada SOB DEMANDA* (não processo sempre-ligado):
    mantém determinismo-primeiro + runtime efêmero (K); a "permanência" vem da **memória durável
    (G)** + persona versionada; ele é "acordado" quando você fala. **(recomendado)**
  - *Processo sempre-ligado*: presença contínua, mas custo de idle + estado vivo fora da issue (pior).
- **Proposta:** nova **classe de agente (Trilha 0)** — **persona consultiva persistente**
  (on-demand + memória), acessível pela porta Telegram (M), escopada por empresa/projeto (D17).
  Planejamento/arquitetura/refino conversam por ela; **execução segue nos agentes efêmeros**;
  verdade continua na issue/repo.
- **Decisão:** ✅ **Confirmado** (dono): sob demanda + memória durável; **execução nos efêmeros**;
  é um tech lead/staff **consultivo** por empresa/projeto.

### D19 · Acesso de leitura a dados/APIs da empresa (insumo para desenvolver)
- **Pergunta:** o agente (sênior consultivo e implementadores) pode **ler o banco e APIs internas**
  da empresa como contexto para planejar/desenvolver? É válido?
- **Resposta:** **Sim — e útil —, mas NUNCA como query livre.** Dar credencial de DB a um modelo que
  lê texto do usuário é **superfície de exfiltração** (confirmado na busca e no próprio exemplo viva:
  *"a única porta é `get_recommendations(memberId)`"*). Padrão seguro (2026):
  - **Read-only por padrão**; **service account dedicada por agente/tenant**; least privilege.
  - **Sem SQL cru do LLM** → **views restritas / queries parametrizadas pré-definidas**; allowlist de operações.
  - **RLS deny-by-default** + escopo **por tenant** (nunca cross-empresa); preferir **réplica de leitura**.
  - **Auditoria** de todo acesso (liga ao `llm_call`, D10) + egress allowlist (K) + secret via vault (D4).
  - ⚠️ **Read-only NÃO basta contra prompt injection via dado armazenado**: texto numa linha pode
    mandar o agente devolver dado fora do escopo → por isso **porta curada** (função específica, não
    consulta livre) + RLS + minimização.
  - **APIs de outros sistemas**: mesmo modelo — tools de leitura curadas, token escopado, allowlist.
- **Pontos de vista:** *query livre (DB para o modelo)* = flexível, exfiltração enorme → **rejeitado** ·
  *tools read-only curadas + views/RLS* = seguro, menos flexível → **recomendado**.
- **Proposta:** um **"data-gateway de leitura" (MCP)** com tools read-only curadas, por tenant,
  auditado — como o `code-intel` é MCP para código (ferramentificação, F). Amarra H/I/K/D17.
- **Decisão:** ✅ (dono) **data-gateway de leitura (MCP) read-only curado, por tenant, auditado — nunca query livre**.

---

## §2 · Design a escrever (proposta — eu redijo como extensão das trilhas)

### D8 · Orquestrador + persistência (passo de design mais fundo)
- **Proposta:** **máquina de estados do run no banco**; idempotência por `head_sha+evento+nº`
  **com "reconferir dentro do lock"** (não só dedupe na entrada); serialização por issue/PR;
  **varredura** de run abandonado (estado gravado antes da chamada externa). Padrão do turno do viva.
- **Decisão:** ✅ **escrito em [`DESIGN-nucleo.md`](DESIGN-nucleo.md)** (ciclo de vida, idempotência, lock+reconferir, varredura)

### D9 · Outbox / efeitos exactly-once
- **Proposta:** ações com efeito colateral (abrir PR, notificar Telegram, publicar evento) via
  **gravar → commit → publicar**, com dedupe do consumidor. Dissolve "morreu no meio" (estado sem efeito
  / efeito sem estado). Toca B (idempotência) + M (Telegram/estado).
- **Decisão:** ✅ **adotado** — outbox + `gravar→commit→publicar` ([`DESIGN-nucleo.md`](DESIGN-nucleo.md))

### D10 · Esquema de auditoria `llm_call`
- **Proposta:** registro por chamada de modelo: `tokens, custo, latência, modelo/provedor,
  versão de prompt, versão de AGENTS.md/guia, run/issue`. É o que torna **custo (L)** e
  **observabilidade/reprodutibilidade (H)** verificáveis.
- **Decisão:** ✅ **adotado** — tabela `llm_call` ([`DESIGN-nucleo.md`](DESIGN-nucleo.md))

### D11 · Versão de prompt/AGENTS.md por run
- **Proposta:** carimbar em cada run qual prompt/AGENTS.md rodou (liga ao D10) → "qual regra falou no
  run X" sem reconstruir histórico.
- **Decisão:** ✅ **adotado** — campos no `run`/`llm_call` ([`DESIGN-nucleo.md`](DESIGN-nucleo.md))

---

## §3 · Afinações de trilha (dá pra decidir ao implementar)

### D12 · Issue types + sub-issues nativos vs labels; Projects dentro ou fora
- **Proposta:** **issue types + sub-issues nativos** do GitHub; **Projects fora** no MVP (estado via
  labels/status), reavaliar como visualização depois.
- **Decisão:** ✅ issue types + sub-issues nativos; Projects fora no MVP (estado via labels).

### D13 · Adotar GitHub Spec Kit como ferramenta de spec?
- **Pontos de vista:** *Sim* (padrão pronto Constitution→…→Implement, menos reinvenção) · *Não*
  (nossa DoR/DoD já cobre; menos dependência).
- **Proposta:** **usar as ideias do Spec Kit** (spec versionada = issue), **sem acoplar à ferramenta** no MVP.
- **Decisão:** ✅ usar as ideias (spec versionada = issue), sem acoplar à ferramenta no MVP.

### D14 · Onde as skills vivem + versionamento
- **Proposta:** `.claude/skills/` no `roboto`, **versionadas e revisadas por composição** (CompoSkill);
  plugin/compartilhamento depois.
- **Decisão:** ✅ `.claude/skills/` no `roboto`, versionadas e revisadas por composição.

### D15 · Canal canônico de aprovação
- **Proposta:** **GitHub é o canônico** (review/estado da issue); **Telegram = atalho revalidado no servidor**.
- **Decisão:** ✅ GitHub canônico; Telegram = atalho revalidado no servidor.

### D16 · Mix de modelos por etapa (provedor barato inicial)
- **Proposta:** começar com **1 modelo chinês/aberto barato** (ex.: um de coding forte) para geração +
  **Claude frontier** no difícil + **Jev** no judge; **pinar por medição** (não por leaderboard).
- **Decisão:** ✅ começar com 1 modelo chinês/aberto barato + Claude frontier + Jev; **pinar por medição**.

### D20 · Canais de comunicação + áudio (refinamento de D15/M)
- **Pergunta:** Telegram é o melhor canal? Dá pra fazer tudo por ele? E áudio?
- **Decisão:** ✅ **Canais = adapters sobre um núcleo agnóstico.** **Telegram = canal humano primário**
  (móvel/push/assíncrono) **com áudio** (voz → STT Whisper/OpenRouter → mesmo pipeline). **CLI** =
  canal do operador/dev (local). **GitHub = registro canônico** (D15). Dá pra fazer toda a conversa
  humana no Telegram; a verdade fica na issue; o CLI serve operação. Detalhe em Trilha M.

---

## §4 · Operação interativa + motores de coding (spec do dono, 2026-10-19)

> Vêm do doc "Visão geral da arquitetura" do dono. Reconciliadas e detalhadas em
> [`N-operacao-interativa-e-motores.md`](N-operacao-interativa-e-motores.md). ⬜ = aguardam o ok
> do dono (recomendação já dada). D26 fica **parcial** (doc cortado no §8).

### D21 · Bot do Telegram por empresa; tenant derivado do servidor (refino de D20/D17)
- **Decisão (proposta):** **um bot por empresa**; o backend resolve o `tenant` pelo **token/bot**
  (nunca confia em `tenant_id` vindo na mensagem); identidade + autorização validadas mesmo em
  grupo privado; token do bot é secret (vault, D4). *(o adapter atual já vincula token→tenant na
  construção — falta só formalizar a regra e a allowlist por empresa.)*
- **Decisão:** ✅ **implementado** (adapter vincula token→tenant; allowlist; webhook ingest com
  tenant do servidor — PRs #22/#25).

### D22 · Registro de motores de coding (Codex, Claude Code) via adapters + contrato comum ⭐
- **Decisão (proposta):** motor de coding é **plugável por ambiente** (não fixar fornecedor);
  cada motor tem um **`EngineAdapter`** (evolução da porta `Runner`, K) com contrato comum: iniciar/
  acompanhar execução, eventos, erros/resultados, `request_human_input`, aprovações, **retomada**,
  mapa **sessão nativa↔interna**, encerrar/cancelar/recuperar. **PoC obrigatório** (matriz de
  capacidades por motor) antes de fixar o contrato. É o **reframe** central: motor ≠ `ModelGateway`.
- **Decisão:** ✅ **contrato + registro + matriz resolvidos** — porta `CodingEngine` (start/events/
  respond/interrupt; resume por id de sessão nativa → D23), `CAPABILITIES` por motor e driver
  `drive_turn` ligando evento→sessão→interação(D24), testado por `StubEngine` (PR em curso;
  detalhe/reflexão em [`N2-motores-de-coding.md`](N2-motores-de-coding.md)).
  ⏳ **PoC vivo pendente** (gate antes dos adapters reais): aprovação por ação no Codex (SDK grosso →
  talvez app-server cru) e ergonomia de pausa/retomada no Claude Code — precisam dos SDKs + auth.

### D23 · Identificadores session / execution / interaction (protocolo + auditoria)
- **Decisão (proposta):** três entidades de primeira classe — **session** (sessão de trabalho do
  motor), **execution** (= nosso `run`), **interaction** (pergunta/decisão pendente) — com IDs
  internos únicos + versão curta legível (S-…, E-…, Q-…). Preservar vínculos e o **id nativo** do
  motor sem confundir com o interno. IDs são **rastreabilidade, não credencial**. Entra como
  **migração `0002`**; **precede** a interação humana (D24).
- **Decisão:** ✅ **implementado** — migração 0002 + modelos + métodos de store (PR #26).

### D24 · Protocolo de interação humana (`request_human_input`) + roteamento por reply
- **Decisão (proposta):** capacidade comum `request_human_input` (pergunta/contexto/alternativas/
  resposta livre/ids/prazo). Pergunta sai pelo **outbox (D9)**; guarda-se o **`message_id`** do
  Telegram na `interaction`; resposta em *reply* resolve a interação → valida autz → entrega ao
  `EngineAdapter`. Estado `AWAITING_HUMAN` **=** `waiting` (sobrevive a restart; sweeper/lease).
  **Sem resposta ≠ aprovação.** Concorrência: **1ª resposta válida vence**; demais rejeitadas.
  Destino incerto → **pedir esclarecimento, nunca inferir**. Amarra H/D7/D15.
- **Decisão:** ✅ **implementado** — `request_human_input` + `handle_reply` (reply-routing por
  `message_id`, first-wins, WAITING/AWAITING_HUMAN) sobre o outbox (PR #27). Retomada = motor (D22).

### D25 · Console web operacional + terminal via tmux
- **Decisão (proposta):** console que mostra empresas/ambientes/execuções/sessões/interações/logs/
  custos e permite ações autorizadas (pausar/cancelar/retentar/reatribuir/pedir review) — **mesmo
  backend** do Telegram. Terminal no navegador (**ttyd/Wetty**) para diagnóstico: autenticado,
  isolado por empresa, **nunca exposto cru**; fechar a janela **não** encerra a execução (tmux é
  diagnóstico, não fonte do estado). Stack do front decidida no passo 5.
- **Decisão:** ✅ **API implementada** (Starlette, PR em curso): mesma store do Telegram; auth bearer
  + **isolamento por empresa** (run de outro tenant → 404); views de execuções/sessões/interações e
  ações cancelar/retentar; endpoint `terminal` devolve URL do ttyd (processo+proxy = **infra**, fora
  do código). Front rico (HTML/SPA) e o ttyd em si ficam para depois — a espinha (API) está pronta.

### D26 · Modelo de auditoria de execução (taxonomia de eventos) — *parcial*
- **Decisão (proposta):** além de `run_event` (D8) + `llm_call` (D10), registrar a **taxonomia de
  eventos** do §8 (tarefa/critérios, atribuição empresa-papel-agente-motor, início/fim, etapas/
  tentativas/estados, tool calls, comandos, erros de lint/test, recuperações, perguntas/respostas,
  aprovações, arquivos/commits/PRs, cancelamentos/timeouts), **correlacionada** aos IDs
  (empresa/tarefa/execution/session/interaction/attempt). ⚠️ **Fechar "Separação dos registros"
  (store quente vs log frio) quando o §8 chegar inteiro.**
- **Decisão:** ⬜

### D27 · Plano de controle multi-empresa (fleet manager) — camada acima do D17
- **Pergunta:** com várias empresas, dá pra ter uma imagem genérica que "gera" instâncias por
  empresa + um gerenciador com o registro e as configs de todas?
- **Decisão (proposta):** ✅ sim, mas **uma imagem genérica → N containers** (1 por empresa, D17),
  cada um parametrizado pela **config/vault da empresa** (o `load_config` já é 1 tenant por processo).
  **Não** se gera imagem por empresa (desperdício). Um **control-plane/manager** mantém o **registro
  de empresas** (repos, bot, ref do vault, orçamento, estado, saúde) e **provisiona/supervisiona** os
  containers via Docker API / compose / k8s; console pode ser multi-empresa pro operador. Detalhe em
  [`N4-controle-multiempresa.md`](N4-controle-multiempresa.md). **Pós-PoC** (o PoC valida 1 empresa primeiro).
- **Decisão:** ⬜

---

## Fora desta lista de propósito (medir no build, não decidir agora)
Baseline de custo por issue/PR · golden set de evals · latência da escada · mapa fino operação→tier.
Esses só existem com execução real — não travam o build.

---
Ao fechar §1 (+ aceitar §2), o próximo passo é a **aprovação de fase** (dono) → implementação na
ordem do `READINESS.md`.
