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
- **Decisão:** ⬜

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
- **Decisão:** ⬜

---

## §2 · Design a escrever (proposta — eu redijo como extensão das trilhas)

### D8 · Orquestrador + persistência (passo de design mais fundo)
- **Proposta:** **máquina de estados do run no banco**; idempotência por `head_sha+evento+nº`
  **com "reconferir dentro do lock"** (não só dedupe na entrada); serialização por issue/PR;
  **varredura** de run abandonado (estado gravado antes da chamada externa). Padrão do turno do viva.
- **Decisão:** ⬜ (aceitar que eu escreva este design na Trilha B)

### D9 · Outbox / efeitos exactly-once
- **Proposta:** ações com efeito colateral (abrir PR, notificar Telegram, publicar evento) via
  **gravar → commit → publicar**, com dedupe do consumidor. Dissolve "morreu no meio" (estado sem efeito
  / efeito sem estado). Toca B (idempotência) + M (Telegram/estado).
- **Decisão:** ⬜ (adotar outbox?)

### D10 · Esquema de auditoria `llm_call`
- **Proposta:** registro por chamada de modelo: `tokens, custo, latência, modelo/provedor,
  versão de prompt, versão de AGENTS.md/guia, run/issue`. É o que torna **custo (L)** e
  **observabilidade/reprodutibilidade (H)** verificáveis.
- **Decisão:** ⬜ (adotar + onde mora)

### D11 · Versão de prompt/AGENTS.md por run
- **Proposta:** carimbar em cada run qual prompt/AGENTS.md rodou (liga ao D10) → "qual regra falou no
  run X" sem reconstruir histórico.
- **Decisão:** ⬜

---

## §3 · Afinações de trilha (dá pra decidir ao implementar)

### D12 · Issue types + sub-issues nativos vs labels; Projects dentro ou fora
- **Proposta:** **issue types + sub-issues nativos** do GitHub; **Projects fora** no MVP (estado via
  labels/status), reavaliar como visualização depois.
- **Decisão:** ⬜

### D13 · Adotar GitHub Spec Kit como ferramenta de spec?
- **Pontos de vista:** *Sim* (padrão pronto Constitution→…→Implement, menos reinvenção) · *Não*
  (nossa DoR/DoD já cobre; menos dependência).
- **Proposta:** **usar as ideias do Spec Kit** (spec versionada = issue), **sem acoplar à ferramenta** no MVP.
- **Decisão:** ⬜

### D14 · Onde as skills vivem + versionamento
- **Proposta:** `.claude/skills/` no `roboto`, **versionadas e revisadas por composição** (CompoSkill);
  plugin/compartilhamento depois.
- **Decisão:** ⬜

### D15 · Canal canônico de aprovação
- **Proposta:** **GitHub é o canônico** (review/estado da issue); **Telegram = atalho revalidado no servidor**.
- **Decisão:** ⬜

### D16 · Mix de modelos por etapa (provedor barato inicial)
- **Proposta:** começar com **1 modelo chinês/aberto barato** (ex.: um de coding forte) para geração +
  **Claude frontier** no difícil + **Jev** no judge; **pinar por medição** (não por leaderboard).
- **Decisão:** ⬜ (ou deixar 100% para "medir no build")

---

## Fora desta lista de propósito (medir no build, não decidir agora)
Baseline de custo por issue/PR · golden set de evals · latência da escada · mapa fino operação→tier.
Esses só existem com execução real — não travam o build.

---
Ao fechar §1 (+ aceitar §2), o próximo passo é a **aprovação de fase** (dono) → implementação na
ordem do `READINESS.md`.
