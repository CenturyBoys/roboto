# Trilha K — Runtime containerizado (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/K-runtime-containerizado.md`](https://github.com/CenturyBoys/roboto/blob/main/research/K-runtime-containerizado.md).
> **Princípio-âncora:** sandbox seguro = container **não-root** + egress controlado + timeout por
> task; **1 instância por empresa, N repos via GitHub App** (D17). **Status:** imagem do PoC +
> **preflight** no `main`; hardening de egress/efemeridade como follow-up.

## 1. O que a trilha entrega

O ambiente onde o fleet roda: imagem containerizada reproduzível, não-root, com as ferramentas
pinadas, e uma **validação de pré-condições** antes de trabalhar.

## 2. A imagem (já existente — `poc/Dockerfile`)

| Peça | Como |
|---|---|
| **não-root** | roda como `pwuser` — exigência do Claude Code p/ bypassPermissions (autonomia git/pnpm/PR) |
| **code-intel pinado** | `IDE_CC_VERSION` fixa; o build **falha** se não instalar (pilar de token, F) |
| **Playwright** | imagem base oficial (navegação/login web sob demanda) |
| **Node por-repo** | bootstrap instala em runtime o Node que cada repo pede (`.nvmrc`/engines) — imagem sem opinião |
| **venv dedicado** | evita PEP 668; pip novo sem `--break-system-packages` |
| **fleet skills** | `fleet/skills` → `~/.claude/skills` (trilha C) |

## 3. Preflight — pré-condições antes de trabalhar (novo)

Validação **determinística** no startup do daemon (`app/preflight.check`), a pedido da pesquisa
("validadores de acesso/infra como pré-condição"):

| Check | Falha se |
|---|---|
| `env:OPENROUTER_API_KEY` | faltando (o motor não roteia) |
| `workdir` | o diretório do repo-alvo não existe |
| `disco` | menos que o mínimo livre (default 500MB) |

- **Puro e testável:** recebe os valores lidos (env, caminho, disco livre) e só decide; o I/O
  (`os.environ`, `shutil.disk_usage`) fica no runtime.
- **Não-bloqueante:** loga `✓/✗` por check (a config crítica já é validada em `load_config`) — falha
  cedo e **claro** em vez de o motor flailar no meio da task.

## 4. Isolamento e secrets (decidido)

- **1 instância por empresa, N repos via GitHub App** (D17); observabilidade em Docker (D3).
- Secrets: **ansible-vault** (1 var `ANSIBLE_VAULT_PASSWORD` no GitHub) p/ config estática (D4).

## 5. Follow-ups (backlog)

- **Egress deny-all + allowlist** (GitHub, OpenRouter, feeds) + `--cap-drop=ALL` + `--read-only`.
- **Efêmero 1-por-task + git worktree** dedicado (mecanismo concreto da prevenção de colisão da J);
  estado durável **fora** do container (store externo — trilha M).
- **gVisor/Firecracker** para código **não-confiável** (PR externo no repo público) — não é opcional.
- **Warm-cache** do índice do code-intel (read-only, por-projeto-confiável, assinado) sem furar o
  isolamento efêmero.
- **Injeção runtime de credencial curta** (Vault/OpenBao) para o que é sensível.
