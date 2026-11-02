---
name: Issue (feature/fix) — executável por agente
about: Unidade de trabalho issue→PR. Deve passar no gate de prontidão (DoR) do fleet.
title: "tipo(escopo): resumo curto (Conventional Commits)"
labels: []
---

<!--
As seções abaixo são EXIGIDAS pelo gate de prontidão (DoR) do fleet
(`check_issue_readiness`): Contexto, Escopo, Critérios de aceite (com itens `- [ ]`) e DoD.
Sem elas, a issue fica em WAITING e não é implementada. Mantenha os títulos `##` exatos.
-->

## Contexto
<!-- Por quê. Links para a spec/épico e arquivos/área provável do código (fundamente no repo real). -->

## Escopo
<!-- O que entra: arquivos/áreas REAIS do repo. -->

## Critérios de aceite
<!-- Verificáveis, preferencialmente expressáveis como teste (determinismo primeiro). -->
- [ ] 

## DoD
- [ ] Testes cobrindo os critérios
- [ ] lint · typecheck · build · testes (CI verde)
- [ ] Review aprovado (revisor ≠ autor)
- [ ] Docs/ADR atualizados se a mudança for observável (doc-in-sync)

## Fora de escopo
<!-- O que explicitamente NÃO entra (evita o agente extrapolar). -->
