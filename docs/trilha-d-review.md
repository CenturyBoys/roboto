# Trilha D — Review de PR (como funciona)

> Documento **operacional**. O *porquê* está em
> [`research/D-review-de-pr.md`](https://github.com/CenturyBoys/roboto/blob/main/research/D-review-de-pr.md).
> **Status:** núcleo + fluxo automático + **re-review com contexto** + **gatilho em review dismissed**
> no `main` (#151 fechado).

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

## 5. Onde está ligado

- **Manual:** botão **Revisar PR** no cockpit → review estruturado + inline.
- **Automático:** `run_pr_cycle` (ciclo de implementação) e `process_correct_tick` (correção por
  polling) usam o **mesmo** review estruturado — o PR do fleet já nasce com os comentários inline, e
  os findings viram feedback rico pra correção.

## 6. Re-review com contexto (#151)

O re-review recebe os **comentários/reviews anteriores** do PR (`get_pr_comments` → `contexto_previo`)
e o prompt pede pra **não repetir** o que já foi apontado — foca no que mudou. Já ligado no botão
Revisar PR.

**Gatilho em review dismissed (#151):** se alguém **remove** um review (ex.: tira o do fleet e sobe
dado), o evento `pull_request_review:dismissed` **re-dispara o review** (`github/webhook`), com
idempotência pelo `head_sha` atual. Demais gatilhos: commit novo / `@potter` / `check_suite` — ver
[Trilha B](trilha-b-orquestracao.md).
