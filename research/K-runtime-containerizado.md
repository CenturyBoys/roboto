# Trilha K — Runtime containerizado

> Status: ESQUELETO (pesquisa não iniciada)

## Pergunta

Como deve ser o ambiente de execução do fleet? Ideia de partida (do dono): **rodar tudo numa
máquina/container Docker**, com login/auth dentro do container, Playwright disponível quando
precisar de navegação web, e credenciais entregues via symlink/sync.

Vantagens: reprodutível, isolado, efêmero e fronteira de segurança natural para um agente com
credenciais e push access.

## A pesquisar / decidir

- [ ] **Imagem base**: Claude Code headless + toolchain + Playwright (imagens oficiais do Playwright).
- [ ] **Auth dentro do container**: como persistir sessões de login (GitHub, serviços) de forma segura.
- [ ] **Playwright**: quando o fleet realmente precisa de browser (logins web, verificação de UI).
- [ ] **Credenciais** (crítico — amarra com Trilha H / segurança):
      - nunca assar segredo na imagem;
      - montar **read-only**, least privilege (token GitHub de escopo mínimo);
      - symlink/sync vs. secret manager — avaliar; preferir o mais auditável.
- [ ] **Gestão de secrets**: avaliar **Ansible Vault** vs **HashiCorp Vault** (e SOPS) para
      guardar/entregar/rotacionar secrets; injeção em runtime vs. symlink.
- [ ] **Validadores determinísticos de acesso/infra** (determinismo primeiro, SEM LLM): checks de
      SSL/certificados, disco, conectividade/portas e saúde de credenciais como **pré-condição**
      antes de o agente agir. Amarra com Trilha J (health) e H (segurança).
- [ ] **Efemeridade vs. cache**: container descartável por tarefa vs. warm para cache (ex.: índice do code-intel).
- [ ] **Onde roda**: VPS única vs. orquestração (um container por tarefa/worktree) — amarra com Trilhas B e J.
- [ ] **Isolamento entre tarefas paralelas** (worktrees/containers separados) para evitar conflito.

## Saída esperada

Desenho do runtime (imagem, modelo de auth, política de credenciais, efemeridade, isolamento)
que vira base da orquestração (Trilha B) e herda as regras de segurança (Trilha H).
