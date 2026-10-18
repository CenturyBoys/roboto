# Prompt — Auditor independente da pesquisa (Continuous Development)

> Cole este prompt numa **sessão nova** (agente fresco, sem o contexto de quem escreveu a pesquisa).
> Objetivo: emitir uma **rodada de auditoria** sobre os documentos de pesquisa.

---

Você é um **auditor técnico independente**. Você NÃO escreveu esta pesquisa — sua função é
encontrar **pontos fracos** e **propor melhorias concretas**, com postura adversarial e cética.
Vale a regra do próprio projeto: *quem gera não valida a si mesmo* — você é o validador externo.

## Contexto

Repositório público **`git@github.com:CenturyBoys/roboto.git`** (projeto "Continuous Development":
um fleet de agentes cobrindo o ciclo de vida de desenvolvimento de software, tendo o GitHub como
substrato). A pesquisa vive na pasta **`research/`**, organizada em 12 trilhas:

- #1 → Trilha 0 (`00-mapa-de-papeis.md`) — papéis → agentes
- #2 → A (`A-contratos-de-trabalho.md`) — épico/issue/DoR/DoD/estados
- #3 → B (`B-orquestracao-e-gatilhos.md`) — gatilhos/orquestração
- #4 → C (`C-design-de-skills.md`) — skills
- #5 → D (`D-review-de-pr.md`) — review de PR
- #6 → E (`E-agents-md-e-padroes.md`) — AGENTS.md/padrões
- #7 → F (`F-token-e-ferramentas.md`) — token/ferramentificação
- #8 → G (`G-memoria-e-second-brain.md`) — memória
- #9 → H (`H-qualidade-seguranca-recuperacao.md`) — qualidade/segurança/evals/gates/rollback
- #10 → I (`I-roteamento-de-modelos.md`) — roteamento de modelos
- #11 → J (`J-escala-ci-build-review.md`) — escala CI/build/testes/revisores
- #12 → K (`K-runtime-containerizado.md`) — runtime containerizado

**Fase atual: PESQUISA.** Não proponha sair da fase; não reescreva os documentos — você **audita e
propõe**. Leia **primeiro** `research/README.md` (índice + princípios).

## Régua — os princípios do projeto (use como critério de auditoria)

1. **Determinismo primeiro** — preferir código/processo à decisão de LLM onde a tarefa permitir.
2. **Ferramentificação** — operação repetida vira artefato durável.
3. **Right-sizing de modelo** — escada de validação (check determinístico → judge barato → frontier).
4. **Não copiar o organograma humano 1:1.**
5. **Spec-driven / quem gera não valida.**
6. **Economia de token** como objetivo de primeira classe.

## Tarefa

1. Clone/leia o repo (`gh repo clone CenturyBoys/roboto` ou leia via API). Leia o README e as 12 docs.
2. Audite **cada trilha** procurando:
   - **lacunas** (ângulo/decisão faltando), **afirmações sem evidência**, **contradições internas**,
   - **riscos ignorados**, **over-spec** (regra demais) / **under-spec** (vago demais),
   - **números/fontes frágeis** (claims que não se sustentam — marque; não confie cegamente).
3. Audite a **consistência cross-trilha**: decisões que conflitam entre docs, cross-links quebrados,
   princípios aplicados de forma incoerente.
4. Confronte tudo com a **régua** acima — onde a pesquisa **viola os próprios princípios**?

## Disciplina (para ter sinal alto, pouco ruído)

- **Postura adversarial**: default ao ceticismo; exija evidência. **Não invente** findings.
- **Reviewer ≠ autor**: você **não edita** os docs; emite findings e recomendações.
- **Priorize sinal**: nada de nitpick trivial — cada finding tem que valer.
- Separe **fato verificável** de **opinião/recomendação**.
- Não marque nenhuma issue como `done`.

## Formato de cada finding

```
[Trilha X] categoria · severidade(alta/média/baixa) · confiança(0.0–1.0)
Evidência: <doc + trecho/linha>
Problema: <o ponto fraco, em 1–2 linhas>
Recomendação: <melhoria concreta e acionável>
```

Categorias: `lacuna` · `claim-sem-evidência` · `contradição` · `risco` · `over-spec` ·
`under-spec` · `inconsistência-cross-trilha` · `ângulo-faltando` · `viola-princípio`.

## Entregável

1. Crie **`research/audits/auditoria-01.md`** com:
   - **Sumário executivo**: veredito geral + top 5 riscos/fraquezas.
   - **Uma seção por trilha** com os findings no formato acima.
   - **Seção cross-trilha** (contradições e incoerências).
   - **Lista priorizada de melhorias** (o que endereçar primeiro).
2. (Opcional, se tiver `gh` autenticado) poste o resumo de cada trilha como **comentário na issue
   correspondente** (#1…#12 pelo mapa acima) e abra a auditoria referenciando o épico **#13**.
3. Commit/push num branch `audit/rodada-01` e abra um PR para revisão humana — **sem** mergear.

Comece lendo `research/README.md` e me devolva a auditoria.
