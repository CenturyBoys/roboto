# Trilha C — Design de skills

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)
>
> ✅ **Decidido** (ver `DECISOES-A-FECHAR.md`): skills em `.claude/skills/` no `roboto`, versionadas
> e revisadas por composição (D14).

## Pergunta

Qual a granularidade e a composição certas de skills para os 9 agentes (Trilha 0), maximizando
reuso e **economia de token**?

## Anatomia de uma skill (Agent Skills / SKILL.md)

Pasta auto-contida: **`SKILL.md`** (frontmatter YAML obrigatório: `name` + `description` + instruções)
· **`scripts/`** (código executável opcional) · **`references/`** (docs lidos sob demanda) ·
**`assets/`** (templates/dados).

### Progressive disclosure (a alavanca de token) — 3 tiers
- **Tier 1 — Catálogo**: `name` + `description` de toda skill no início da sessão (~50–100 tokens/skill).
- **Tier 2 — Instruções**: corpo do `SKILL.md` só quando a task casa (**≤ 5000 tokens / ≤ 500 linhas**).
- **Tier 3 — Recursos**: `scripts/`/`references/`/`assets/` só quando referenciados.

> 20 skills instaladas NÃO custam 20 conjuntos de instrução upfront. É o mecanismo central de
> economia de token do fleet (amarra com Trilha F).

> ⚠️ Os limites (~50–100 tokens/skill no Tier 1; ≤5000 tokens no Tier 2) são **diretriz das best
> practices da plataforma / heurística de projeto**, não limite técnico rígido.

## Granularidade

- **"A skill tem que caber na sua cabeça"**: se precisa de mais que um parágrafo de doc, provavelmente
  são duas skills.
- Muito estreita → carrega skills demais (overhead); muito larga → difícil de **triggar** com precisão.
- Alvo: **uma unidade coerente de trabalho que compõe** com outras.
- `description` afiada = trigger preciso (Tier 1 decide quando a skill é carregada).

## Matriz de decisão — skill vs tool/MCP vs subagent vs script

| Precisa de… | Use | Por quê |
|-------------|-----|---------|
| Operação pontual, padronizada, baixa variância | **MCP tool** (ex.: code-intel, gh) | Agente decide *qual* tool e *quando* |
| Conhecimento procedural + workflow + expertise embutida | **Skill** | Agente decide qual/quando **e como**; compõe |
| Passo determinístico repetido | **Script** (dentro de `scripts/` da skill) | Determinismo primeiro + ferramentificação (Trilha F) |
| Contexto que estouraria / especialista de toolset estreito / paralelizável | **Subagent** | Isola execução; **retorna síntese, não transcript** |

### Padrão de composição do fleet
`orquestrador (mantém contexto global) + skills (capacidades reutilizáveis) + subagents (execução
isolada) + MCP tools (operações pontuais)`. Cada um dos 9 agentes é um papel orquestrado por essas peças.

## Catálogo candidato de skills (por agente da Trilha 0)

- **Refinamento**: `refine-issue`, `validate-readiness` (o gate da Trilha A)
- **Planejamento/Arquitetura**: `decompose-epic`, `plan-issue`, `write-adr`
- **Implementação**: `implement-issue`, `open-pr`, `fix-ci`
- **Review**: `review-pr` (orquestra subagents por dimensão — Trilha D)
- **Testes**: `write-tests`, `expand-coverage`
- **Segurança**: `triage-advisory` (ambiente/feed), `triage-scan-findings`
- **Docs**: `sync-docs`, `detect-doc-drift`
- **SRE/Incidente**: `triage-incident`, `correlate-signals` (ambiente/alerta; entra quando houver produção)

> Alinhamento com a Trilha 0 (9 agentes): aqui **Arquitetura está fundida com Planejamento** e
> **SRE/Incidente** entra quando houver software em produção — decisão explícita, não omissão.

Cada skill: `description` afiada, `scripts/` para as partes determinísticas (ferramentificação),
`references/` carregados sob demanda, **versionada** e **testada contra tasks reais** (insumo de evals, Trilha H).

## Segurança de skills (compositional supply chain)
Pesquisa 2026 (**CompoSkill**): skills que passam individualmente num scanner podem **compor um
ataque em cadeia**. → review de skill não é só por skill isolada; precisa olhar composição.
Amarra com a Trilha H (segurança do próprio fleet).

## Impacto em token
- Progressive disclosure = principal alavanca (catálogo barato, corpo só quando casa, recursos sob demanda).
- Partes determinísticas viram script (não re-descritas em NL a cada uso).
- Subagent retornando síntese protege o contexto do orquestrador.

## Perguntas em aberto
- [ ] MVP de skills cobre quais passos primeiro? (sugestão: `refine-issue` + `validate-readiness`
      + `implement-issue` + `open-pr` + `review-pr`).
- [ ] **Onde as skills vivem** — decisão de **segurança** (afeta supply chain / CompoSkill), não detalhe:
      proposta inicial `.claude/skills/` no `roboto`, versionadas e **revisadas por composição**; plugin depois.
- [ ] Política de versionamento e teste de skill antes de "instalar" no fleet.

---

### Fontes
- [Agent Skills — Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Skill authoring best practices — Claude Platform Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Skills vs Tools vs MCP vs Subagents vs Hooks: 2026 Comparison — dev.to](https://dev.to/miaoshuyo/skills-vs-tools-vs-mcp-vs-subagents-vs-hooks-2026-ultimate-comparison-kpi)
- [Agent, Sub-Agent, Skill, or Tool? A Practitioner's Guide (techrxiv)](https://www.techrxiv.org/doi/pdf/10.36227/techrxiv.177204917.78786098/v1)
- [CompoSkill: Compositional Skill Chain Attacks (arXiv)](https://arxiv.org/pdf/2608.16246)
