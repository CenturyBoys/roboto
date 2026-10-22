# Cockpit — front do console (trilha O)

Cockpit web do fleet `roboto`: **React + TypeScript (strict) + Vite + Tailwind + shadcn**. Substitui
o Telegram no papel de *painel de gerência* (o Telegram fica só como conversa/push). Ver
[`research/O-interface-de-gerenciamento.md`](../../research/O-interface-de-gerenciamento.md).

## Como roda

O front **consome a API JSON do console** (`src/roboto/web/console.py`) — não tem backend próprio.
O build gera o SPA em `../../src/roboto/web/static/`, de onde o **Starlette serve** (`/` = app,
`/assets/*` = estáticos). Sem build, o console cai no **viewer legado embutido** (`web/viewer.py`).

```bash
npm ci            # setup (uma vez)
npm run dev       # dev server do vite (proxy manual p/ o backend, se precisar)
npm run typecheck # tsc --noEmit (tier 1 do front)
npm test          # vitest
npm run build     # gera o SPA em src/roboto/web/static (é o que o console serve)
```

Em produção, o **Dockerfile** builda o front num estágio Node e copia o resultado para o pacote
Python. Autenticação = bearer `CONSOLE_TOKEN` (guardado no `localStorage`), isolamento por tenant —
tudo do backend; a UI só injeta o header.

## Estrutura

- `src/lib/api.ts` — client tipado da API (espelha `console.py`).
- `src/types.ts` — tipos do JSON do console.
- `src/components/ui/` — primitivos estilo shadcn (Button, Card, StatePill, Table).
- `src/components/` — telas: `ExecList`, `ExecDetail` (com terminal embutido), `Costs`, `Interactions`.

## Próximas fatias (modo torre de controle)

2. feed legível via **SSE** · 3. responder HITL pelo front · 4. custo agregado + diff · 5. co-piloto.
