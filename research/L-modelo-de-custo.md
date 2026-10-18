# Trilha L — Modelo de custo do fleet

> Status: RASCUNHO PARA REVISÃO (criada na remediação da auditoria rodada-01, 2026-10-18)

## Por que existe

A auditoria rodada-01 apontou o maior buraco: o objetivo-mãe é **economia de token**, mas
**nenhuma trilha orçava o custo agregado** do fleet. Sem modelo de custo, "economia de token" não é
verificável e o review multi-agente (Trilha D) — que **não batcheia** como o CI (Trilha J) — pode
dominar a conta sem ninguém perceber. *Não dá para otimizar o que não se mede.*

## Pergunta

Como **orçar e medir** o custo (token/$) do fleet por **agente**, por **etapa**, por **issue** e por
**PR**, com teto e alerta — de forma que a economia seja comprovável e o gasto, previsível?

## Unidades de custo

- **Por issue (custo até `done`)**: refino + planejamento + implementação + review + correções.
  É a métrica de negócio ("quanto custa fechar uma issue").
- **Por PR**: dominado pelo **review** (D) — multi-dimensão × multi-pass, re-disparado a cada
  `synchronize`. Maior risco de custo não-batcheado.
- **Por agente/etapa**: atribuição por tipo (refine/plan/impl/review/security/docs) e por modelo.

## Alavancas de redução (já decididas nas outras trilhas — aqui viram orçamento)

| Alavanca | Trilha | Efeito |
|----------|--------|--------|
| Escada de validação (determinístico → Jev → frontier) | I | evita frontier no que não precisa |
| Progressive disclosure + subagents com síntese | C, F | contexto enxuto, não paga 20 skills upfront |
| Ferramenta certa (grafo/semântica vs grep-and-read) | F | ordens de magnitude de token |
| CI batching + test impact analysis | J | -50–70% da conta de CI |
| Checks determinísticos fora do LLM (review/evals) | D, H | não gasta token no óbvio |

## Política de orçamento (proposta)

- **Teto por tipo de agente** (token/$ por run) + **budget por issue**; ao exceder, **degrada o
  tier de modelo** ou **pausa e escala ao humano** (não estoura silenciosamente).
- **Review budgetado**: teto de dimensões × passagens por PR; só roda review completo **depois** do
  gate determinístico passar (Trilha D).
- **Alerta de runaway** (loop de agente) via observabilidade (Trilha H).
- **Atribuição de custo** por feature/modelo/agente → mede o ganho real da ferramentificação (F) e
  do right-sizing (I) contra um **baseline**.

## Perguntas em aberto (precisam do dono)
- [ ] **Teto de token/$ por tipo de agente** e **budget-alvo por issue**.
- [ ] Custo/issue aceitável antes de acionar gate humano de custo.
- [ ] Política ao estourar: degradar modelo, pausar, ou escalar? (default sugerido: degradar → pausar → escalar).
- [ ] Plataforma de medição (liga com a decisão de observabilidade da Trilha H).

---

### Fontes
- Deriva das Trilhas [F], [I], [J], [H] e [D]; evidências quantitativas lá (todas verificadas na auditoria rodada-01).
- [Context Engineering: Why More Tokens Makes Agents Worse — Morph](https://www.morphllm.com/context-engineering)
