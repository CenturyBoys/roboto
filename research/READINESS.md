# Prontidão para implementação — revisão final

> Fase: PESQUISA (revisão final). Avalia se a pesquisa está pronta para virar **build** e o que
> falta fechar antes. Não troca de fase — isso é decisão explícita do dono.

## Veredito

A pesquisa está **coerente, ampla e auditada** (14 trilhas, SYNTHESIS, C4, 4 rodadas de auditoria
independente). O *desenho conceitual* fecha. **Porém, não é "buildável" ainda** por dois motivos:
(1) faltam ~6 **decisões-fundação** que bloqueiam código; (2) a peça mais central — **Orquestrador +
persistência** — está desenhada em alto nível mas **pede um passo de design mais fundo** antes de
implementar. Além disso, três temas **novos** apareceram nesta revisão e merecem uma nota antes do build.

## O que está sólido (não re-pesquisar)

Princípios-guia · taxonomia do fleet (Trilha 0) · contratos de trabalho/DoR/DoD/estados (A) ·
gatilhos e taxonomia reativo/ambiente (B) · design de skills + progressive disclosure (C) · review
multi-agente com reviewer≠autor (D) · AGENTS.md "como" + naming (E) · ferramentificação + roteamento
de busca (F) · memória file-first storage≠search (G) · princípio "output=proposta, política decide"
+ evals + segurança (H) · escada de validação + OpenRouter + chineses (I) · escala/merge-queue/test-impact (J) ·
runtime efêmero + isolamento (K) · modelo de custo (L) · observabilidade/Telegram/checkpoint (M).

## Lacunas antes do código

### A. Decisões-fundação a fechar (bloqueiam build)
| # | Decisão | Trilha | Dono |
|---|---------|--------|------|
| 1 | **Stack do `roboto`** (linguagem/framework) — destrava comandos, linter, test-impact, base do runner | E/J/K | dono |
| 2 | **Escopo + ordem do MVP** (quais agentes/skills primeiro) | 0/C | dono |
| 3 | **Plataforma de observabilidade** (self-host vs SaaS) — escolha única, consumida por M/L | H | dono |
| 4 | **Secrets**: Vault/OpenBao vs token OIDC curto do GitHub | K | dono |
| 5 | **Checkpoint**: leve (issue+git+journal) vs durable execution engine no MVP | M | dono |
| 6 | **Orçamento**: teto token/$ por tipo de agente + catálogo de ações que exigem gate humano | L/H | dono |

### B. Entender melhor (1 passo de design mais fundo — não é "mais pesquisa de mercado")
- **Orquestrador + persistência** é a peça menos especificada e mais central. Precisa de um design
  concreto de: ciclo de vida do run/turno (máquina de estados **no banco**), **idempotência**
  (chave + "reconferir dentro do lock" — não basta deduplicar na entrada), serialização por
  issue/PR, e **varredura** de run abandonado (processo morto no meio). Hoje B/M cobrem isso por
  cima. *(inspiração direta do padrão de turno do exemplo viva.)*

### C. Medir durante o build (não dá pra pré-fabricar — não trave o build por isso)
- **Baseline de custo** token/$ por issue/PR (L) — só existe com execução real.
- **Golden set de evals** (H) — começa de casos curados/sintéticos e refina com falhas reais.
- **Latência** da escada encadeada (I/M) e **mapa operação→tier** (I) — medir e calibrar.

## Faltou pesquisar? (temas novos desta revisão — valem uma nota curta antes/junto do build)

1. **Esquema de auditoria `llm_call`** — registrar por chamada: tokens, custo, latência, **versão de
   prompt e de AGENTS.md/guia**. É o que torna L (custo) e H (observabilidade/reprodutibilidade)
   *verificáveis*. Hoje falamos "custo por run" sem o registro concreto. **Novo — adicionar.**
2. **Outbox / efeitos exactly-once** — ações com efeito colateral (abrir PR, notificar Telegram,
   mandar evento) precisam de **gravar→commit→publicar** com dedupe do outro lado, senão falha no
   meio deixa estado e efeito fora de sincronia. Toca B (idempotência) + M (Telegram/estado).
   **Novo — adicionar (padrão outbox).**
3. **Versionamento de prompt/guia por run** — qual AGENTS.md/prompt rodou em cada turno (liga ao #1).
   **Novo — adicionar.**

> Esses três não são "pesquisa de mercado" — são **design**, e cabem num único incremento da Trilha
> B/H/M. O exemplo viva mostra os três resolvidos (máquina de estados no banco, outbox, `agent_audit`).

## Ordem de implementação sugerida (MVP, quando o dono aprovar a fase)

1. **Fundação**: stack + repo scaffolding + `AGENTS.md` v1 + CI determinístico (tier 1) + schemas
   (issue state, `llm_call` audit, outbox, índice de memória) + secrets.
2. **Orquestrador mínimo**: webhook→dedupe→dispatch→runner efêmero; estado no banco + varredura.
3. **Loop núcleo**: Refinamento (+gate de prontidão) → Implementação → PR → **CI** → Review(≠autor) → DoD.
4. **Gateway + escada**: OpenRouter + 1 modelo barato + Claude frontier; Jev como judge/guardrail.
5. **Humano**: Telegram (aviso+aprovação revalidada) + dashboard de observabilidade.
6. **Segurança (ambiente)** e **checkpoint** depois do loop estável; SRE/Incidente só com produção.

## Como seguir
- Fechar as 6 decisões-fundação (A) — a maioria é só o dono dizer.
- Um incremento de design para (B) + os 3 temas novos — eu escrevo como extensão de B/H/M.
- (C) fica explicitamente como "medir no build", não bloqueia.
- Então: **aprovação de fase** (dono) → implementação na ordem acima.

## Revisão da jornada — spec de operação interativa (2026-10-19)

O doc do dono (incorporado na **[Trilha N](N-operacao-interativa-e-motores.md)**) adiciona 6 decisões
(**D21–D26**) que **estendem** a ordem acima — não a substituem:

- **Passo 1 (Fundação):** ✅ feito. **Passo 2 (Orquestrador):** núcleo + **PgStore** ✅ feito;
  falta **GitHub App** (transporte) + **D21** (bot↔empresa) + wiring do **outbox** (issue como verdade).
- **Passo 2.5 (novo):** **D23** — migração `0002` com `session`/`execution`/`interaction` + mapa de
  sessão nativa. **Precede** interação humana.
- **Passo 3 (Loop núcleo):** **D22** (EngineAdapters Codex/Claude Code, **após PoC**) + **D24**
  (`request_human_input` + roteamento por reply). O Refinamento (agente já criado) materializa a issue.
- **Passo 5 (Humano):** **D25** console web + terminal tmux.
- **Transversal:** **D26** auditoria (taxonomia de eventos ligada aos IDs).

**Gating do passo 3:** PoC de capacidades dos motores (D22) antes de fixar o contrato do adapter.
