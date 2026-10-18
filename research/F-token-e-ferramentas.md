# Trilha F — Economia de token, ferramentas e ferramentificação

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

1. Como minimizar token por tarefa sem perder qualidade?
2. **Ferramentificação**: quando uma operação repetida deve virar artefato durável, e onde mora?

## Princípio da ferramentificação

Qualquer comando/fluxo usado "muitas vezes" vira tool durável. Reconstruir a chamada em linguagem
natural a cada sessão custa token e é não-determinístico; promover resolve os dois (= "determinismo
primeiro"). Caso-guia: **`ide_cc`** (CenturyBoys, o MCP `code-intel` desta sessão) — refactors
mecânicos viram tools verificadas por build. O LLM decide o *quê*; a tool faz o *mecânico*; o
validador *confere*.

## Evidência: ferramenta certa = ordens de magnitude de token

- **Busca por grafo/semântica vs grep-and-read**: 5 perguntas estruturais custaram **~3.400 tokens
  via grafo vs ~412.000 via grep+read** (10× menos tokens, 2,1× menos tool calls). É exatamente o
  que `code-intel` entrega (`find_references`, `call_hierarchy`, `blast_radius`).
- **Busca semântica (AST + BM25/vetor)** recupera as poucas funções relevantes em vez de ler
  arquivos inteiros → ~40% menos token; variantes "MCP-native" chegam a 84–88% menos tokens de leitura.
- **Ferramentas Rust**: ripgrep ~2,6× mais rápido que grep (5–20× em bases grandes, até 100× com
  `.gitignore`); fd ~2,5× mais que find. Respeitam `.gitignore` → output menor e mais focado (menos token).
  (Nota: o Grep do Claude Code é construído sobre ripgrep; versões recentes migraram parte para ugrep/bfs — detalhe sujeito a versão.)
- Greps "token-aware" (ex.: rustygrep `--llm`) comprimem a saída 60–95%.

> ⚠️ Os **múltiplos exatos** (3.400 vs 412.000; -58,6%; 60–95%) são de **medições específicas de
> blogs** (ilustrativos, possível cherry-pick). O **argumento qualitativo é robusto** (busca
> estrutural/semântica >> grep+read para símbolos); **medir no nosso caso** antes de citar número (Trilha L).

## Regra de roteamento de busca (determinismo + token)

| Preciso de… | Use |
|-------------|-----|
| Símbolos, refs, hierarquia, impacto, rename/move/extract | **code-intel / ide_cc** (semântico, verificado) |
| Busca semântica/cross-file por função relevante | **busca semântica (AST+vetor)** se adotarmos |
| Texto **literal** / arquivo único conhecido | **ripgrep/grep + glob** |

> code-intel já instrui: grep só para texto literal; símbolos sempre via tool semântica (grep corrompe
> strings/comentários/homônimos).

## Engenharia de contexto (as 3 estratégias)

"Mais token deixa o agente pior" — contexto inchado degrada qualidade, não só custo. Três alavancas:
- **Compaction** (trim/resumo/retenção seletiva): exemplo real 208K → 86K tokens (-58,6%).
- **Note-taking estruturado** (estado durável fora do contexto — amarra Trilha G).
- **Subagents** que isolam contexto e **retornam síntese** (Anthropic: multi-agente supera
  single quando os contextos são isolados). Ex.: Planner retorna um objeto `Plan` injetado só quando
  preciso, em vez de reescrever arquivos todo turno. (Amarra Trilha C.)
- **Programmatic tool calling**: resultados grandes ficam fora da janela.

## Taxonomia de artefato (critério de promoção)

- **Script de sistema** (`scripts/` da skill ou PATH) — ex.: exec padronizado na VPS.
- **Alias/função de shell** — atalhos triviais.
- **Tool/MCP** — operação com estado/índice/verificação/cache (ex.: ide_cc, busca semântica).
- **Skill** — procedimento multi-passo (Trilha C; partes determinísticas viram `scripts/`).
- **Base Rust/RTK** — ripgrep/fd/bat/sd como substrato mais enxuto que coreutils.

**Critério de promoção**: operação repetida ≥N vezes **ou** que reconstruir em NL custa token
relevante **ou** que precisa de determinismo → promover. Medir antes/depois (custo por run, Trilha H).

**Registro de ferramentas**: um `TOOLS.md`/índice para o fleet descobrir o que já existe e não
reinventar (candidato a regra no AGENTS.md, Trilha E).

## Perguntas em aberto
- [ ] Adotamos busca semântica (AST+vetor) além do code-intel, ou code-intel + ripgrep bastam?
- [ ] Qual o stack Rust base padrão do runtime (Trilha K)?
- [ ] Formato do registro de ferramentas (`TOOLS.md`) e quem o mantém atualizado.
- [ ] Orçamento de token por tipo de agente (amarra com observabilidade, Trilha H).

---

### Fontes
- [Semantic Code Search vs Grep for Coding Agents 2026 — particula.tech](https://particula.tech/blog/semantic-code-search-vs-grep-coding-agents)
- [CodeGrok MCP: Semantic Code Search That Saves 10x Context — HackerNoon](https://hackernoon.com/codegrok-mcp-semantic-code-search-that-saves-ai-agents-10x-in-context-usage)
- [How Faster CLI Tools Speed Up AI Coding Agents by 2–3× — Medium](https://medium.com/@abhishekuniyal/i-cut-agent-dev-loops-by-2-3x-with-a-better-cli-stack-4e4ed013cfb6)
- [rustygrep: token-efficient grep for AI coding agents — GitHub](https://github.com/AkashPriyadarshii/rustygrep)
- [Context Engineering: memory, compaction, and tool clearing — Claude Platform Cookbook](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools)
- [Less Context, Better Agents: Efficient Context Engineering (arXiv)](https://arxiv.org/pdf/2606.10209)
- [Context Engineering: Why More Tokens Makes Agents Worse — Morph](https://www.morphllm.com/context-engineering)
- [ide_cc (CenturyBoys)](https://github.com/CenturyBoys/ide_cc)
