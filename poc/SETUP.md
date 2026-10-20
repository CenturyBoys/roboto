# PoC — fluxo de configuração (runbook)

Como sair do zero até o fleet trabalhando no `arenavalendo/main`. Responde: onde ficam as configs,
como o repo é acessado, de onde vêm as chaves, e em que ordem.

## Modelo mental (leia primeiro)
1. **O fleet age como um GitHub App** (robô próprio) — você **não** usa sua conta/`gh login`. Você
   cria o App, instala no repo e põe as **credenciais do App** na config. Ele clona/comenta/abre PR
   como ele mesmo (identidade própria, token curto — D17/D21).
2. **O container clona o repo sozinho** em `/work/target` (`TARGET_REPO_URL`). Você não clona à mão.
3. **Config = valores num arquivo** (`poc/.env.poc`, gitignored). Em produção, vem do ansible-vault (D4).
4. **Claude Code não fala direto com a Anthropic**: aponta pro **claude-code-router** no container,
   que traduz pro **OpenRouter/Qwen**. A chave que importa é a `OPENROUTER_API_KEY`.

## Onde cada coisa vive
| Config | Onde | De onde vem |
|---|---|---|
| Tudo do PoC | `poc/.env.poc` (copie de `.env.poc.example`) | você preenche |
| Chave do OpenRouter | `OPENROUTER_API_KEY` → o entrypoint injeta no `ccr.config.json` | openrouter.ai |
| GitHub App (id/pem/installation/webhook) | `GITHUB_APP_*` + `GITHUB_WEBHOOK_SECRET` | você cria o App |
| Token p/ clonar repo privado | `GITHUB_CLONE_TOKEN` (https) ou chave ssh montada | PAT fine-grained ou token do App |
| Telegram (bot + allowlist) | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWLIST` | BotFather + seu user id |
| Checkout do repo-alvo | `/work/target` dentro do container | clonado pelo entrypoint |
| Credencial do Claude Code | **não precisa chave Anthropic** (`ANTHROPIC_BASE_URL`→ccr) | — |

## Ordem recomendada
**Fase 0 primeiro (sem nenhuma chave)** → depois junta as credenciais → **Fase 1**. Não precisa ter
nada configurado pra provar o encanamento.

### Passo 0 — Fase 0 (encanamento, zero secret)
```bash
./poc/phase0.sh
```
Builda a imagem, sobe Postgres, checa ferramentas e roda o loop com `StubEngine`. Se passar, a
infra está boa. **Só depois disto vale configurar o resto.**

### Passo 1 — GitHub App (acesso ao repo)
1. GitHub → *Settings → Developer settings → GitHub Apps → New GitHub App* (ou na org `arenavalendo`).
2. **Permissions (repository):** Contents RW, Issues RW, Pull requests RW, Metadata RO, Checks RO.
3. **Subscribe to events:** Issues, Pull request, Push.
4. **Webhook:** URL = `https://<seu-host>/webhook`; **secret** = gere e guarde → `GITHUB_WEBHOOK_SECRET`.
   (Local sem host público: use um túnel — cloudflared/ngrok — ou rode num VPS. Dá pra começar **sem
   webhook**, criando a issue e deixando o fleet reagir por polling/Telegram.)
5. **Generate a private key** (.pem) → o conteúdo vai em `GITHUB_APP_PRIVATE_KEY` (com `\n` escapados).
6. **Install App** no repo `arenavalendo/main` → o número na URL de instalação é o `GITHUB_APP_INSTALLATION_ID`.
7. O `App ID` está na página do App → `GITHUB_APP_ID`.
8. Para o **clone** no PoC: gere um **PAT fine-grained** (só `Contents: Read` no repo) → `GITHUB_CLONE_TOKEN`.

### Passo 2 — Telegram
1. Fale com **@BotFather** → `/newbot` → copie o token → `TELEGRAM_BOT_TOKEN`.
2. Descubra seu **user id numérico** (ex.: @userinfobot) → coloque em `TELEGRAM_ALLOWLIST` (vírgulas).

### Passo 3 — OpenRouter
openrouter.ai → crie uma API key → `OPENROUTER_API_KEY`. Confirme acesso a `qwen/qwen3-coder` e
`qwen/qwen-2.5-72b-instruct` (ajuste os ids em `poc/ccr.config.json` se necessário).

### Passo 4 — preencher e subir a Fase 1
```bash
cp poc/.env.poc.example poc/.env.poc   # preencha tudo; ROBOTO_ENGINE=claude_code
docker compose -f poc/compose.poc.yml --env-file poc/.env.poc up --build
```
O container: sobe o ccr → clona o repo → roda o daemon (servidor em `:8080` + laços). A partir daí,
uma issue no `arenavalendo/main` (ou uma mensagem no Telegram) vira trabalho do motor.

## Produção (depois do PoC)
Mesmo conjunto de valores, mas renderizados do **ansible-vault** (a única var no GitHub é
`ANSIBLE_VAULT_PASSWORD`, D4); 1 instância por empresa (D17); webhook num host público.
