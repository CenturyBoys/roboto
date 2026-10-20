# Registro de ferramentas do fleet (economia de token — Trilha F)

Índice do que o fleet já tem, pra **não reinventar** e pra **gastar menos token** (F). Regra de ouro:
operação repetida / que custa token em NL / que precisa de determinismo → vira ferramenta durável.

## Ferramentas de código (o motor usa estas, não força bruta)
| Preciso de… | Ferramenta | Por quê |
|---|---|---|
| Símbolos, refs, hierarquia, impacto, rename/move/extract | **code-intel (`ide_cc`)** — MCP, 23 tools | semântico + verificado por build; ~10× menos token que grep+read |
| Texto **literal** / arquivo conhecido | **ripgrep (`rg`)**, **fd** | respeita `.gitignore` → saída menor/focada |
| Editar/validar | tools de edição do code-intel (apply verificado) | edita só se o build/net_delta valida |

**Roteamento (no prompt do motor):** símbolos → code-intel; texto literal → ripgrep; **evitar ler
arquivo inteiro**. grep corrompe strings/comentários/homônimos — só para texto literal.

## Como está ligado
- **Imagem** (`poc/Dockerfile`): instala `ripgrep`+`fd-find` e o **`ide_cc`** (`code-intel-mcp` em
  `~/.local/bin`, via `install.sh INSTALL_LSP=1`).
- **Motor** (`engines/claude_code.ClaudeCodeEngine`): recebe `mcp_servers` → `{"code-intel": ...}`
  quando `ROBOTO_CODE_INTEL=1` (default). Assim o Claude Code enxerga os 23 tools semânticos.
- **Config**: `ROBOTO_CODE_INTEL` (1/0).

## Artefatos internos (ports/adapters do próprio fleet)
`Store` · `Channel` · `ModelGateway`/`Transcriber` · `Publisher`/`RouterPublisher` · `CodingEngine`
· `GithubAppClient` (issue/PR) · `correction_cycle` · `check_issue_readiness`/`review_pr`.

## Medição (pinar por medição, não por fé — F/L)
O custo real por run deve sair do **OpenRouter/`llm_call`** (D10), não do rótulo do `claude` (que
reporta preço de Opus mesmo rodando Qwen). Medir token antes/depois do code-intel p/ comprovar o ganho.

## Em aberto (F) — ainda NÃO ligado
- **Busca semântica AST+vetor** além do code-intel (decisão: code-intel+ripgrep bastam?).
- **Context engineering**: compaction / note-taking (liga G) / subagents que retornam síntese.
- **Orçamento de token por tipo de agente** (liga H/L).
- **Warm container** p/ cache do índice do code-intel (~23×) — hoje é efêmero (re-indexa por run).
