# Breakdown de épico (refino destrincha épico em sub-issues)

> **Em construção** — feature #203. O refino/definição de issue é o **coração do fleet**; esta
> trilha o ensina a reconhecer um **épico** e destrinchá-lo **ponto a ponto** em sub-issues
> **esqueleto**, conversando com o humano nas dúvidas e encadeando por dependência.

## Visão

Hoje o refino é **1→1** (um pedido → uma issue). Um épico é largo demais para uma issue só. A ideia:

1. **Detectar** que a issue é um épico (heurística determinística — não decisão cega de LLM).
2. Entrar em **modo breakdown**: propor **N sub-issues leves** (título + pontos a cobrir), a decisão
   do destrinchar **conversada** com o humano.
3. **Pesquisar na web** quando o texto não basta (validar lib/versão, abordagem) e citar a fonte.
4. Perguntar (`PERGUNTA:`) o que não dá pra inferir de texto/pesquisa.
5. Com **OK humano**, materializar as sub-issues no GitHub **encadeadas** (`Depende de #N`), linkadas
   ao épico. Cada uma é **refinada a fundo 1-a-1** depois, quando for a vez.

O encadeamento pluga direto no **gate de dependência** ([`app/deps.py`](../trilha-j-escala.md)):
a sub-issue `Depende de #N` fica em `WAITING` até a anterior fechar. E o **DoR gate** garante que um
esqueleto não é implementado antes de ser refinado — a própria falta de DoR puxa a conversa 1-a-1.

```mermaid
flowchart TB
  R[refino conversa] --> D{é épico?}
  D -->|não| One([1 issue, fluxo normal])
  D -->|sim| B[modo breakdown: N esqueletos]
  B --> Q{dúvida?}
  Q -->|sim| P[PERGUNTA / pesquisa web] --> B
  Q -->|não| OK{OK humano?}
  OK -->|sim| M[cria N sub-issues encadeadas - Depende de #N]
  M --> L[gate segura em ordem · DoR puxa refino 1-a-1]
```

## O que já existe (incrementos 1–2)

