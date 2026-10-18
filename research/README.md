# Continuous Development — Pesquisa

Fase atual: **PESQUISA**. Só mudamos de fase com aprovação explícita do dono do projeto.

Este diretório guarda a investigação que vai definir o fleet de agentes que cobre o
ciclo de vida de desenvolvimento de software, usando o **GitHub** como substrato
(Issues = fonte de verdade, PR/CI = feedback loop, Projects = possivelmente só visualização).

Objetivo de primeira classe em todas as trilhas: **economia de token** e sessões curtas
em vez de sessões gigantes de contexto.

> 📄 **Visão de conjunto (com diagramas):** [`SYNTHESIS.md`](SYNTHESIS.md) — sintetiza e amarra todas
> as trilhas sem substituí-las. Comece por lá para o panorama; use as trilhas abaixo para o detalhe.
> 🧱 Vistas estruturais em **padrão C4** + esboços de implementação: [`ARCHITECTURE-C4.md`](ARCHITECTURE-C4.md).
> ✅ **Revisão final / prontidão para implementar:** [`READINESS.md`](READINESS.md) — o que está sólido, lacunas, decisões-fundação e ordem do MVP.
> 🟦 **Decisões a fechar (proposta + pontos de vista p/ o dono verificar):** [`DECISOES-A-FECHAR.md`](DECISOES-A-FECHAR.md).
> 🧩 **Design do núcleo durável (§2):** [`DESIGN-nucleo.md`](DESIGN-nucleo.md) — run lifecycle, idempotência, outbox, auditoria `llm_call`, versão de prompt.

## Trilhas

| # | Trilha | Pergunta central | Depende de |
|---|--------|------------------|------------|
| 0 | Mapa de papéis → agentes | Que responsabilidades viram agente vs. são resolvidas por processo/estrutura? | — |
| A | Contratos de trabalho | O que é épico/issue/DoR/DoD executável e a máquina de estados da issue? | 0 |
| B | Orquestração e gatilhos | Como disparar agentes (reativo / ambiente / sob demanda) de forma idempotente? | 0 |
| C | Design de skills | Qual granularidade e composição de skills por etapa? | 0, A |
| D | Review de PR | Estado-da-arte de review com agentes: sinal alto, pouco ruído. | — |
| E | Padrões de código / AGENTS.md | Quão completo deve ser; naming verboso vs. comentários. | — |
| F | Economia de token, ferramentas e **ferramentificação** | Quando uma operação repetida deve virar artefato durável (script/alias/MCP/skill)? code-intel/ide_cc vs grep, RTK, subagents. | — |
| G | Memória / continuidade / second brain | Issue+repo+memória em texto como default; avaliar camadas externas (mem0/Letta/Zep/knowledge graph) só como exceção. | A |
| H | Qualidade/segurança/recuperação | Evals, segurança (agente de feed), gates humanos, paralelismo, rollback, observabilidade. | 0, B |
| I | Roteamento de modelos | Qual compute por operação: check determinístico → judge barato (Jev/System One) → frontier tiered (Haiku/Sonnet/Opus). OpenRouter como substrato. | F, H |
| J | Escala: build/CI, carga de testes e revisores | Com muitos PRs/builds/pipelines concorrentes, qual a política de prioridade de build, de carga de testes e de distribuição de revisão? | B, A |
| K | Runtime containerizado | Rodar o fleet em Docker: auth no container, Playwright, credenciais via symlink/sync com least privilege. | H, B |
| L | Modelo de custo do fleet | Orçar/medir token/$ por agente/issue/PR, com teto e alerta (criada na auditoria rodada-01). | F, I, J, H, D |
| M | Observabilidade operacional, Telegram e checkpoints | Monitor de jobs (duração/erros), notificação+aprovação via Telegram, checkpoint/resume (durable execution). | H, A, B, G, J, K, L |

## Como cada doc de trilha é estruturado

1. **Pergunta** — o que estamos tentando decidir.
2. **Estado da arte** — como o mercado/pesquisa faz hoje (com fontes).
3. **Opções e trade-offs.**
4. **Recomendação.**
5. **Impacto em token.**
6. **Perguntas em aberto.**

## Princípios já estabelecidos

- **Determinismo primeiro (princípio-mãe).** Preferir código/processo bem-feito à decisão de
  LLM sempre que a tarefa permitir. LLM só onde há julgamento ou geração que não dá pra
  expressar em código. Isso é a raiz da ferramentificação (Trilha F) e da escada de validação
  (Trilha I): mais confiável, mais barato, menos token.
- Não copiar o organograma humano 1:1. Responsabilidade migra conforme a ferramenta
  absorve complexidade (ex.: ORM absorveu a modelagem que era do DBA). Pergunta por papel:
  **agente dedicado / resolvido por processo / híbrido**.
- Taxonomia de gatilho de agente: **reativo a evento** (PR, issue, CI) · **ambiente/contínuo**
  (feed ou schedule — ex.: segurança assinando CVEs) · **sob demanda** (humano invoca).
- `CLAUDE.md` mínimo aponta para `AGENTS.md`; as regras vivem no `AGENTS.md`.
- **Ferramentificação**: toda operação repetida (comando, build de chamada, exec em máquina
  remota) deve virar um **artefato durável** — script de sistema, alias, tool/MCP ou skill —
  em vez de ser reconstruída em linguagem natural a cada sessão. Ganho duplo: menos token e
  mais determinismo/qualidade. Caso-guia: `ide_cc` (CenturyBoys) = o MCP `code-intel`, que
  promove refactors mecânicos a tools verificadas por build. Ver Trilha F.
- **Disciplina de fontes** (introduzida pela auditoria rodada-01): separar evidência
  **primária/acadêmica** de **número de vendor/blog** (indicativo, a verificar). Decisão de desenho
  se apoia em fonte verificável; claim de parte interessada é marcado como "indicativo".
- **Right-sizing de modelo**: dimensionar o compute à operação, não usar Opus para tudo.
  Escada de validação (do mais barato ao mais caro): (1) check determinístico — teste/lint/
  type-check/build (sem LLM); (2) decisão estruturada barata com confiança calibrada (Jev/
  System One) para o que não vira script; (3) frontier tiered (Haiku→Sonnet→Opus) só quando
  há raciocínio/geração de verdade. Ver Trilha I.
