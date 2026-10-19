# Trilha N2 · Motores de coding — matriz, contrato e reflexão (D22)

> PoC de pesquisa (out/2026) + contrato implementado. Fecha o desenho do **D22**: motor de coding
> como adapter externo (Claude Code, Codex) sob um contrato comum. Fontes: docs oficiais de cada
> motor (ver abaixo). Implementação: `src/roboto/engines/` + `src/roboto/app/engine_loop.py`.

## 1. O reframe (confirmado)

"Agente de coding" (Codex, Claude Code) **≠** `ModelGateway`. O motor tem **sessão própria**, usa
ferramentas, **faz perguntas**, pede **aprovação** e **retoma**. Logo: porta `CodingEngine`
(evolução de `Runner`, K), consumida pelo orquestrador; o `ModelGateway` continua para chamadas
primitivas (refino/judge). Ambos convivem.

## 2. Matriz de capacidades (o que é nativo vs. suprido pelo host)

| Capacidade | Claude Code (Agent SDK py) | Codex (SDK/app-server) |
|---|---|---|
| Start headless | ✅ `query()`/`ClaudeSDKClient` | ✅ `AsyncCodex.thread_start+turn` / `app-server` |
| Stream de eventos | ✅ `include_partial_messages` | ✅ `turn_handle.stream()` / `item/*` |
| **Aprovação por ação** | ✅ `can_use_tool` (*não* em tools pré-aprovadas) | ⚠️ **parcial**: só no app-server (`item/permissions/requestApproval`); SDK alto-nível é grosso |
| **Pedir input humano / pausar** | ⚠️ parcial: `AskUserQuestion` (model) ou deny+re-`query` | ⚠️ parcial: `tool/requestUserInput` + `turn/steer` (app-server) |
| Resume por sessão (sobrevive restart) | ✅ `session_id` + `resume=` | ✅ `threadId` + `thread_resume` |
| Interrupt/cancelar | ✅ `interrupt()` (só streaming) | ✅ `turn/interrupt` |
| Resultado estruturado + usage/custo | ✅ `ResultMessage.usage/total_cost_usd` | ✅ `TurnResult`+`thread.usage` |
| Auth headless | ✅ `ANTHROPIC_API_KEY` no env | ⚠️ `codex login --with-api-key` (grava credencial; env não basta) |

Dados em `src/roboto/engines/capabilities.py` (`CAPABILITIES[Engine] -> {Capability: level/mechanism/caveat}`).

## 3. Contrato comum (`CodingEngine`, implementado)

`start(spec) -> native_session_id` · `events() -> AsyncIterator[EngineEvent]` · `respond(answer)` ·
`interrupt()`. Eventos: `MESSAGE · TOOL_CALL · NEEDS_APPROVAL · NEEDS_INPUT · FINISHED · FAILED`.
Resume dobra em `start(resume_session_id=...)` (ambos suportam). O **id nativo** mapeia para
`session.native_session_id` (D23) — nunca confundido com o id interno.

**Driver** (`app/engine_loop.drive_turn`): start → cria `session` (mapeia nativo) → consome eventos;
`NEEDS_INPUT/NEEDS_APPROVAL` → `request_human_input` (D24) + execução `WAITING` (pausa); `FINISHED`
→ `VERIFYING`; `FAILED` → `FAILED`. Testado de ponta a ponta com `StubEngine` (sem rede).

## 4. Degradação graciosa por motor
- **Aprovação por ação**: Claude Code via `can_use_tool`; Codex via **app-server cru** (não o SDK
  alto-nível). O registro de motores marca isso `partial` → o host decide (ou cai para política de
  sandbox + gate humano no outbox, D7/D24) quando o motor não expõe o callback fino.
- **Pausa/retomada**: nenhum "pausa nativa" perfeito. Padrão adotado = **encerrar o turno na pergunta
  + `WAITING` + retomar com `resume_session_id`** quando a resposta humana chegar (vale p/ ambos).

