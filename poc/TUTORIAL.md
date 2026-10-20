# Tutorial — configurar e rodar o fleet (genérico e repetível)

Vale para **qualquer empresa/repo** (troque os `<placeholders>`). Faça **uma vez por empresa**; pra
uma nova empresa, repita com outro `.env.poc` (mesma imagem — D27). Tudo que você preenche vive num
único arquivo: **`poc/.env.poc`** (gitignored).

## 0. Pré-requisitos (uma vez na máquina)
- **Docker** + **docker compose** instalados e rodando.
- Este repo (`roboto`) clonado. Nada de Python/Node local — tudo roda no container.

## 1. Checklist do que preencher (`poc/.env.poc`)
| Variável | Para quê | Obrigatório | Onde conseguir (Parte 2) |
|---|---|---|---|
| `ROBOTO_TENANT` | nome curto da empresa | sim | você escolhe (ex.: `<empresa>`) |
| `TARGET_REPO_URL` | repo-alvo (https) | sim | `https://github.com/<owner>/<repo>.git` |
| `ROBOTO_DEFAULT_REPO` | `<owner>/<repo>` | sim | idem |
| `ROBOTO_ENGINE` | `stub` (Fase 0) / `claude_code` (Fase 1) | sim | — |
| `OPENROUTER_API_KEY` | modelos Qwen (motor + gateway) | sim | §2.1 |
| `GITHUB_API_TOKEN` | API: abrir PR/issue | sim (modo PAT) | §2.2 |
| `GITHUB_CLONE_TOKEN` | clonar repo privado (https) | sim (modo PAT) | §2.2 (mesmo token) |
| `TELEGRAM_BOT_TOKEN` | canal humano | sim | §2.3 |
| `TELEGRAM_ALLOWLIST` | user IDs autorizados | sim | §2.3 |
| `ROBOTO_CHAT_ID` | chat p/ perguntas do motor | sim p/ Fase 1 | §2.3 |
| `CONSOLE_TOKEN` | bearer do console web | opcional | você escolhe |
| `STT_API_KEY` | transcrição de áudio | opcional | §2.4 |
| `GITHUB_APP_*` | modo App (produção) | não (deixe vazio) | §2.5 |

## 2. Como conseguir cada credencial

### 2.1 OpenRouter (modelos Qwen)
1. Crie conta em **openrouter.ai** → *Keys* → **Create key**. Copie → `OPENROUTER_API_KEY`.
2. Garanta crédito e acesso a `qwen/qwen3-coder` e `qwen/qwen-2.5-72b-instruct` (ajuste os ids em
   `poc/ccr.config.json` se o seu plano usar outros).

### 2.2 GitHub — modo PAT (1 token para git + API; recomendado)
1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens** →
   **Generate new token**.
2. **Resource owner:** a conta/org dona do repo. **Repository access:** *Only select repositories* →
   escolha **`<owner>/<repo>`**.
3. **Permissions (Repository):** **Contents: Read and write** · **Issues: Read and write** ·
   **Pull requests: Read and write**. (Metadata fica Read automático.)
4. Gere, copie o token (`github_pat_...`) → cole em **`GITHUB_API_TOKEN`** e também em
   **`GITHUB_CLONE_TOKEN`** (o mesmo serve pra clonar via https).

### 2.3 Telegram (bot + quem pode falar)
1. No Telegram, fale com **@BotFather** → `/newbot` → siga os passos → copie o token →
   `TELEGRAM_BOT_TOKEN`.
2. Descubra seu **ID numérico**: fale com **@userinfobot** (ele responde seu `id`). Coloque em
   **`TELEGRAM_ALLOWLIST`** (vírgulas p/ vários). Para o motor te perguntar, o mesmo chat vai em
   **`ROBOTO_CHAT_ID`** (seu id, ou o id do grupo).
3. Mande qualquer mensagem pro seu bot uma vez (pra abrir conversa).

### 2.4 STT (opcional — só se for testar áudio)
Chave de um endpoint compatível (ex.: OpenAI Whisper) → `STT_API_KEY` (e `STT_BASE_URL` se não for a OpenAI).

### 2.5 GitHub App (opcional — produção, deixe vazio no PoC)
Só quando quiser identidade de robô + webhooks + multi-repo. Ver `poc/SETUP.md` §App. No PoC PAT,
deixe `GITHUB_APP_*` e `GITHUB_WEBHOOK_SECRET` em branco.

## 3. Preencher
```bash
cp poc/.env.poc.example poc/.env.poc   # gitignored
# edite poc/.env.poc e cole os valores das etapas acima
```

## 4. Validar (reexecutável — rode quantas vezes quiser)
```bash
./poc/phase0.sh        # 1ª vez: builda a imagem e prova o encanamento (sem token)
./poc/check-config.sh  # diz CONFIG OK ou exatamente o que falta
```

## 5. Rodar
```bash
# Fase 0 (sem secrets): só o encanamento
ROBOTO_ENGINE=stub ./poc/phase0.sh

# Fase 1 (motor vivo): preencha tudo, ROBOTO_ENGINE=claude_code
docker compose -f poc/compose.poc.yml --env-file poc/.env.poc up --build
```
A partir daí: mande uma mensagem no Telegram do bot (vira issue), ou crie uma issue e dispare pelo
chat. O console fica em `http://localhost:8080` (header `Authorization: Bearer <CONSOLE_TOKEN>`).

## 6. Repetir para outra empresa
Copie `poc/.env.poc` para outro arquivo (ex.: `poc/.env.<empresa>`), troque `ROBOTO_TENANT`,
`TARGET_REPO_URL`/`ROBOTO_DEFAULT_REPO`, o PAT, o bot do Telegram — e suba com `--env-file` apontando
pra ele. **Mesma imagem, config diferente** (é o princípio do fleet manager, D27).

## Segurança (sempre)
`poc/.env.poc` é gitignored — **nunca** commite. Token com escopo mínimo (só o repo, só as permissões
da §2.2). O fleet **nunca** commita direto em `main`/`develop` (branch + PR) e o merge tem gate humano.
