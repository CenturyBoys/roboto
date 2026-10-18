# Trilha F — Economia de token, ferramentas e ferramentificação

> Status: ESQUELETO (pesquisa não iniciada)

## Pergunta

Duas perguntas acopladas:
1. Como minimizar token por tarefa sem perder qualidade (code-intel vs grep, RTK, subagents, contexto enxuto)?
2. **Ferramentificação**: quando uma operação repetida deve deixar de ser linguagem natural e
   virar um **artefato durável**? Qual o lifecycle e onde ela mora?

## Princípio da ferramentificação

Qualquer comando/fluxo que o agente usaria "muitas vezes" deve ser promovido a tool durável.
Reconstruir a chamada em NL a cada sessão custa token e é não-determinístico. Promover resolve
os dois. Caso-guia: `ide_cc` (CenturyBoys, https://github.com/CenturyBoys/ide_cc) — o MCP
`code-intel` desta sessão — que transformou refactors mecânicos (rename/move/extract/change-signature)
em tools verificadas por build. O LLM decide o *quê*; a tool faz o *mecânico*; o validador *confere*.

## Taxonomia de artefato (preencher: critério de escolha)

- [ ] **Script de sistema** (no PATH / `scripts/` do repo) — ex.: exec padronizado em máquina remota.
- [ ] **Alias / função de shell** — atalhos triviais.
- [ ] **Tool / MCP server** — operação que precisa de estado, índice, verificação ou cache (ex.: ide_cc).
- [ ] **Skill** — procedimento multi-passo que o agente invoca.
- [ ] Ferramentas Rust / RTK (ripgrep, fd, bat, sd...) como base mais enxuta que coreutils.

## Perguntas a decidir

- [ ] **Critério de promoção**: quantas repetições / qual custo justifica virar artefato?
- [ ] **Registro de ferramentas**: como o fleet descobre as tools existentes (um índice/`TOOLS.md`?)
      para não reinventar nem duplicar.
- [ ] **Execução remota**: script único parametrizado para rodar comandos na VPS em vez de montar a chamada toda vez.
- [ ] **Quando code-intel ganha de grep** e vice-versa (grep só para texto literal).
- [ ] Medição: tokens/$ por etapa antes/depois de ferramentificar (amarra com Trilha H / observabilidade).

## Saída esperada

Doutrina de ferramentificação + taxonomia + critério de promoção + esboço de registro de tools,
que vira regra no futuro `AGENTS.md`.
