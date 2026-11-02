---
name: implement-issue
description: Implementa uma issue PRONTA no repo-alvo — escopo mínimo, testes, checks verdes, doc-in-sync. Dispare ao implementar/codar uma issue, ou quando pedirem "implementa a issue #N".
version: 1
---

# implement-issue — codar a issue (escopo mínimo)

Só implemente issue **PRONTA** (DoR — ver `validate-readiness`). Entregue um PR; o **merge é humano**.

## Regras de escopo
- Entregue **APENAS** o que os Critérios de aceite pedem — nada além.
- **NÃO** crie documentos/arquivos extras (breakdown, "update" de épico), **NÃO** edite o épico nem
  outras issues, **NÃO** toque em código não relacionado.
- **NÃO** commite lockfile/deps sem a issue exigir.
- Trabalho FUTURO (quebrar épico, sub-issues): apenas **MENCIONE** no fim — não crie nada por conta.

## Qualidade
- **TDD quando fizer sentido:** teste antes.
- Siga o `AGENTS.md` do repo-alvo — inclusive **doc-in-sync**: mudança de regra/domínio atualiza a
  doc (.md/ADR) no **mesmo commit**.
- Rode os checks do repo (lint, typecheck, testes, doc-sync) e **corrija até passarem ANTES** de concluir.

## Navegação (economia de token — regra OBRIGATÓRIA)
Pra DESCOBRIR onde algo está / quem usa um símbolo / o que quebra ao mudá-lo: use SEMPRE as tools do
**code-intel** (`find_symbol`, `find_references`, `document_symbols`, `blast_radius`) e ripgrep pra
texto literal. **NUNCA** leia um arquivo inteiro com `Read` só pra "procurar". Pra editar um símbolo,
prefira `rename_symbol`/`replace_symbol_body` a sed/regex.

Terminou de editar e os checks passam → siga para `open-pr`.
