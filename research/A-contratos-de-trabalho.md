# Trilha A — Contratos de trabalho (épico / issue / DoR / DoD / estados)

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)
>
> ✅ **Decidido** (ver `DECISOES-A-FECHAR.md`): issue types + sub-issues nativos; **Projects fora** no
> MVP (estado via labels) (D12); usar **ideias do Spec Kit** sem acoplar à ferramenta (D13).

## Pergunta

O que é um épico, uma issue e uma task bem definidos; o que é "Definition of Ready" (DoR) e
"Definition of Done" (DoD) **executáveis por agente**; e qual a máquina de estados da issue —
de forma que o agente trabalhe **sem sessões gigantes de contexto**.

## Grounding — spec-driven development (SDD) / GitHub Spec Kit

O padrão que o mercado convergiu em 2026: **a especificação versionada é a fonte da verdade**,
não o código nem o prompt. É a "unidade de governança" entre agentes (Copilot, Claude Code, etc.).
O GitHub Spec Kit implementa SDD num pipeline de 7 fases:

`Constitution → Specify → Clarify → Plan → Analyze → Tasks → Implement`

Princípio crítico do SDD (e que reforça o nosso "determinismo primeiro"):
**a verificação de cada checkpoint NÃO pode ser delegada ao agente que produziu o artefato** —
quem gera não valida a si mesmo. (Fontes no fim.)

### Mapeamento Spec Kit → nosso fleet (Trilha 0)

| Fase SDD | Artefato | Agente/mecanismo nosso |
|----------|----------|------------------------|
| Constitution | Princípios/convenções | `AGENTS.md` (Trilha E) — determinístico |
| Specify | Spec funcional (= corpo da issue) | Agente de **Refinamento** |
| Clarify | Resolver ambiguidade | DoR + gate humano quando preciso |
| Plan | Arquitetura/data model | Agente de **Arquitetura/Planejamento** |
| Analyze | Consistência entre artefatos | Check determinístico + judge barato (Jev, Trilha I) |
| Tasks | Decomposição em issues/subtasks | Agente de **Planejamento** |
| Implement | Código | Agente de **Implementação** |

## Taxonomia de trabalho

- **Épico** = uma *spec de feature/capacidade*. Grande demais para um PR; agrega issues. Tem
  objetivo de negócio, critério de sucesso macro e um conjunto de issues filhas.
- **Issue** = a *unidade executável por um agente num loop issue→PR*. Deve ser **INVEST**
  (Independente, Negociável, Valiosa, Estimável, Small, Testável). Carrega sua própria mini-spec.
- **Task/Subtask** = passo interno de uma issue quando necessário (checklist dentro da issue),
  não um item de primeira classe no board.

Mapeamento no GitHub (objeto de estudo): **issue types** (Epic/Feature/Task), **sub-issues**
(hierarquia nativa), **task lists** para subtasks, e **Projects status field** para o estado.

## Definition of Ready (DoR) — issue executável por agente

Uma issue só entra em `ready` quando é **self-contained** (o agente não precisa reabrir contexto):
- [ ] **Contexto** suficiente (links para a spec/épico, arquivos/área prováveis do código).
- [ ] **Objetivo** claro (o "porquê").
- [ ] **Critérios de aceite testáveis** (preferencialmente expressáveis como teste — determinismo primeiro).
- [ ] **Escopo e não-escopo** explícitos.
- [ ] **Dependências** declaradas (bloqueios → grafo de dependências, Trilha J).
- [ ] **Tamanho** cabe num PR (se não, quebrar — é épico/múltiplas issues).
- [ ] **Restrições** (perf, segurança, dados — ex.: SQL complexo não cabe em ORM, ver Trilha 0).

> DoR é o gate que troca "sessão gigante" por "issue densa". Quanto melhor a DoR, menos token na execução.

## Definition of Done (DoD) — preferencialmente determinística

