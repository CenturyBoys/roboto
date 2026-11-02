# fleet/skills — skills do fleet (Trilha C)

Procedimentos que o **motor** segue trabalhando em **repos-alvo**, empacotados como skills
(progressive disclosure). O container symlinka esta pasta em `~/.claude/skills` (ver
`poc/entrypoint.sh`), então o motor as acha em qualquer repo-alvo.

| Skill | O quê |
|---|---|
| `refine-issue` | montar uma issue acionável lendo o repo |
| `validate-readiness` | DoR em 3 camadas (estrutural → semântico → escalada) |
| `implement-issue` | codar a issue (escopo mínimo, testes, checks verdes) |
| `open-pr` | abrir o PR (GitFlow + Conventional Commits + Closes) |
| `review-pr` | review estruturado (reviewer≠autor, findings) |

**Separado** do `.claude/skills/` do roboto (skills de dev: `docs`, `github`) — aquelas são pra quem
trabalha no próprio roboto; estas, pro motor em repos-alvo. Política de versão/teste em
`docs/trilha-c-skills.md`.
