# Trilha K — Runtime containerizado

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Como deve ser o ambiente de execução do fleet? Ideia de partida (do dono): **rodar tudo em Docker**,
com auth dentro do container, Playwright quando precisar, e credenciais entregues com segurança.

## Arquitetura de sandbox (estado-da-arte)

Sandbox seguro de agente = **container não-root + filtro de egress + mounts read-only + timeout
estrito por task**. Flags Docker-chave:
- `--network=none` (ou egress allowlist), `--cap-drop=ALL`, `--read-only` (root FS imutável).
- **Isolamento mais forte para código não-confiável** (ex.: contribuição em repo público):
  `gVisor` (`--runtime=runsc`, kernel em user-space) ou **microVM Firecracker** — fronteiras bem
  mais fortes que container padrão. Provedores: E2B, Modal, Daytona, Docker Sandboxes.

### Isolamento para paralelismo (amarra Trilhas J e C)
**Cada agente = container efêmero próprio + git worktree dedicado** → trabalho paralelo e
livre de conflito. É o mecanismo concreto da prevenção de colisão da Trilha J.

### Egress
Políticas: open / **deny-all (default) + allow por domínio+CIDR** / CIDR deny, mutáveis no box.
Recomendado: **deny-all + allowlist** (GitHub, API do modelo/OpenRouter, feeds de segurança).

### Playwright
Imagem oficial do Playwright quando o agente precisa de navegação/login web (ex.: verificação de UI).

## Credenciais e secrets (crítico — amarra Trilha H)

Padrão moderno = **runtime injection**: o pipeline pede a credencial **no momento do uso**, recebe
um valor **curto** e usa só naquele passo. Okta relata **-92% de roubo** com token de **300s** vs. 24h
(número de vendor, **ilustrativo** — o argumento vale por least-privilege/blast-radius mesmo sem ele).
Regras: service account por estágio; secret escopado ao ambiente
(secret de prod só a partir do branch de prod); **identidade curta por agente** (certs tipo
Teleport), nunca API key longa; token **task-scoped e time-boxed** (minutos/horas).

### Ferramentas de secret
| Ferramenta | Modelo | Uso para nós |
|-----------|--------|--------------|
| **HashiCorp Vault / OpenBao** | **secrets dinâmicos** (gera sob demanda, lease curto, revoga) | ideal para injeção runtime; OSS free; tem overhead operacional |
| **SOPS** (CNCF) | cifra valores em YAML/JSON/.env, chaves legíveis → **git diff útil** | config estática cifrada no git; integra com Ansible (`community.sops`) |
| **Ansible Vault** | secrets **estáticos** (update manual) | pragmático para config estática simples, baixo overhead |

> Refina a ideia inicial do dono: symlink/estático serve para baixa sensibilidade, mas **preferir
> injeção runtime de credencial curta** (Vault/OpenBao ou token OIDC) para o que é sensível.

## Efemeridade vs. cache
Container descartável por task (segurança) **vs.** warm para cache (ex.: índice do code-intel ~23×,
número sem fonte primária → **ilustrativo**). Resolver por tipo: efêmero para execução; cache de
índices **read-only / por-projeto-confiável / assinado**, **nunca compartilhado entre tasks de código
não-confiável** (senão fura o isolamento — vetor de envenenamento de cache; usar gVisor/Firecracker nesse caminho).

## Recomendação
Container **não-root, efêmero, 1 por task + git worktree**, `--read-only` + `--cap-drop=ALL` +
**egress deny-all/allowlist**, timeout por task; **gVisor/Firecracker** para código não-confiável;
Playwright via imagem oficial sob demanda; secrets por **injeção runtime de credencial curta**
(Vault/OpenBao), SOPS/Ansible Vault só para config estática. É onde vive o runner da Trilha B.

## Perguntas em aberto
- [ ] Isolamento: **separar "código nosso" de "PR de terceiro"**. Como `roboto` é público e aceita PR
      externo, o caminho de **PR externo exige isolamento forte (gVisor/Firecracker) — não é opcional-MVP**;
      container padrão só para código confiável nosso.
- [ ] Vault/OpenBao agora, ou tokens OIDC curtos do próprio GitHub bastam no início?
- [ ] Estratégia de cache warm (code-intel) sem furar o isolamento efêmero.
- [ ] Validadores determinísticos de acesso/infra (SSL/disco/conectividade) como pré-condição do container.

---

### Fontes
- [AI Agent Sandboxing in 2026: Docker, E2B, Firecracker, gVisor, Modal, Daytona — amux](https://amux.io/guides/ai-agent-sandboxing/)
- [Sandboxing AI Coding Agents with Docker: Secure and Reproducible — yurtbay.dev](https://yurtbay.dev/blog/docker-sandboxes-ki-coding-agents/en/)
- [AI Agent Sandbox: How to Safely Run Autonomous Agents in 2026 — Firecrawl](https://www.firecrawl.dev/blog/ai-agent-sandbox)
- [Best Secrets Management Tools in 2026: Vault, OpenBao, Infisical — devtoollab](https://devtoollab.com/blog/best-secrets-management-tools)
- [HashiCorp Vault vs Ansible Vault — arnav.au](https://arnav.au/2025/12/12/hashicorp-vault-vs-ansible-vault/)
- [Least-Privilege Credentials for AI Agents: a Practical Guide — aitechconnect](https://aitechconnect.in/tips/least-privilege-credentials-ai-agents-oauth-secrets-2026)
- [The Hidden Risks of Secrets Mismanagement in CI/CD — Akeyless](https://www.akeyless.io/blog/the-hidden-risks-of-secrets-management-in-ci-cd-pipelines/)