Uma issue vira `done` só quando (quase tudo é check de máquina, não julgamento de LLM):
- [ ] Critérios de aceite atendidos e **verificados por teste**.
- [ ] **CI verde**: lint + type-check + build + testes (gate determinístico).
- [ ] Cobertura mínima na área tocada.
- [ ] **Review aprovado** — por agente **diferente** do que implementou (regra SDD de não auto-validar) + gate humano onde definido (Trilha H).
- [ ] Docs atualizadas se a mudança for observável (Trilha 0 — Documentação).
- [ ] Sem regressão de segurança (scan determinístico, Trilha 0 — Segurança).

## Máquina de estados da issue

```
backlog → refining → ready → planned → in_progress → in_review → verifying → done
            (qualquer estado -> blocked)        (falha de gate -> rejected/reopened)
```

| Transição | Quem faz | Gate |
|-----------|----------|------|
| backlog → refining | Agente Refinamento (reativo a issue nova) | — |
| refining → ready | **DoR** (checklist determinístico + Clarify/humano) | DoR |
| ready → planned | Agente Planejamento/Arquitetura | — |
| planned → in_progress | Agente Implementação | — |
| in_progress → in_review | abertura do PR | — |
| in_review → verifying | Agente Review (≠ implementador) + CI | review |
| verifying → done | **DoD** (CI verde + aceite + review) | DoD |
| qualquer → blocked | dependência não satisfeita | — |
| verifying/in_review → rejected/reopened | falha de gate | volta a planned/in_progress |

- **Estado de falha do loop**: se o loop de definição excede **N iterações** (loop breaker, Trilha B),
  a issue vai para `blocked` + escala ao humano — não fica em loop infinito.

Representação no GitHub: estados como **status field do Projects** (ou labels), transições
disparadas por eventos (Trilha B). O **merge do PR** fecha a issue (`Closes #n`).

## Gate de prontidão, tipagem de task e loop de definição

Antes de qualquer agente **executar** uma task, ela passa por um **gate de prontidão** — e isso
não é opcional, porque a pesquisa mostra que LLMs *reconhecem* ambiguidade mas **raramente
perguntam por conta própria** ("Knowing but Not Showing"); o gate tem de ser forçado.

### Tipagem de task (não desenvolver o que é de definição)

Toda task tem um **tipo**: `definição` · `desenvolvimento` · `spike/pesquisa`. Uma **task de
definição** NÃO pode ser desenvolvida — seu "done" é uma **spec aprovada**, não código. Confundir
os dois é o erro central que o gate previne.

### O validador (em camadas — determinismo primeiro)

1. **Checklist determinístico da DoR** (sem LLM): campos obrigatórios presentes? critérios de
   aceite testáveis existem? escopo/dependências declarados? Falhou aqui → nem chama LLM.
2. **Classificador estruturado barato (Jev / Trilha I)**: retorna `{tipo, bem_definida: bool,
   confiança, lacunas[]}`. Confiança calibrada vira threshold.
3. **Escala a frontier** só se a confiança for baixa.

> **Independência do validador**: o validador da DoR (checklist + Jev) é **independente** do agente de
> Refinamento — quem escreve a spec não valida a própria prontidão ("quem gera não valida"). A garantia
> dura é o **checklist determinístico**; o Jev é apoio, não a independência em si.

### Loop de definição (quando não está pronta)

```
não-ready → Agente Refinamento propõe (edita a issue) → humano aprova/comenta no pipeline
          → comentário dispara reprocessamento (trigger issue_comment) → agente melhora
          → revalida → se passa: estado vira `ready`
```

### Fail-closed no pickup

Quando a task é finalmente "pega"/trigada para execução, o validador roda **de novo** como
pré-condição. Se não passar, volta ao loop de definição — **nunca** desenvolve uma task não-pronta.

### Existe esquema pronto? (resposta à pergunta do dono)

