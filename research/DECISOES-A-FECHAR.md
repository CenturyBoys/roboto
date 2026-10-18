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
- **Decisão:** ⬜

### D6 · Orçamento (token/$)
- **Pontos de vista:** *Teto global* (R$550/mês de API) simples de controlar · *Budget por issue*
  exige baseline medido (ainda não existe).
- **Proposta:** **Teto global = R$550/mês**, roteamento barato-primeiro (Jev/chineses) + alerta em 80%;
  **budget por issue** entra depois da 1ª medição (fica como "medir no build").
- **Decisão:** ⬜

### D7 · Catálogo de ações com gate humano obrigatório
- **Pontos de vista:** *Lista curta* (só irreversível) = mais autonomia, mais risco · *Lista longa* =
  seguro, mas recria gargalo humano.
- **Proposta (lista inicial):** **merge, deploy, mudança de credencial, decisão arquitetural,
  resolução de conflito de merge, ação destrutiva.** O resto é `allow`/`deny` determinístico
  (jev-guard), com amostragem dos `allow` de baixo risco.
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
