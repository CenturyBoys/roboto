# RFC — UI/UX do Cockpit (Potter console) — trilha O

> **Status:** proposta · **Escopo:** `web/ui/` (React + TS + Tailwind v4 + primitivos tipo shadcn)
> **Objetivo:** subir o cockpit de "funcional e cru" para "torre de controle que dá gosto de usar",
> sem reescrever — evoluindo a base que já existe (tokens `@theme`, `ui/` primitives, feed SSE).

## 1. Contexto

O cockpit já tem fundação boa: Tailwind v4 com tokens semânticos (`bg-surface`, `text-muted`,
`--color-accent`…), primitivos em `components/ui/` (`button`, `card`, `state-pill`, `table`,
`tool-activity`), feed ao vivo por SSE, markdown renderizado. O que falta é **disciplina visual e de
estado**: hierarquia, feedback de ação, estados de vazio/carregando/erro, e navegação. Este RFC fixa
**regras** (pra qualquer tela nova já nascer certa) e um **plano por fatias**.

## 2. Não-objetivos

- Não trocar o stack (fica React/TS/Tailwind + primitivos tipo shadcn/Radix).
- Não virar "bonito e inútil": é ferramenta de operador (power-user), densidade é bem-vinda **quando deliberada**.
- Não redesenhar tudo de uma vez — fatias pequenas, cada uma entregável.

## 3. As 10 regras básicas (o contrato de UI)

Toda tela/PR de front **segue estas regras** (viram item de DoD, §8):

1. **Hierarquia por peso e cor, não por tamanho.** Título grande só quando é o assunto da tela; o
   resto diferencia com `font-weight` e `text-muted`/`text-foreground`. (Refactoring UI)
2. **Escala de espaçamento fixa** — use só 4/8/12/16/24/32/48 (os utilitários do Tailwind). Nada de
   valores arbitrários. **Espaço ENTRE grupos > espaço DENTRO do grupo.**
3. **Cinza primeiro, cor com parcimônia.** O amarelo (`--color-accent`) é **sinal**, não decoração:
   reservado para o item ativo, a ação primária e o destaque-chave. Máx. 1 acento por bloco.
