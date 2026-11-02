# Trilha C — Skills do fleet (como funciona)

> Documento **operacional**. O *porquê* está em
> [`research/C-design-de-skills.md`](https://github.com/CenturyBoys/roboto/blob/main/research/C-design-de-skills.md).

## 1. O que são as skills do fleet

As **convenções do fleet** (como refinar, validar, implementar, abrir PR, revisar) empacotadas como
**skills com progressive disclosure**: o motor carrega a skill só quando precisa daquele passo, em vez
de carregar um prompt gigante. Antes essas regras viviam hardcoded nos prompts do orquestrador — agora
são **artefatos versionados e revisáveis**.

## 2. Onde vivem (e por quê separadas)

- **`fleet/skills/`** (no repo `roboto`) — as skills que o **motor** usa trabalhando em **repos-alvo**.
  Versionadas, revisadas por composição.
- Separadas do **`.claude/skills/`** do roboto (ex.: `docs`, `github`), que são pra quem trabalha **no
  próprio roboto** — não pro motor em repos-alvo.

**Por quê separar:** o Claude Code descobre skills no `.claude/skills/` do **cwd** + no `~/.claude/
skills` global. O motor roda com cwd no repo-alvo (`/work/<repo>`) — então ele **não** vê o
`.claude/skills/` do roboto. Por isso as skills do fleet moram em `fleet/skills/` e são **expostas ao
motor** via `~/.claude/skills` no container.

## 3. Como o motor usa

O entrypoint do container **symlinka** `fleet/skills/` → `~/.claude/skills/` da imagem. Assim o motor
acha as skills em **qualquer repo-alvo** (progressive disclosure pelo `description` da skill).

## 4. O MVP (o core do loop)

| Skill | Quando dispara |
|---|---|
| `refine-issue` | montar uma issue acionável lendo o repo (engine-scoped) |
| `validate-readiness` | decidir se a issue está pronta (DoR em 3 camadas) |
| `implement-issue` | codar a issue (escopo mínimo, testes, checks verdes) |
| `open-pr` | abrir o PR (GitFlow + Conventional Commits + Closes) |
| `review-pr` | revisar o PR (reviewer≠autor, findings estruturados) |

## 5. Versionamento e teste (antes de "instalar")

- Cada `SKILL.md` tem `version:` no frontmatter. Bump = mudou o procedimento.
- **Revisão por composição:** mudança numa skill é um PR revisado (reviewer≠autor) — a skill é código.
- **Teste antes de valer:** a skill nova roda primeiro num repo-alvo de teste (PoC contra
  `arenavalendo`) e só então entra no fluxo. Supply-chain: skill de terceiro não entra sem revisão.

## 6. Relação com o código

As skills **codificam** o que o orquestrador já faz (os prompts de `app/loops.py`, `app/pr_cycle.py`,
`agents/review.py`). A fonte da verdade do *gate* continua no código (determinismo primeiro: DoR por
regra, veredito por `aprovado_por_findings`); a skill é o **procedimento** que o motor segue.
