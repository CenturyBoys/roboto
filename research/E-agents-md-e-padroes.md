# Trilha E — AGENTS.md e padrões de código

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Quão completo deve ser o `AGENTS.md`? Qual padrão usar/evitar? E a hipótese do dono: **naming
verboso/auto-descritivo para escrever menos comentário** se sustenta?

## AGENTS.md — o padrão (2026)

`AGENTS.md` é o **padrão aberto de fato** (20k+ repos, formalizado em ago/2025): um Markdown na
raiz que diz ao agente como buildar, testar e mudar o projeto. `CLAUDE.md` aponta para ele
(confirma o plano do dono).

### Princípios
- **Papel específico**, não "assistente prestativo".
- **Exemplo de código > prosa.**
- **Imperativo e específico**: "Use pnpm, não npm" > "preferimos pnpm".
- **Comandos exatos**, com flags — não descrições vagas.

### Seções recomendadas
Overview (linguagem/framework + versões) · comandos de build/test exatos · estilo de código
(**só o que difere do default da linguagem**) · como rodar a suíte/um teste/o que mockar ·
estrutura de diretórios · git workflow · **limites operacionais (o que o agente NUNCA faz)** ·
decisões de arquitetura que o agente não consegue inferir · implementações canônicas a seguir.

### O que EXCLUIR (determinismo primeiro + token)
- **Qualquer coisa que um linter/formatter/type-checker já imponha** → vai para a **config da
  ferramenta**, não para prosa. (= ferramentificação do padrão, Trilha F. Regra determinística >
  texto que o agente pode ignorar.)
- Qualquer coisa já no README que o agente pode ler → **cross-reference, não duplique**.
- Diretrizes aspiracionais → só regras para seguir em **toda** ação.

### Tamanho / token
**< 500 linhas**, sweet spot **200–500** — o arquivo entra no contexto a cada ação; token importa.
Monorepo: múltiplos `AGENTS.md` por nível, o **mais próximo vence**.

> Cross-link Trilha F/C/L: se o AGENTS.md inteiro entra **a cada ação**, 200–500 linhas é **custo de
> token fixo** → contabilizar no orçamento (Trilha L) ou aplicar carregamento progressivo (seções sob demanda).

### Regra de decisão
"Se o agente precisa disso para escrever código **correto**, está no AGENTS.md." Nada além disso.

### AGENTS.md é código
Atualizado **no mesmo PR** que muda a convenção → entra na **DoD** (Trilha A). Liga à fase
*Constitution* do Spec Kit (Trilha A).

## Naming vs comentários — hipótese do dono SUPORTADA (fontes fracas)

Hierarquia de clareza (pesquisa 2026): **naming 1º, estrutura 2º, comentário por último.** Nomes
bons + funções focadas carregam a maior parte da clareza.

- `calculateMonthlyInterest(principal, rate, months)` se explica; `calc(p, r, m)` exige 3 linhas de
  comentário só para compensar o naming ruim.
- **Anti-padrão de IA**: pegar código mal-nomeado e pedir ao LLM para **comentar o QUE ele faz**.
  O certo é estruturar para o que faz ser **óbvio**, e reservar comentário para o **PORQUÊ**
  (contexto de negócio, edge cases).
- **Comentário bom = PORQUÊ, não O QUÊ.** Comentário desatualizado é **pior que nenhum** (mente).
- Copilot, sem prompt explícito, usa nomes genéricos (`temp/val/res`) e pula type hints → nosso
  AGENTS.md precisa **mandar** nomes semânticos + tipos.

> ⚠️ Postura cética: a evidência (HackerNoon + 1 arXiv) é **fraca** para "validado". Contra-argumento:
> em código denso/algorítmico, comentário-o-quê pode ajudar. Tratar como **suportado pela literatura
> disponível**, não comprovado.

### Regras de padrão que isso gera (para o AGENTS.md)
- [ ] Identificadores **descritivos e semânticos**; proibir `temp/val/res/data/foo`.
- [ ] **Type hints/tipagem** sempre que a linguagem suportar.
- [ ] **Comentário só para o PORQUÊ** (negócio, edge case, decisão não-óbvia); nunca reescrever o código.
- [ ] Funções pequenas e focadas (clareza via estrutura).
- [ ] Tudo que der → **linter/formatter/type-check** (determinismo), não prosa no AGENTS.md.

Benefício duplo: menos token (menos comentário, menos prosa no AGENTS.md) **e** menos ruído de
review (Trilha D não reflaga o que o linter pega).

## Perguntas em aberto
- [ ] Stack inicial do `roboto` (linguagem/framework) para fixar os comandos exatos e o linter?
- [ ] Quais regras entram no linter/formatter (determinístico) vs no AGENTS.md (julgamento)?
- [ ] Esqueleto do AGENTS.md do roboto — escrever agora (curto) ou ao sair da pesquisa?

---

### Fontes
- [AGENTS.md Spec (2026): seções + AGENTS.md vs CLAUDE.md vs .cursorrules — morphllm](https://www.morphllm.com/agents-md-guide)
- [AGENTS.md Complete Guide for Engineering Teams (2026) — BuildBetter](https://blog.buildbetter.ai/agents-md-complete-guide-for-engineering-teams-in-2026/)
- [How to Build Your AGENTS.md — Augment](https://www.augmentcode.com/guides/how-to-build-agents-md)
- [The "Comment" Fallacy: Why Self-Documenting Code is Still the Goal — HackerNoon](https://hackernoon.com/the-comment-fallacy-why-self-documenting-code-is-still-the-goal)
- [Talking to Itself While Coding: What Makes Comments Help Code Generation? (arXiv)](https://arxiv.org/pdf/2609.09242)
