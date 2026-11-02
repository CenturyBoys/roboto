# Potter ⚡ — Continuous Development

> *"Todo PR nasce com uma cicatriz."*

**Potter** é um **fleet de agentes** que cobre o ciclo de vida inteiro de software, tendo o
**GitHub** como substrato (Issues = fonte da verdade; PR/CI = feedback loop). Foco de primeira
classe: **economia de token** e sessões curtas em vez de contextos gigantes.

## Por onde começar

<div class="grid cards" markdown>

- :material-rocket-launch: **[Tutorial do operador](tutorial-operador.md)** — subir o fleet, usar o
  cockpit, disparar refino/implementação, comandos `@potter`.
- :material-code-braces: **[Tutorial de dev / arquitetura](tutorial-dev.md)** — como o sistema
  funciona por dentro, onde está no código, pontos de extensão.
- :material-sitemap: **[Arquitetura](arquitetura.md)** — a visão esquemática.
- :material-check-decagram: **[Trilha A — Contratos](trilha-a-contratos.md)** ·
  **[Trilha B — Orquestração](trilha-b-orquestracao.md)** — como cada parte funciona hoje.

</div>

## Princípios-guia

- **Determinismo primeiro** — preferir código/processo à decisão de LLM; o CI é o juiz do "pronto".
- **Agnóstico de plataforma** — o núcleo não conhece GitHub; GitHub é um **adapter** (issues, labels,
  PRs). Trocar de plataforma = trocar o adapter.
- **Quem gera não valida** — review por agente ≠ autor.
- **Ferramentificação** — operação repetida vira artefato durável (script/MCP/skill).
- **Output do modelo = proposta; política determinística decide.**

## O loop, em uma frase

Uma **issue** acionável (DoR) vira um **run** no orquestrador → o **motor** implementa → abre **PR** →
**review (≠autor)** → se reprova, **corrige** → humano **mergeia** (gate). Tudo rastreável no
**cockpit** e projetado como estado (`status:*`) na própria issue.
