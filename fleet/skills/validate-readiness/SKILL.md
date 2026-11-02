---
name: validate-readiness
description: Decide se uma issue está PRONTA para dev (Definition of Ready) em 3 camadas — estrutural, semântica e escalada. Dispare antes de implementar uma issue, ou ao perguntar "essa issue está pronta?".
version: 1
---

# validate-readiness — a issue está pronta? (DoR)

Barato-primeiro: só sobe o custo quando a dúvida justifica. **Reviewer ≠ gerador** (quem refinou não
valida a si mesmo).

## Camada 1 — estrutural (SEM LLM, determinística)
Reprova na hora se faltar:
- as seções `Contexto`, `Escopo`, `Critérios de aceite`, `DoD`;
- um **critério verificável** `- [ ]` **sob** "Critérios de aceite" (vale dentro de subtítulos `###`).

Se faltar algo aqui → **não está pronta**: liste o que falta e peça pra completar. NÃO chute.

## Camada 2 — semântica (juiz barato)
Saída **estruturada** (não binária): `{ bem_definida: sim|nao, confianca: alta|media|baixa,
lacunas: [...] }`. Avalia ambiguidade, escopo claro, DoD significativo.

## Camada 3 — escalada
Se a **confiança for baixa**, re-avalia no **tier forte** (frontier) e usa esse veredito.

## Gate
Só vai pra `implement-issue` quando passa nas 3. Task de **definição** (ADR/RFC, sem critério) NÃO é
codada — seu "done" é a spec aprovada (ver a tipagem de task).