**Incremento 1 — base determinística** em [`agents/breakdown.py`](https://github.com/CenturyBoys/roboto/blob/main/src/roboto/agents/breakdown.py):

- **`is_epic(title, body)`** — heurística: "épico"/"epic" como palavra no título é sinal forte;
  senão soma sinais do corpo (palavra épico, ≥8 checkboxes, ≥3 cenários/critérios, menção a
  breakdown) e decide por ≥2 sinais. "epicentro" **não** dispara (casamento por palavra).
- **`parse_breakdown(text)`** — lê o formato que o motor emite (`ITEM:` + pontos `- `). Resolve a
  dependência de cada item: `DEPENDE: nenhuma` (independente), `DEPENDE: #N` (dependência **NOMEADA**
  de um item anterior → forma um **DAG raso**, não uma fila) ou ausente/`da anterior` (encadeia no
  anterior). Índice nomeado inválido cai no default conservador.
- **`skeleton_body(item, dep_number)`** — monta o corpo do esqueleto; `dep_number` é o número real já
  resolvido (encadeamento simples **ou** DAG), e a frase `Depende de #N` é a mesma que o gate
  `blocked_by` reconhece. Além do bloco `🔎 Pesquisa`, **auto-injeta blocos por DIMENSÃO** da
  sub-issue (🎭 Jornada & UI, 🗄️ Migração, 🔒 Garantias transversais) — a cobertura vira estrutural.

**Incremento 2 — modo breakdown conversacional** em `agents/refiner.py`:

- **`breakdown_converse(transcript, gateway)`** — passo multi-turno (espelha o `converse()` do
  refino normal): devolve uma **pergunta** (`PERGUNTA:`) quando falta info, ou o **breakdown**
  (lista de esqueletos já encadeados) quando dá pra propor.
- **`BREAKDOWN_SYSTEM`** — o contrato do prompt: dependência **nomeada** (`DEPENDE: #N`, grafo e não
  fila), **um item = uma responsabilidade** (não funde concerns; bug nomeado vira item próprio),
  épico arquitetural começa por **pesquisa + ADR** (com garantias transversais e testes de
  durabilidade), épico com **usuário final** exige ≥1 item de **UI/jornada**, e doc "antes de
  implementar" **não** é o último item. Também **instrui a pesquisar na web** citando a fonte.

**Incremento 3 — materializar no GitHub** em `app/breakdown_apply.py`:

- **`materialize_breakdown(github, repo, epic_number, breakdown)`** — cria as sub-issues **em ordem**,
  cada uma com `Depende de #<número real da anterior>` (números que só existem após criar → criação
  sequencial) + `Parte do épico #N`. Comenta no épico o **índice** das filhas (guarda-chuva).
- **Encadeamento real:** a dependência aponta pro número GitHub de fato, então o gate `blocked_by`
  já segura cada filha em WAITING até a anterior fechar. `DEPENDE: nenhuma` no meio não encadeia.
- **Fail-fast:** para na 1ª falha de criação (não deixa cadeia pela metade silenciosa); as já criadas
  permanecem e aparecem no comentário do épico.

**Incremento 4 — cockpit (endpoints + painel)**:

- **`POST /issues/{n}/breakdown`** (propor) — checa `is_epic`, roda `breakdown_converse` semeado com
  título+corpo do épico, devolve `{question}` **ou** `{items}` — **sem criar nada** (409 se não parece
  épico).
- **`POST /issues/{n}/breakdown/apply`** (materializar) — recebe os itens **confirmados/editados pelo
  humano** e chama `materialize_breakdown`. Só cria o que o painel enviou (OK humano no código).
- **Painel `BreakdownPanel`** no refino: botão *Destrinchar épico* → lista editável (título, pontos,
  "depende da anterior") → *Criar N sub-issue(s)*; mostra os links das filhas criadas. O *Destrinchar*
  nunca cria; a criação é um segundo clique explícito.

**Incremento 5 — rascunho durável** (sobrevive a F5 e troca de dispositivo):

- Tabela `breakdown_draft` (migration 0011), chave `(tenant, repo, issue)`, 1 linha por épico (upsert);
  métodos no `Store` (InMemory + Postgres).
- **`GET/PUT/DELETE /issues/{n}/breakdown/draft`** — ler / salvar / descartar. O `apply` **apaga** o
  rascunho ao materializar (não reabre uma proposta já criada).
- UI: o `BreakdownPanel` **restaura** o rascunho ao abrir, faz **autosave** a cada edição, e tem
  **descartar rascunho**. Agora dá pra propor, sair, dar F5 (ou trocar de máquina) e voltar pra
  finalizar — a proposta editada continua lá.

**Incremento 6 — dimensões de cobertura + DAG + gate determinístico** (refino do próprio processo):

Revisão de um destrinchamento real (épico #73 do arenavalendo, em 3 lentes: arquitetura de software,
de sistema e UX) mostrou que os defeitos eram **do processo**, não do épico: cadeia 100% serial,
dimensões (UX, idempotência, testes duráveis) virando "bala solta" dentro de features, e itens
inchados. As correções tornam a cobertura **estrutural**, não dependente do motor lembrar:

- **Dependência NOMEADA (DAG):** `SubIssueSkeleton.depends_on_index` + `DEPENDE: #N` no parser e
  resolução no `materialize_breakdown` — pendura cada item no antecessor REAL (não na fila), sem
  serializar trabalho paralelizável nem empurrar transversais pro fim.
- **Detectores de dimensão** em `breakdown.py`: `is_architectural()` (ADR/durável/idempotência/
  scheduler/"se sobrepõe a #") e `needs_ux()` (usuário final: tela/notificação/jornada/PWA).
- **Gate de cobertura `review_breakdown(title, body, breakdown)`** — determinístico, **não bloqueia**:
  avisa o humano o que o destrinchamento provavelmente deixou passar (épico arquitetural sem
  pesquisa/ADR, épico com usuário sem UI/jornada, doc de fluxo como último item, sub-issue inchada).
- **Seeding por dimensão** no `skeleton_body`: itens de UI/schema/durável ganham checklists prontos
  (jornada/notificações, migração/backfill, idempotência/ownership/testes de crash-restart).
- **Cockpit:** `POST /issues/{n}/breakdown` devolve `warnings`; o `BreakdownPanel` os mostra num
  painel âmbar **antes** de criar — o operador revisa a cobertura e decide.

## Próximo

7. Dogfood: destrinchar um épico real (ex.: #73 do arenavalendo) pela UI, revisar os avisos de
   cobertura e materializar.
