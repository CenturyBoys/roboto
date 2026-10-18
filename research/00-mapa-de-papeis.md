# Trilha 0 — Mapa de papéis → agentes

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Para cada responsabilidade de uma org de tecnologia moderna, decidir:
**(a) agente dedicado**, **(b) resolvido por processo/CI/estrutura (determinístico)**, ou
**(c) híbrido** — e por quê. O resultado é a **lista canônica de agentes** do fleet, que alimenta
a orquestração (Trilha B) e as skills (Trilha C).

## Método / lentes de decisão

1. **Lente DBA-ORM**: responsabilidade migra conforme a ferramenta absorve a complexidade. O ORM
   absorveu "modelar tabelas" (schema virou código + migrations), então a modelagem deixou de
   precisar de papel dedicado; o que restou do DBA é operacional e migrou para DevOps/SRE.
2. **Determinismo primeiro (princípio-mãe)**: se a responsabilidade vira script/CI/processo, ela
   NÃO deve virar agente de LLM. Agente só onde há julgamento ou geração irredutível a código.
3. **Taxonomia de gatilho**: cada agente é **reativo** (evento: PR/issue/CI), **ambiente**
   (feed/schedule, proativo) ou **sob demanda** (humano invoca).

## Estado da arte (2026) — grounding

- SDLC agêntico já cobre todo o ciclo (requisitos → arquitetura → código → review → testes →
  docs → produção); o humano sobe para arquitetura, validação, segurança e governança, e
  orquestra **fleets** de agentes sob controle humano. ([Forrester], [PwC], [CIO])
- **SRE/DevOps**: 2026 foi o ponto de virada — Azure SRE Agent e AWS DevOps Agent em GA (mar/2026),
  Gartner publicou Market Guide da categoria (jan/2026); MTTR caindo 40–60%. Diagnóstico de
  incidente virou caso real de agente. ([Gartner via Sherlocks], [beri.net])