## 5. O que o stub cobre e o que falta (gating honesto)
- **Coberto/testado agora:** contrato, matriz, driver ligando evento→sessão(D23)→interação(D24),
  estados `WAITING/VERIFYING/FAILED`, pergunta no outbox.
- **PoC real pendente** (precisa dos SDKs instalados + auth + sandbox — não dá no CI):
  1. Claude Code: ergonomia de **pausar+retomar** (deny+interrupt vs. `AskUserQuestion`) e o custo de
     re-`query` com `resume`. `interrupt()` só em streaming — o driver precisará do `ClaudeSDKClient`.
  2. Codex: **aprovação por ação** via SDK alto-nível é grossa (`auto/deny`) → confirmar se exige
     falar **JSON-RPC direto com o app-server**. Isto define se o CodexEngine usa o SDK ou o protocolo.
  3. Mapear usage/custo dos dois ao `llm_call` (D10) e estabilizar parsing (schema do `exec --json`
     é instável — usar SDK/app-server).

## 6. Reflexão crítica

**O que ficou bom.** O contrato é genuinamente o mínimo comum e os dois motores o atendem no
essencial (start, stream, resume por sessão, interrupt, resultado). O ponto mais valioso: o
**resume por id de sessão nativa sobrevive a restart** nos dois — isso valida o D23 (guardar o id
nativo) e o desenho "estado no banco, não no processo". O driver já exercita o loop interativo
inteiro contra um stub, então podemos construir o resto do fleet sem motor real na frente.

**Onde eu posso estar errado / riscos.**
- **Risco de alucinação na matriz.** Nomes exatos (`can_use_tool`, `include_partial_messages`,
  `AskUserQuestion`, `thread/resume`, `ApprovalMode`) vieram de pesquisa, não de execução. Alguns
  podem estar com nome/shape ligeiramente diferente na versão instalada. **A matriz é hipótese a
  confirmar por PoC**, não verdade — por isso ela carrega `caveat` e marca `partial`.
- **O ponto que mais ameaça o design é a aprovação fina no Codex.** Se o SDK não expõe aprovação
  por ação, o CodexEngine terá que falar app-server cru (mais código, protocolo JSON-RPC, acoplado a
  versão). Isso pode inverter a escolha "SDK vs. protocolo" e aumentar o custo do adapter do Codex.
- **"Pausar para humano" é a maior fricção conceitual.** Nenhum motor pausa de graça: o padrão
  real é *terminar o turno e retomar depois*. Isso é compatível com nosso `WAITING`+outbox, mas
  significa que uma pergunta no meio de um raciocínio longo **perde o estado em memória do turno** e
  depende da qualidade do resume — custo e fidelidade a medir (pode encarecer tokens no re-contexto).
- **Acoplamento de versão** (Codex empacota um binário do CLI; features gated por versão). O registro
  de motores precisa **pinar versão** e testar upgrade — senão um bump quebra o parsing/contrato.
- **`interrupt()` do Claude Code só em streaming** → o adapter real terá que usar `ClaudeSDKClient`
  (loop), não `query()` one-shot, se quisermos cancelamento — detalhe que muda a forma do adapter.

**Conclusão honesta.** O D22 está **resolvido no nível de contrato + registro + matriz + integração
testada por stub** — o suficiente para seguir construindo o loop. **Não** está validado contra os
motores vivos; o PoC real (itens §5) é o próximo passo e tem um risco concreto conhecido (aprovação
fina no Codex). Mantê-lo como gate explícito antes de implementar `ClaudeCodeEngine`/`CodexEngine`
é a decisão certa — não dá para "fingir" PoC de capacidade que depende de SDK+auth num ambiente sem eles.

## Fontes
- Claude Code: `code.claude.com/docs/en/agent-sdk/{python,permissions,streaming-output,mcp,structured-outputs}`, `.../sessions`, `.../headless`.
- Codex: `learn.chatgpt.com/docs/app-server`, `.../developer-commands`, `developers.openai.com/codex/noninteractive`, repo `openai/codex` (`sdk/python`, issues #41216, #50586).
