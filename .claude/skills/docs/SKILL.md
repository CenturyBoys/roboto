---
name: docs
description: Documentação do Potter — site MkDocs Material (GitHub Pages) + doc-guard (doc-in-sync). Dispare ao mexer na documentação, rodar/prever o site localmente, adicionar uma página, ou checar se uma mudança de código precisa de doc antes de abrir PR.
---

# Docs — site MkDocs + doc-guard

A documentação vive em **`docs/`** e é publicada como site **MkDocs Material** (GitHub Pages).
O contrato é **doc-in-sync** (AGENTS §5): mudança de regra/domínio atualiza a doc no MESMO PR.

## Onde está o quê
- `docs/` — conteúdo (markdown). `docs/index.md` é a home; `docs/stylesheets/potter.css` é o tema (tokens).
- `mkdocs.yml` — config + **navegação** (ao criar uma página nova, adicione no `nav:`).
- `docs/tutorial-operador.md` / `docs/tutorial-dev.md` — os dois tutoriais.
- `docs/trilha-*.md` — "como funciona" de cada trilha (capstone, tom operacional — não pesquisa).

## Rodar o site localmente
```bash
pip install mkdocs-material      # ou: pip install -e ".[docs]"
mkdocs serve                     # http://127.0.0.1:8000 (live reload)
mkdocs build --strict            # valida links/nav (o que o CI faz)
```

## Publicação
Push em `main` que toque `docs/**` ou `mkdocs.yml` dispara o workflow **`.github/workflows/docs.yml`**
(`mkdocs gh-deploy` → branch `gh-pages`). Habilite uma vez: repo → Settings → Pages → Source = `gh-pages`.

## doc-guard (o portão)
`scripts/doc_guard.py` + workflow `.github/workflows/doc-guard.yml`: um PR que mexe em `src/roboto/**`
(fora de testes) **sem** tocar `docs/`/`research/`/`README`/`AGENTS` → **check vermelho**.
- Rodar local antes do PR: `PR_TITLE="meu título" python3 scripts/doc_guard.py origin/main`
- Escape consciente (refactor interno puro, sem doc): `[skip-docs]` no título do PR.

## Screenshots — documentação viva (Playwright)

As imagens das telas (`docs/assets/screens/*.png`) são **geradas da UI real**, não desenhadas —
garante **conformidade** (a doc reflete a tela). Com o cockpit RODANDO:
```bash
cd web/ui && npm ci && npx playwright install chromium
COCKPIT_URL=http://localhost:8090 CONSOLE_TOKEN=<token> node scripts/screenshots.mjs
```
- As telas e os **destaques** vivem no array `SCREENS` de `web/ui/scripts/screenshots.mjs`.
- O highlight é por **`data-testid`** — todo elemento relevante do cockpit tem um id estável
  (`nav-execs`, `exec-summary`, `settings-toggle`…). Mesmo id serve pra **teste e doc**. Ao criar uma
  tela/elemento que a doc aponte, **dê um `data-testid`** e, se for destacável, registre no `SCREENS`.
- Mexeu na UI? Regenere e commite as imagens no mesmo PR (conformidade).

## Diagramas (Mermaid)
Renderizam nativo (fence configurado no `mkdocs.yml`). **Siga a convenção** —
`docs/convencao-diagramas.md`: labels ≤ 2–3 palavras (detalhe vai na legenda em prosa), sem nó-hub
(muitas arestas num só nó empilham as labels), ≤ ~8 nós, aspas em labels com `()`/`/`. Diagrama
ilegível (labels coladas)? **Encurte as labels e mova o detalhe pra legenda** — é a correção padrão.

## Ao adicionar/alterar doc
1. Edite/crie o `.md` em `docs/`.
2. Se for página nova, registre no `nav:` do `mkdocs.yml`.
3. `mkdocs build --strict` (sem links quebrados).
4. Mudou comportamento? Atualize o tutorial/arquitetura correspondente — senão o doc-guard barra.
