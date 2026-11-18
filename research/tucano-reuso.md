# Reuso do Tucano — análise e deltas (2026-11-18)

> *Porquê* / decisão de arquitetura. O *como funciona hoje* vive em
> [`docs/trilha-h-qualidade.md`](../docs/trilha-h-qualidade.md).

## Fonte e licença

[**Tucano**](https://github.com/eduwxyz/tucano) — "team of AI agents" em TypeScript/Electron, roda
sobre Claude Code/Codex/Cursor/Grok/Cline/Hermes/OpenCode/Pi. **Licença Apache-2.0** → podemos
derivar código/design mantendo atribuição. Nada é copiado literal (eles são TS, nós Python); o que
reusamos é **design**, reimplementado idiomático (`Result`, async, mypy strict). Esta nota é a
atribuição.

Também avaliados (contexto): **OpenBot** (nightly-labs, PolyForm **Noncommercial** → não reusável) e
**OpenMausBot** (milind-soni, Apache-2.0). Mesmo nicho: "seu time de bots num chat, bring-your-own-
engine, local-first, aprove-o-que-importa".

## Veredito — ganho real, não porte de tudo

O `roboto` já tinha ~85% do que o Tucano oferece, em Python. Cruzamento (o que já existe × gap):

| Item deles | Já temos | Gap real |
|---|---|---|
| Adapters de motor | `engines/port.py` + `claude_code.py` | callback de aprovação, interrupt |
| LLM/endpoint (OpenRouter/local) | `llm/openrouter.py` (`base_url` configurável) | **nenhum** — cobre Ollama/vLLM |
| Policy/aprovação | `approval_guard` (digest=`approvalHash`), `tool_policy`, `jev_guard` | enforcement não ligado; autonomia não graduada |
| Budget/token | `metering`, `budget`, corte por-run (#242) | só falta flag `pause`; custo/issue já derivável |
| Sessões/IDs | `run/session/interaction/llm_call/session_event` | — |
| Isolamento de HOME | roda em container efêmero (home limpo) | N/A |

**Conclusão:** "fazer todos" colapsa de 6 para **3 issues** de ganho real.

## As 3 issues

- **#265 (feito):** enforcement de aprovação por ação — liga `can_use_tool` ao `approval_guard` +
  `SessionHub` + `interaction`; `interrupt()` cooperativo. Derivado do "harness executa o call
  aprovado, ligado por hash" do Tucano.
- **#267:** policy de 2 eixos (`verdict()` puro) — tool-class × autonomia por ação (commit/push/pr/
  merge/delete), high-risk sempre bloqueia (reusa `jev_guard`), **outside-content guard** (anti
  prompt-injection). Fraqueza concreta que cobre: `tool_policy` é estático/binário (`Bash` tudo-ou-
  nada); `jev_guard` só surfa. **Decisão arquitetural** — depende de #265, passa por gate humano (D7).
- **#266:** guard de sessão — rotacionar `native_session_id` quando muda model/effort/system/tools
  (`sessionConfig`-hash), pro switcher de modelo por etapa não retomar sessão sob config incompatível.

## Fora de escopo (já coberto / não se aplica)
- Casca Electron/desktop + metáfora "channels de chat" (nossa verdade é a **issue**, não o chat).
- Motor "sem arquivos do projeto" (eles dão `cwd` vazio + tudo via gateway MCP; nós editamos o repo).
- `endpoint.ts` (já temos equivalente), isolamento de HOME (container), budget pause (trivial).
