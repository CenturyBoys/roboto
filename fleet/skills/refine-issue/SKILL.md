---
name: refine-issue
description: Refina uma issue do repo-alvo em uma issue ACIONÁVEL (engine-scoped) — o motor LÊ o repo pra fundamentar e produz Contexto/Escopo/Critérios de aceite/DoD. Dispare ao refinar uma issue antes de implementar, ou quando pedirem "refina a issue #N".
version: 1
---

# refine-issue — montar uma issue acionável lendo o repo

Seu trabalho é **ESCREVER a issue refinada** — NÃO executar a tarefa dela. Mesmo que a issue fale em
"discovery"/"mapear"/"levantar", você descreve **COMO fazê-lo** (escopo + critérios), não faz agora.

## Procedimento
1. **Leia o repo pra fundamentar** — no máximo ~10 consultas de leitura. Prefira **code-intel**
   (`workspace_symbols`/`find_references`/`document_symbols`) e ripgrep a `Read` de arquivo inteiro.
   NÃO varra o repo. Atingindo ~10 consultas (ou antes), **PARE e emita a proposta**.
2. **Produza as QUATRO seções**, nesta ordem e com estes títulos exatos:
   - `## Contexto` — fundamentado no código (cite arquivos/símbolos reais).
   - `## Escopo` — dentro / fora, explícito.
   - `## Critérios de aceite` — itens **verificáveis** `- [ ]` (podem estar sob subtítulos `### Teste N`).
   - `## DoD` — itens `- [ ]` (CI, testes, doc, i18n se houver). NUNCA omita o DoD.
3. Se faltar info, **preencha com o razoável** — mas as quatro seções SEMPRE aparecem.
4. NÃO edite arquivos nem abra PR.

## Saída
Emita o **corpo final da issue** — e NADA MAIS — entre os marcadores `===ISSUE-INICIO===` e
`===ISSUE-FIM===`, cada marcador sozinho na sua linha. Fora dos marcadores pode explicar; dentro, só o
markdown da issue (sem preâmbulo, sem cercas de código).

> Determinismo primeiro: a prontidão (DoR) é checada por regra depois — ver `validate-readiness`.