4. **Todo estado visível (Nielsen #1).** Nada "acontece em silêncio": ação dispara feedback imediato
   (toast/`Saved`/spinner no botão), e processos longos (motor rodando) mostram progresso vivo.
5. **4 estados por view, sempre:** `vazio` (explica + próxima ação), `carregando` (skeleton que
   espelha o layout), `erro` (diz o quê + como recuperar), `parcial`. O "happy path" é 1 de 4.
6. **Reconhecer, não lembrar (Nielsen #6).** Ações e estados legíveis sem decorar: rótulos claros,
   ícones com texto, `state-pill` com cor+label. Sem jargão interno cru na tela.
7. **Ação primária única e óbvia por tela.** Uma `Button variant=default` (acento); o resto é
   `outline`/`ghost`. Ação destrutiva pede confirmação (Nielsen #5, prevenção de erro).
8. **Contraste e teclado (WCAG 2.1 AA).** Texto ≥ 4.5:1, texto grande ≥ 3:1; `focus-visible`
   preservado; navegável por teclado (herdar do Radix, não recriar). `text-muted` só em texto
   secundário — nunca em informação crítica.
9. **Consistência de componente (Nielsen #4).** Botão/card/tabela/pill vêm de `components/ui/` —
   zero `<button>`/`<table>` solto. Novo padrão? Vira primitivo antes de repetir.
10. **Minimalismo (Nielsen #8).** Cada elemento ganha o lugar. O que não é operação vai pra um menu
    (ex.: token/config) — a tela principal é operação, não configuração.

## 4. Heurísticas de Nielsen — checklist aplicado ao cockpit

| # | Heurística | Onde aplicar no cockpit |
|---|---|---|
| 1 | Visibilidade do status | run `running` com feed vivo + tempo decorrido; "salvando…"; conexão SSE |
| 2 | Mundo real | "Execução", "Issue", "Revisar PR" (ok); evitar `queued/verifying` crus → rótulos PT + tooltip |
| 3 | Controle e liberdade | cancelar/interromper run; voltar sem perder contexto; desfazer onde der |
| 4 | Consistência | tudo via `ui/` primitives; mesmo padrão de tabela/estado em todas as abas |
| 5 | Prevenção de erro | confirmar ações destrutivas (cancelar run, aplicar na issue); validar token antes |
| 6 | Reconhecer > lembrar | `state-pill` colorido; ícones+texto; breadcrumb nas telas de detalhe |
| 7 | Flexibilidade | atalhos de teclado; filtro/busca nas listas (issues já tem) |
| 8 | Minimalista | tirar o input de token do topo; densidade deliberada, não poluição |
| 9 | Recuperar de erro | estado de erro com mensagem humana + botão "tentar de novo" (retry já existe no back) |
| 10 | Ajuda | microcopy ("revisão do fleet, revisor≠autor"); tooltips nos estados |

## 5. Estado atual — crítica honesta

Fundamentado no que roda hoje (`web/ui/src/`):

- ✅ **Bom:** tokens semânticos; `state-pill`/`tool-activity`; feed SSE; markdown; PWA/offline.
- ⚠️ **Token no topo, fixo.** O `CONSOLE_TOKEN` + "salvar token" ocupa a barra principal — é
  configuração (e segredo) no lugar de operação. Vai pra um menu/avatar (regra 10).
- ⚠️ **Hierarquia fraca.** Tabelas em mono/muted sem âncora visual; difícil varrer. Falta "o número
  grande, o contexto pequeno" (ex.: estado em destaque, metadados discretos).
- ⚠️ **Estados faltando.** Pouco/zero skeleton (regra 5); vazios sem orientação ("nenhuma issue" vs.
  "nenhuma issue — configure o GitHub / crie uma"); erros às vezes viram texto cru.
- ⚠️ **Feedback de ação.** Clicar "Revisar PR"/"Aplicar" não dá retorno visível na própria tela
  (você mesmo perguntou "cliquei e não apareceu nada") — falta toast/estado inline. **(Nielsen #1)**
- ⚠️ **Navegação plana.** Pills lado a lado sem hierarquia; detalhe de execução sem breadcrumb claro.
- ⚠️ **Densidade acidental.** Informação espremida sem agrupamento (regra 2: espaço entre grupos).

## 6. Proposta — por fatias (cada uma entregável e testável)

**Fatia 1 — Fundamentos invisíveis (base pra tudo):**
- Padronizar escala de espaçamento + um `PageHeader`/`Section` com título+ação primária.
- `EmptyState`, `Skeleton`, `ErrorState`, `Toast` como primitivos em `ui/`.
- Mover token/config pra um menu (ícone no canto); barra principal = navegação only.

**Fatia 2 — Estados em toda view:** aplicar os 4 estados (regra 5) em Execuções, Issues, Custos,
Interações. Skeleton espelhando o layout final; vazios com próxima ação; erro com "tentar de novo".

**Fatia 3 — Feedback de ação (Nielsen #1):** toast em toda ação (Aplicar/Revisar/Implementar/
Cancelar); botão com estado `…` (já há em alguns); confirmação em destrutivas.

**Fatia 4 — Hierarquia & leitura:** tabelas com âncora (estado como `pill` colorido, nº da issue em
destaque, metadados em `muted`); "número grande, contexto pequeno" nos Custos e no detalhe de run.

**Fatia 5 — Navegação & contexto:** breadcrumb nas telas de detalhe; estado ativo claro na nav;
tempo decorrido/"ao vivo" no run `running`; atalhos de teclado (`j/k`, `/` pra buscar).

**Fatia 6 — Acabamento:** auditoria de contraste (AA), `focus-visible` em tudo, microcopy/tooltips,
densidade revisada (agrupar com espaço).

## 7. Design System (a camada durável: tokens → primitivos → padrões)

Design system **não é "uma pasta de componentes"** — são **4 camadas com governança**. É o que faz
tela nova nascer consistente sem redecidir tudo (regra 9) e sobreviver a troca de dev/motor.

**Camada 1 — Tokens (fonte da verdade visual).** Cor = **papel**, não aparência. Manter os
semânticos (`background/surface/foreground/muted/accent/border`) e **acrescentar tokens de estado**
(`success/warning/danger/info`) — hoje verde/vermelho/amarelo aparecem como **hex solto** em classes.
Espaçamento/raio/tipografia já herdados do `@theme` do Tailwind. Acento é **sinal** (ativo/primário/
destaque), nunca decoração.

**Camada 2 — Primitivos (headless + acessível).** O que vive em `components/ui/`. Hoje: `button`,
`card`, `state-pill`, `table`, `tool-activity`. **Faltam (fatia 1):** `EmptyState`, `Skeleton`,
`ErrorState`, `Toast`, `Dialog`/`ConfirmDialog`, `Menu` (pro token/config sair do topo), `Tooltip`,
`Tabs`, `FilterChips`, `Field`/`Input`. Interação complexa (menu/dialog/tooltip) = **Radix/shadcn**
(foco, ARIA, teclado de graça) — não reimplementar (regra 8).

**Camada 3 — Padrões (composições recorrentes).** Receitas feitas com primitivos: `ListView` (busca
+ filtros + 4 estados + tabela/cards), `DetailView` (breadcrumb + header + seções), `ActionButton`
(estado `…` + toast), `SummaryCards` (métrica grande / contexto pequeno). É aqui que **filtros &
cards (§8)** viram peça reutilizável.

**Camada 4 — Telas.** Execuções, Issues, Custos… montadas **só** com as camadas 1–3. Zero
`<button>`/`<table>`/hex solto numa tela (regra 9).

**Documentação & governança:**
- **Inventário vivo:** index dos primitivos/padrões (um `ui/README.md` ou Storybook leve) — consultar
  antes de inventar.
- **Regra do "3º uso":** repetiu 3×? Vira primitivo/padrão. Antes disso, compõe local.
- **Versão junto do código** (`web/ui/`): mudança de token é PR revisado (um token errado quebra
  contraste em todo lugar).
- **Lint `check:ui`** (espelho do `check:tokens` do repo-alvo): barra hex solto / primitivo não usado.

## 8. Filtros & cards (aterrado nos dados que a API JÁ expõe)

Regra de ouro: **só ofereça filtro para dado que a API retorna** — senão é promessa quebrada. O que
temos hoje por view:

**Execuções** (`/executions` → `id, repo, issue_id, agent, state, attempt, created_at, updated_at`):
- Filtros (dado já existe): **Estado** (queued/running/waiting/verifying/done/failed/abandoned) em
  chips multi-seleção; **Agente** (refine/impl/review/scope/triage); **Repo** (quando N repos);
  **busca** por nº da issue.
- Ordenar por recente (`updated_at`); **ativos no topo** (running/waiting em destaque).
- Backend: nada a fazer — tudo já vem. (Se a lista crescer, migrar o filtro pra server-side via query param.)

**Issues** (`/issues` → `number, title, labels`):
- Já há busca por nº/título/label (manter) → acrescentar **chips de label** (derivados dos presentes).
- **DoR pronta / incompleta**: o dado **NÃO vem na lista** hoje (só no detalhe). Para virar filtro, o
  backend precisa rodar `check_issue_readiness` por issue na listagem (determinístico, barato). É o
  filtro **mais útil** pro operador — recomendo priorizar.
- Estado open/closed: hoje a lista é só `open`; se expuser closed, vira filtro.

**Custos** (`/costs` → `run_id, model, tier, tokens_in/out, cost_usd, at`):
- Filtros: **tier** (cheap/judge/frontier), **modelo**, **execução**, **período** (`at`).
- **Cards de topo** (métrica grande, contexto pequeno — Refactoring UI): `$ total`, `tokens total`,
  `$ médio por execução` — já dá com `totals` + `by_execution`.

**Dead-letter** (`/dead-letter` → `source, kind, attempts`): filtros por **source** (effect/run) e **kind**.

### Cards — quando usar
- **Card = unidade escaneável** (uma execução, uma issue, um item). Composição: **1 âncora** (estado
  como `pill` colorido OU nº em destaque) + metadados em `muted` + no máx. **1 ação primária**.
- **Tabela** para varrer muitos itens homogêneos; **card** quando cada item tem status + ações (ex.:
  Interações pendentes / inbox de HITL). Densidade é decisão por contexto (regra 2), não default.
- Topo de cada view: **cards-resumo** com os números que importam (ativos, falhas, $ do dia).

### Princípio transversal dos filtros
Filtro que não muda nada visível é ruído. Todo filtro deve: (a) refletir no estado/URL (voltar não
perde), (b) mostrar **contagem** ("12/40"), (c) ter **"limpar"**, (d) ter **vazio-por-filtro**
distinto do vazio-real ("nenhuma execução **falhada**" ≠ "nenhuma execução").

## 9. DoD de front (como a gente garante)

Todo PR que toca `web/ui/` precisa:
- [ ] usar só primitivos `ui/` (sem `<button>`/`<table>`/hex solto);
- [ ] cobrir os **4 estados** da view que tocou (vazio/carregando/erro/parcial);
- [ ] dar **feedback visível** nas ações que dispara;
- [ ] respeitar a escala de espaçamento e **1 ação primária** por tela;
- [ ] passar contraste AA e manter `focus-visible` + navegação por teclado;
- [ ] (opcional, recomendado) um lint `check:ui` espelhando o `check:tokens` do repo-alvo.

## 10. Referências

- Refactoring UI (Wathan & Schoger) — hierarquia, espaçamento, cor:
  [resumo](https://www.sglavoie.com/posts/book-summary-refactoring-ui/) ·
  [top 20](https://medium.com/design-bootcamp/top-20-key-points-from-refactoring-ui-by-adam-wathan-steve-schoger-d81042ac9802)
- Nielsen Norman — 10 heurísticas de usabilidade:
  [NN/g heurísticas](https://www.humanstandards.org/interaction-patterns/nielsen-heuristics/)
- Dashboard UX 2026 — densidade, estados, skeletons:
  [princípios](https://www.uxpin.com/studio/blog/dashboard-design-principles/) ·
  [loading states](https://kompassify.com/blog/loading-state-ux-guide) ·
  [best practices 2026](https://5of10.com/articles/dashboard-design-best-practices/)
- shadcn/Radix + WCAG (tokens, contraste, teclado):
  [acessibilidade shadcn](https://shadcnstudio.com/blog/making-your-website-accessible-with-shadcn-ui/) ·
  [Radix/ARIA](https://eastondev.com/blog/en/posts/dev/20260330-shadcn-radix-accessibility/)
- Design system — camadas (tokens → primitivos → padrões → telas) e governança:
  [Atomic Design (Brad Frost)](https://atomicdesign.bradfrost.com/chapter-2/) ·
  [Radix Colors (escala + contraste garantido)](https://www.radix-ui.com/colors)