As **peças** existem, o produto turnkey (tipagem + gate + loop de comentário no GitHub) **não** —
a gente compõe:
- **GitHub Spec Kit**: fases **Clarify** (resolver ambiguidade) e **Analyze** (consistência entre
  artefatos) são exatamente esse gate embutido no SDD.
- **Cursor Plan mode / Verdent clarification mode**: perguntam antes de codar.
- Pesquisa: **ClarifyCodeBench**, **Ambig-SWE** (agentes interativos p/ underspecificity em SWE),
  **"Ask or Assume? Uncertainty-Aware Clarification"**, e **Expected Information Gain** para
  escolher a melhor pergunta de clarificação.
- **Cuidado (Stanford)**: splits planner/critic adicionam pontos de falha e um critic pode
  *reduzir* o sucesso em tasks curtas → o gate deve ser **barato (Jev) e por nível de task**
  (task-level gating), não um critic pesado uniforme.
- **Self-evaluation bias**: verificação deve ser **externamente ancorada** — reforça "quem gera
  não valida" (o validador é independente do agente que escreveu a task).

> Cross-links: trigger por comentário (Trilha B), judge barato (Trilha I), gate humano no pipeline (Trilha H).

> **Fontes verificadas (auditoria rodada-01, out/2026)**: ClarifyCodeBench (arXiv 2607.00711) e
> Ambig-SWE (arXiv 2502.13069) existem e conferem; Ambig-SWE reporta até **+74%** com interação.
> Os demais arXiv citados (2605.25284, 2603.26233, 2606.03135, 2607.25152) **não foram verificados
> individualmente** — tratados como indicativos até conferência.

## Impacto em token

- DoR forte → issue densa → agente carrega só a mini-spec + arquivos apontados = sessão curta.
- Estado na issue (não na memória do agente) → continuidade sem re-contextualizar (Trilha G).
- DoD determinística → "pronto?" é decidido por CI, não por LLM caro.

## Perguntas em aberto

- [ ] Usamos **issue types + sub-issues** nativos do GitHub ou labels? (recomendo nativos).
- [ ] Projects entra só como visualização do status field, ou fica fora? (dono sugeriu talvez fora).
- [ ] Onde exatamente entram os **gates humanos** (Clarify, priorização, merge)? → Trilha H.
- [ ] Templates de issue/épico versionados no repo (`.github/ISSUE_TEMPLATE`)? (recomendo — é a DoR como artefato).

---

### Fontes
- [GitHub’s Spec Kit Puts the Spec Back in Software Development — DevOps.com](https://devops.com/githubs-spec-kit-puts-the-spec-back-in-software-development)
- [Meet GitHub Spec-Kit — MarkTechPost](https://www.marktechpost.com/2026/05/08/meet-github-spec-kit-an-open-source-toolkit-for-spec-driven-development-with-ai-coding-agents/)
- [Spec-Driven Development in 2026: tooling and how teams use it — dev.to](https://dev.to/krlz/spec-driven-development-in-2026-what-it-is-the-tooling-and-how-teams-actually-use-it-2fk2)
- [Spec-Driven Development (SDD): The Definitive 2026 Guide — thebcms](https://www.thebcms.com/blog/spec-driven-development/)
- [ClarifyCodeBench — Evaluating LLMs on Clarifying Ambiguous Requirements (arXiv)](https://arxiv.org/html/2607.00711v2)
- [Ambig-SWE — Interactive Agents to Overcome Underspecificity in SWE (arXiv)](https://arxiv.org/html/2502.13069v3)
- [Knowing but Not Showing — LLMs recognize ambiguity but rarely ask (arXiv)](https://arxiv.org/pdf/2605.25284)
- [Ask or Assume? Uncertainty-Aware Clarification-Seeking in Coding Agents (arXiv)](https://arxiv.org/html/2603.26233)
- [Uncertainty-Aware Clarification with Information Gain (arXiv)](https://arxiv.org/html/2606.03135v1)
- [Self-Evaluation Bias & Externally Grounded Verification in agent loops (arXiv)](https://arxiv.org/pdf/2607.25152)
