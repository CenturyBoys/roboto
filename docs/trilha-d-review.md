# Trilha D — Review de PR (como funciona)

> Documento **operacional**. O *porquê* está em
> [`research/D-review-de-pr.md`](https://github.com/CenturyBoys/roboto/blob/main/research/D-review-de-pr.md).
> **Status: em progresso** — o núcleo abaixo está no `main`; o restante (fluxo automático + #151)
> está em construção.

## 1. Princípios

- **Revisor ≠ autor** (quem gera não valida) — bloqueado sem LLM se forem o mesmo.
- **Determinismo primeiro:** o LLM **não** re-flaga lint/type/test/build/secret — o CI já pega. O
  review foca em **lógica e design**.
- **Juiz determinístico:** `temperature=0` + **rubrica** (bloqueador vs menor; qualquer bloqueador
  reprova; na dúvida, reprova).
- **Shift-left:** o `verify` determinístico (code-intel/tsgo) entra como FATO no prompt, pra o juiz
  não aprovar por cima de erro de tipo.

## 2. Review estruturado + inline

O review produz **findings tipados** (`agents/review.py`):

```
{ severidade: bloqueador|menor, arquivo, linha, confiança, evidência, recomendação }
```

- **Veredito determinístico:** aprovado só se **não há bloqueador** (`aprovado_por_findings`).
- **Comentários INLINE enxutos** (`formatar_finding`): título + recomendação à vista; a **evidência
  (trecho de código) fica COLAPSADA em `<details>`** — sem parede de código no GitHub. Postado via
  `github.submit_review` (event `COMMENT`, não bloqueia — merge é humano).
- **Resumo** curto e escaneável + os findings sem linha específica no corpo (`montar_review`).

## 3. Estratégia plugável

`ROBOTO_REVIEW_STRATEGY` (`agents/review.revisar_pr`):

- **`single`** (hoje): juiz único estruturado.
- **`multi`** (hook futuro): multi-dimensão (bug · segurança · simplicidade) + um passo de
  **verificação** que re-lê a fonte antes de postar. A pesquisa mostra que multi-passagem/multi-agente
  corta falso-positivo e sobe a resolução — ligável sem mexer nos chamadores.

## 4. Ciclo de correção (já existente)

Review reprovou → o **coder corrige** (resume da sessão) → **re-review** → humano mergeia. Dispara
por polling (PR estabilizou, `@potter revisa`, `check_suite` falhou) — ver
[Trilha B](trilha-b-orquestracao.md).

## 5. O que falta (em construção)

- Ligar o review estruturado no fluxo **automático** (`pr_cycle`/`correct`), não só no botão manual.
- **#151:** re-review com **contexto completo** do PR (comentários + reviews anteriores) e gatilho em
  `review dismissed`.