- **Segurança**: triagem agêntica de CVE é padrão estabelecido — **diversificar feeds** (NVD,
  GHSA, OSV, CISA Vulnrichment), priorizar por **exploitabilidade** (não só CVSS), e manter um
  **inventário programaticamente consultável** ("quais dos nossos sistemas são afetados por este
  CVE?"). NVD tem lacunas de cobertura em 2026 → multi-feed é obrigatório. ([CSA], [Sonatype], [safeguard.sh])

## Análise papel-a-papel

| Papel | Decisão | Por quê (lente) | Gatilho |
|-------|---------|-----------------|---------|
| **Produto / PO / PM** | Híbrido | Agente transforma pedido bruto → issue estruturada com DoR (geração). **Priorização = julgamento de negócio = humano** (gate). | Reativo + sob demanda |
| **Arquitetura** | Híbrido | Agente propõe design/ADR; decisão arquitetural relevante é **gate humano**. Tier de modelo alto (Trilha I). | Reativo (épico/issue "precisa design") + sob demanda |
| **Planejamento** (épico→issues, estados) | Agente + muito processo | Decompor é geração; **a máquina de estados da issue é determinística** (Trilha A). | Reativo (issue refinada) |
| **Desenvolvimento / Implementação** | **Agente dedicado** (núcleo) | Geração/edição de código irredutível a script; usa code-intel p/ edição verificada. | Reativo (plano aprovado → PR) |
| **QA / Teste** | Híbrido, inclinado a processo | **O gate de "done" é determinístico**: CI verde + cobertura mínima. Agente só p/ *gerar/expandir* suites; rodar teste é CI, não LLM. | Reativo (PR) |
| **SRE / DevOps** | Híbrido (split claro) | **Deploy/infra = processo determinístico** (pipeline + IaC, sem LLM). **Incidente/observabilidade = agente** (diagnóstico/correlação não viram script). Responde sua pergunta: deploy = processo; incidente = agente. | Deploy: reativo determinístico · Incidente: ambiente/alerta |
| **DBA** | **Dissolvido, com ressalva** | Schema = código + migrations (dev-agent + review); operação = DevOps/SRE; validação de migration = CI em staging. **Ressalva (ver nota abaixo)**: ORM nem sempre é o alvo. | — |
| **Segurança** | Híbrido | **CI de segurança = determinístico** (SAST/SCA/secret-scan/dependabot como gate). **Agente ambiente** para advisory/triagem/novas normas via feeds + inventário queryável. Caso canônico de agente "ambiente". | Ambiente (feed/schedule) + reativo (PR→scan) |
| **Documentação** | Híbrido | Gerar o gerável = processo (docs de API a partir de tipos/OpenAPI). Agente p/ prosa/guia e **detecção de drift**. | Reativo (PR muda API) + ambiente (drift) |
| **Code Review** | **Agente dedicado** | Checks determinísticos (lint/test/build) são gate barato ANTES; agente revisa o resto (lógica/design). Scoring/guardrail pode usar judge barato (Jev, Trilha I). Detalhe na Trilha D. | Reativo (PR aberto) |
| **Release Manager** | **Não (processo)** | Merge queue + semantic versioning + changelog gerado = automação determinística (Trilha J). Quase nenhum LLM. | Reativo determinístico |

### Nota — ORM nem sempre é o alvo (refina o caso-guia do DBA)

A lente DBA-ORM não significa "ORM resolve tudo". **Busca em grafo no Postgres, SQL de
performance e modelagem de dados complexa não cabem em ORM** — exigem SQL cru, query builders
ou stores especializados. Ou seja, a *expertise de dados* não desaparece; ela **migra para
regras no `AGENTS.md` + critério de review + validação determinística** (análise de query plan,
testes de query, benchmarks), e NÃO para um agente DBA dedicado. Conclusão mantida (sem agente
DBA), mas a competência de dados precisa estar codificada nas regras e no review, não assumida
como "o ORM cuida".

## Saída — lista canônica de agentes do fleet

Agentes dedicados (LLM onde há julgamento/geração):
1. **Refinamento** (produto) — reativo/sob demanda · gate humano de priorização.
2. **Arquitetura/Design** — reativo (épico grande)/sob demanda · tier alto · gate humano.
3. **Planejamento** (épico→issues, estados) — reativo.
4. **Implementação** — reativo · núcleo · modelo tiered.
5. **Testes** — reativo · complementa o CI determinístico.
6. **Review de PR** — reativo · ver Trilha D.
7. **Segurança** — **ambiente** (feeds) + complementa CI de segurança.
8. **SRE/Incidente** — ambiente/alerta (deploy em si é processo).
9. **Documentação** — reativo + ambiente (drift).

Dissolvidos em processo/determinístico (**sem** agente dedicado): **DBA** (schema→código),
**deploy/release mechanics**, **gate de QA** (CI como juiz), **grande parte de DevOps** (IaC/pipeline).

## Perguntas em aberto (para o dono decidir)

- [ ] Começamos com o fleet completo (9 agentes) ou um MVP? Sugestão de MVP: Planejamento +
      Implementação + Review + Segurança(ambiente) — cobre o loop issue→PR→review com segurança proativa.
- [ ] Agente de Arquitetura e Refinamento podem ser **um só** ("agente de upstream/produto")? Ou separados?
- [ ] SRE/Incidente entra no escopo inicial ou só depois de termos software em produção?
- [ ] Onde ficam os gates humanos exatos (priorização, merge, decisão arquitetural)? → detalhar na Trilha H.
- [ ] Competência de dados (SQL complexo/grafo/performance) vira regra no AGENTS.md + critério de
      review, ou há casos que justificam um agente/processo especializado de dados? (refina a nota acima)

---

### Fontes
- [Forrester — Agentic Software Development Takes The Lead](https://www.forrester.com/blogs/agentic-software-development-takes-the-lead-from-code-assistants-to-orchestrated-sdlc-agents/)
- [PwC — Agentic SDLC in practice (2026)](https://www.pwc.com/m1/en/publications/2026/docs/future-of-solutions-dev-and-delivery-in-the-rise-of-gen-ai.pdf)
- [CIO — How agentic AI will reshape engineering workflows in 2026](https://www.cio.com/article/4134741/how-agentic-ai-will-reshape-engineering-workflows-in-2026.html)
- [Sherlocks — Top AI SRE Tools in 2026 (cita Gartner Market Guide)](https://www.sherlocks.ai/blog/top-ai-sre-tools-in-2026)
- [beri.net — AI SRE agents, autonomous operations 2026](https://www.beri.net/article/ai-sre-agents-35000-incidents-autonomous-operations-on-call-burnout-enterprise-2026)
- [Cloud Security Alliance — NVD Enrichment Triage: Guidance for AI Security Programs](https://labs.cloudsecurityalliance.org/research/csa-research-note-nist-nvd-cvss-gap-ai-vulnmgmt-20260422-csa/)
- [Sonatype — The AI Vulnerability Storm](https://www.sonatype.com/resources/research/ai-vulnerability-storm)
- [safeguard.sh — GitHub Repository Advisories Missing From the Database (2026)](https://safeguard.sh/resources/blog/github-repository-advisories-missing-from-advisory-database-2026-data)
