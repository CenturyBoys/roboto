---
name: open-pr
description: Abre um PR do trabalho implementado seguindo GitFlow + Conventional Commits, com corpo que fecha a issue. Dispare ao abrir/subir um PR, ou quando pedirem "abre o PR".
version: 1
---

# open-pr — abrir o PR (GitFlow + convenções)

## Branch e commits
- Branch a partir da **base** do repo (GitFlow: `develop`; `hotfix/` a partir de `main`). Uma branch
  por tarefa; nunca trabalhe direto em `main`/`develop`.
- **Conventional Commits** (tipos que o hook `commit-msg` do repo aceita): `feat`/`fix`/`docs`/
  `refactor`/`chore`/`test`/`ci`/… Escopo entre parênteses. Rodapé `Refs #<n>`.
- **NUNCA** inclua `Co-Authored-By` nem rodapé de ferramenta em commit ou PR.
- Não use `--no-verify`. Se o hook barrou, conserte a mensagem ou o código (ex.: `#216` em comentário
  pode ser lido como cor hex por um lint de design — reescreva "issue 216").

## Corpo do PR
```
## O que muda / Por quê

Closes #<n>

## Como testar
## Evidência (print/log — obrigatório)
```

## Fecho
- CI verde + **revisão de outra pessoa/agente** (reviewer≠autor) antes do merge.
- `Closes #<n>` fecha a issue no merge. **Merge = gate humano** — o fleet nunca mergeia sozinho.
