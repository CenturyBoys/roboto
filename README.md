# Continuous Development (roboto)

Fleet de agentes cobrindo o **ciclo de vida inteiro de desenvolvimento de software**, tendo o
**GitHub** como substrato (Issues = fonte da verdade, PR/CI = feedback loop). Objetivo de primeira
classe: **economia de token** e sessões curtas em vez de sessões gigantes de contexto.

> **Fase atual: PESQUISA.** Só mudamos de fase com aprovação explícita do dono do projeto.
> Nada aqui é implementação final — é a base de pesquisa que vai definir o fleet.

## Princípios-guia

- **Determinismo primeiro** — preferir código/processo bem-feito à decisão de LLM sempre que a
  tarefa permitir. LLM só onde há julgamento ou geração irredutível a código.
- **Ferramentificação** — operação repetida vira artefato durável (script/MCP/skill).
- **Right-sizing de modelo** — escada de validação: check determinístico → judge barato (Jev) →
  frontier tiered (Haiku/Sonnet/Opus).
- **Não copiar o organograma humano 1:1** — responsabilidade migra conforme a ferramenta absorve
  complexidade (caso-guia: DBA/ORM).
- **Spec-driven** — a spec versionada é a unidade de governança; quem gera não valida a si mesmo.

## Pesquisa

Toda a investigação vive em [`research/`](research/) — um documento por trilha. Comece pelo
[`research/README.md`](research/README.md) (índice + princípios).

Trilhas: **0** papéis · **A** contratos de trabalho · **B** orquestração · **C** skills ·
**D** review de PR · **E** AGENTS.md/padrões · **F** token/ferramentificação · **G** memória ·
**H** qualidade/segurança · **I** roteamento de modelos · **J** escala CI · **K** runtime ·
**L** modelo de custo.

O próprio backlog desta pesquisa é rastreado como **épico + issues** neste repositório (dogfooding
do processo que estamos projetando).
