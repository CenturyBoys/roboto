# AGENTS.md — regras do roboto

> Arquivo versionado. Atualize-o **no mesmo PR** que muda a convenção. Mantenha < 500 linhas:
> só o que um agente precisa para escrever código **correto** aqui. O que o linter já impõe NÃO
> entra aqui (vai na config). Detalhe de pesquisa/decisão vive em `research/`.

## Projeto
`roboto` — fleet de agentes cobrindo o ciclo de vida de software no GitHub. Objetivo de primeira
classe: **economia de token** + **determinismo**.

## Stack e convenções (decisão D1)
- **Python ≥ 3.11**, **async** por padrão em I/O, **containerizado**.
- **Retorno estilo `Result<Ok, Error>`** (`roboto.result`): operações que podem falhar **retornam
  `Result`**, não lançam exceção para fluxo de controle. Exceção é só para erro de programação/inesperado.
- **Type hints sempre**; `mypy --strict` tem de passar.
- **Nomes descritivos e semânticos**; proibido `temp/val/res/data/foo`.
- **Comentário só para o PORQUÊ** (negócio, edge case, decisão não-óbvia) — nunca reescrever o código.
- **Front (cockpit web, trilha O):** **React + TypeScript (strict)** + Tailwind + shadcn em `web/ui/`;
  builda para `src/roboto/web/static/` e é servido pelo **mesmo backend Starlette** (fallback no viewer
  legado quando não há build). O contrato é a **API JSON/SSE do console** — a UI só consome.
- **Config = banco (fonte única, trilha O):** a config operacional vive em `app_config` (tabela). O
  `.env`, quando existe, só **semeia** o banco no boot (`settable_from_env`); a tela de setup grava no
  mesmo lugar. Exceção — **bootstrap só por env**: `DATABASE_URL` e `CONSOLE_TOKEN`. Faltou config
  obrigatória → daemon sobe em **modo setup** (não morre).

## Comandos exatos
```bash
pip install -e ".[dev]"     # setup (backend)
ruff check src tests        # lint (tier 1)
mypy                        # tipos (tier 1)
pytest                      # testes (tier 1)
```
Front (cockpit React — rodar em `web/ui/`):
```bash
cd web/ui && npm ci         # setup (uma vez)
npm run typecheck           # tipos (tsc --noEmit; tier 1 do front)
npm test                    # vitest (tier 1 do front)
npm run build               # gera o SPA em src/roboto/web/static (servido pelo console)
```

## Estrutura
- `src/roboto/` — código (orquestrador, agentes, gateway, bot, console web).
- `web/ui/` — cockpit React (console web); builda para `src/roboto/web/static/` (não versionado).
- `tests/` — testes do backend (tier 1 do CI); testes do front vivem em `web/ui/src/**/*.test.tsx`.
- `migrations/` — schema do banco (fonte da verdade do schema = migrations).
- `research/` — a pesquisa que fundamenta o desenho (não é código).

## Princípios (herdados da pesquisa)
- **Determinismo primeiro**: preferir código/processo à decisão de LLM; CI é o juiz do "pronto".
- **Ferramentificação**: operação repetida vira artefato durável (script/MCP/skill).
- **Right-sizing de modelo**: check determinístico → Jev → frontier (barato-primeiro).
- **Quem gera não valida**: review por agente ≠ autor.
- **Output do modelo = proposta; política determinística decide.**

## Limites operacionais (o agente NUNCA faz)
- Commitar segredo (ver `.gitignore`; senha do ansible-vault em `.ansible.vault_pass`, nunca versionada).
- Merge/deploy/mudança de credencial/decisão arquitetural/resolução de conflito/ação destrutiva
  **sem gate humano** (decisão D7).
- Dar credencial de banco a um modelo: acesso a dados é só via **data-gateway de leitura curado** (D19).
- Trocar de fase do projeto sem aprovação explícita do dono.
