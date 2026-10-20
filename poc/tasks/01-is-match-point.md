# Tarefa de PoC #01 — `isMatchPoint` (packages/core)

Primeira tarefa de **edição** do PoC (etapa 2 da sequência): pequena, pura, test-first, 1 pacote,
sem decisão arquitetural. Alinhada ao `AGENTS.md` do jo-ken-po (TDD ADR 0010, TS strict, Conventional
Commits, GitFlow).

## Contexto
`packages/core/src/jokenpo/rules.ts` tem as regras puras (MD3): `resolveRound`, `applyRound`,
`initialMatch`, `walkover`, `ROUNDS_TO_WIN`, `MatchState`. Falta um detector de **match point**
(útil pra UI "ponto de partida!").

## O que fazer
Adicionar a função pura:
```ts
/** true quando a partida está em andamento e alguém está a uma vitória de ganhar. */
export function isMatchPoint(state: MatchState): boolean
```
- Regra: `state.winner === null` **e** (`state.scoreA === ROUNDS_TO_WIN - 1` **ou**
  `state.scoreB === ROUNDS_TO_WIN - 1`).
- Em `src/jokenpo/rules.ts`; **exportar** em `src/index.ts` (barrel, junto dos outros do jokenpo).

## DoR (pronto para começar) ✓
- [x] Escopo em **1 pacote** (`@jo-ken-po/core`), sem UI/DB/infra.
- [x] Critério de aceite **verificável** (abaixo) e sem ambiguidade.
- [x] **Sem** decisão arquitetural nova (não exige ADR).
- [x] Assinatura e local definidos.

## Critério de aceite (test-first, vitest)
Em `src/jokenpo/rules.test.ts`, um `describe("isMatchPoint")` cobrindo:
- `0-0` em andamento → `false`.
- `1-0` → `true`; `0-1` → `true`.
- partida terminada (ex.: após `walkover("a")` ou placar `2-x`) → `false` (tem `winner`).
- (borda) empate não muda: `applyRound(initialMatch(),"rock","rock")` → `false`.

## DoD (pronto) ✓
- [ ] Testes escritos **antes** (TDD) e **verdes**: `pnpm --filter @jo-ken-po/core test`.
- [ ] Tipos ok: `pnpm --filter @jo-ken-po/core typecheck`.
- [ ] `isMatchPoint` exportada no barrel (`src/index.ts`).
- [ ] Segue `AGENTS.md` (TS strict, naming, função pura sem I/O).
- [ ] Branch `feat/is-match-point` a partir de `develop`; **Conventional Commits**.
- [ ] **Nada** direto em `main`/`develop` — PR com gate humano (quando for o fluxo completo).

## POC_TASK (cole no poc/.env.poc — etapa 2, edita sem abrir PR)
```
POC_TASK=No pacote packages/core (@jo-ken-po/core), adicione a função pura isMatchPoint(state: MatchState): boolean em src/jokenpo/rules.ts — retorna true quando a partida está em andamento (winner === null) e algum jogador está a uma vitória de ganhar (scoreA ou scoreB === ROUNDS_TO_WIN - 1). Exporte em src/index.ts. Siga TDD (ADR 0010): escreva os testes primeiro em src/jokenpo/rules.test.ts cobrindo 0-0 (false), 1-0 e 0-1 (true) e partida terminada (false). Rode `pnpm --filter @jo-ken-po/core test` e `pnpm --filter @jo-ken-po/core typecheck` até passarem. Siga o AGENTS.md. Crie o branch feat/is-match-point a partir de develop; NÃO abra PR ainda.
```

## Variante fluxo completo (daemon, com PR)
Mesmo enunciado, trocando o final por: "…commit em Conventional Commits e **abra um PR** de
`feat/is-match-point` para `develop` com um resumo do que mudou." (deixa o CI do jo-ken-po julgar.)
