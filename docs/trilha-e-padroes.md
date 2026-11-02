# Trilha E — AGENTS.md e padrões de código (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/E-agents-md-e-padroes.md`](https://github.com/CenturyBoys/roboto/blob/main/research/E-agents-md-e-padroes.md).
> **Princípio-âncora:** "se o agente precisa disso pra escrever código **correto**, está no AGENTS.md".
> Tudo que um linter/formatter/type-checker impõe vai pra **config da ferramenta**, não pra prosa.
> **Status:** regras do roboto no `AGENTS.md` + **injeção determinística das convenções do repo-alvo**
> no `main`.

## 1. O que a trilha entrega

Duas coisas: (a) o **`AGENTS.md` do roboto** como contrato de código do próprio fleet; e (b) o motor
**seguir as convenções do REPO-ALVO** quando implementa nele — não as do roboto. O repo-alvo tem o
próprio `AGENTS.md`; o fleet precisa respeitá-lo pra o PR nascer no estilo da casa.

## 2. AGENTS.md é código (regras do roboto)

- **Imperativo e específico**, exemplo de código > prosa, comandos exatos com flags.
- Decisões que o agente não infere: stack **Python · async**, retorno **`Result[Ok, Error]`**
  (ok/erro explícito, sem exceção pra fluxo), limites operacionais ("o que o agente NUNCA faz" —
  inclui **sem co-autor** em commit/PR).
- **< 500 linhas** (entra no contexto a cada ação → custo de token fixo, trilha F/L).
- **AGENTS.md é atualizado no MESMO PR** que muda a convenção → entra na DoD (trilha A) e é cobrado
  pelo doc-guard.
- Naming vs comentário: **nome semântico 1º, estrutura 2º, comentário por último** (só o *porquê*).
  Proibido `temp/val/res`; type hints sempre. O que o linter pega não vira prosa (nem ruído de review
  na trilha D).

## 3. Convenções do repo-alvo injetadas pelo harness (determinismo primeiro)

Antes o motor só era **instruído** a "ler o AGENTS.md do repo-alvo você mesmo" — podia ignorar, e
gastava token descobrindo/lendo (contra a trilha F). Agora o **harness lê e injeta**:

| Peça | O que faz | Onde |
|---|---|---|
| **perfil operacional** | pm, monorepo, scripts test/lint, deps já instaladas | `app/repo_profile.build_repo_profile` |
| **convenções (novo)** | lê o `AGENTS.md` (ou `CLAUDE.md`) do repo-alvo e injeta o conteúdo | `app/repo_profile.read_agents_conventions` |
| **injeção no prompt** | perfil + convenções entram no prompt de implement, por-run (sempre fresco) | `app/pr_cycle.py` |

- **Capado pelo orçamento de token** (`max_chars`, ~6k ≈ 1.5k tokens): o `AGENTS.md` do alvo não é
  nosso; se exceder, trunca e aponta pro arquivo completo no cwd.
- **Determinístico:** sem LLM, roda por-run — pega mudança no `AGENTS.md` do alvo sem re-boot.
- **Fallback:** `AGENTS.md` → `CLAUDE.md`; nenhum → bloco vazio (não polui o prompt).

## 4. Fonte da verdade e follow-ups

O `AGENTS.md` do repo-alvo é a **fonte da verdade** das convenções daquele repo; o harness o entrega
ao motor em vez de depender da descoberta pelo modelo. O `AGENTS.md` do roboto é o contrato do fleet.

**Follow-ups (backlog):** parsear config de linter/tsconfig do alvo (hoje injetamos o `AGENTS.md`, não
regras de lint — que o motor roda via script); `AGENTS.md` por nível em monorepo ("mais próximo
vence"); injetar as convenções também no refino (hoje: implementação).
