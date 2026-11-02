# Estado do projeto

Visão única do que cada trilha **entregou** e o principal **follow-up**. Todas as trilhas de pesquisa
(0, A–M) estão implementadas, com doc consolidado e issue-guarda-chuva fechada.

## Trilhas

| Trilha | Entregue | Principal follow-up |
|---|---|---|
| [0 — Papéis→agentes](trilha-0-papeis.md) | lista canônica de agentes + o que é processo | agentes laterais (arquitetura, test-gen, SRE) |
| [A — Contratos](trilha-a-contratos.md) | DoR 3 camadas, tipo de task, estados→labels, templates | — |
| [B — Orquestração](trilha-b-orquestracao.md) | RunState, outbox, gatilhos por polling, retry/dead-letter | — |
| [C — Skills](trilha-c-skills.md) | 5 skills do fleet expostas ao motor | empacotar como plugin |
| [D — Review](trilha-d-review.md) | review estruturado + inline, juiz determinístico | gatilho *review dismissed* |
| [E — Padrões](trilha-e-padroes.md) | injeção do AGENTS.md do repo-alvo (determinística) | parse de linter/tsconfig |
| [F — Token](trilha-f-token.md) | code-intel + medição custo **e** comportamento | warm-cache do índice |
| [G — Memória](trilha-g-memoria.md) | recall determinístico injetado no prompt | markdown-first + auto-remember |
| [H — Qualidade/segurança](trilha-h-qualidade.md) | gates, least-privilege, secret-scan, revert, risco, evals, anti-loopjacking | escalada automática; evals LLM-judge |
| [I — Roteamento](trilha-i-roteamento.md) | tier→modelo por config + fallback | Jev plugável; RouteLLM |
| [J — Escala](trilha-j-escala.md) | concurrency-lock + WIP/backpressure | dependency-aware; merge queue |
| [K — Runtime](trilha-k-runtime.md) | imagem do PoC + preflight | egress allowlist; worktree; gVisor |
| [L — Custo](trilha-l-custo.md) | orçamento do mês vs teto + alerta | teto por agente/issue; política ao estourar |
| [M — Observabilidade](trilha-m-observabilidade.md) | aba Monitor + Telegram + continuidade | durable execution se escalar |

## Garantias transversais

- **Determinismo primeiro:** gates (DoR, veredito, risco, secret, orçamento, WIP) são **código**, não
  decisão de LLM; o output do motor é sempre **proposta** revalidada.
- **Gate humano** em merge e em mutação de issue — o fleet nunca mergeia sozinho.
- **Qualidade contínua:** tier-1 (ruff+mypy+pytest) + **evals gate** + **doc-guard** em todo PR.
- **Sem co-autor** em commit/PR (regra da org).

## O que ainda não é trilha

Operação interativa na sessão viva (épico #152 — co-piloto tmux parcial), re-review *dismissed*
(#151), e fixes/itens do PoC (#144/#145/#149/#150). O passo natural de validação é rodar as **issues
reais do repo-alvo** (arenavalendo) por cada etapa do loop, ponta a ponta.
