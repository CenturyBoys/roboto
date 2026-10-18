# Trilha H — Qualidade, segurança, evals, gates e recuperação

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Como **medir, proteger e recuperar** o fleet — a camada que separa "demo legal" de "premium e
confiável". Cobre evals, segurança, gates humanos, rollback e observabilidade.

## Princípio unificador (determinismo primeiro, aplicado à segurança)

**O output do modelo é uma PROPOSTA, não um comando.** Cada ação proposta passa por uma **camada
determinística de política + validação de capacidade** antes de executar. Gates, evals e policy
checks são todos instâncias disso. É o mesmo fio das Trilhas A (gate de prontidão), D (verificação)
e I (escada de validação).

## 1. Evals — como saber se um agente está bom

- **Golden dataset vindo de falhas REAIS de produção** (não sintético). Tamanho: ~50 casos para
  um processo estreito; 150–200 para escopo amplo — acima disso o custo de manter sobe e o ganho cai.
- **Versionar o golden set junto do agente**; refrescar em schedule deliberado, não continuamente
  (senão não dá para distinguir regressão do agente de mudança do dataset).
- **LLM-as-judge calibrado para 85–90% de concordância** com referência humana. Regressão abaixo do
  baseline **bloqueia o merge** (CI gate).
- **Checks determinísticos cobrem 60–70% da superfície de eval**; LLM-judge só para dimensões
  subjetivas (determinismo primeiro). **Agent-as-a-Judge** avalia a *trajetória* inteira, não só o fim.
- Loop de medição: golden set de falhas → graders confiáveis → judge calibrado → CI gate que
  barra regressão. Ferramentas: DeepEval, Promptfoo.

## 2. Segurança do fleet

- **Prompt injection = risco #1 (OWASP) e NÃO resolvido em 2026** — crítico para agente que executa
  tool calls. Existe **OWASP Top 10 for Agentic Applications 2026**.
- **Least privilege por task**: allowlist explícita de tools **por tipo de task**, não o toolbox
  inteiro por sessão; permissões reduzidas ao fim da task.
- **Sandbox obrigatório + egress controlado**; filesystem containerizado por projeto com mounts
  explícitos (amarra com Trilha K).
- **Outputs como propostas** (princípio acima): policy check determinístico antes de agir.
- **Supply chain de skills**: CompoSkill (Trilha C) — skills individualmente "limpas" podem compor
  ataque; review olha composição, não só a skill isolada.
- **Repo público (`roboto`)**: conteúdo de PR/issue não confiável pode injetar → automação só para
  autor/label confiável (Trilha B).

## 3. Gates humanos

- Gate por **classificação da tool + raio de impacto da mudança**; aprovação explícita para ações
  **irreversíveis/alto impacto** (merge, deploy, mudança de credencial, decisão arquitetural).
- **Calibração é o desafio**: gates demais → *approval fatigue*; de menos → brecha de ataque.
  Usar a confiança calibrada (Jev, Trilha I) para decidir quando escalar ao humano.
- **Loopjacking**: ataques sequestram o próprio passo de aprovação humana → o gate precisa de
  contexto íntegro e assinado, não só um "aprovar?" cego.
- Conflito de merge = gate humano (Trilha J); priorização = gate humano (Trilha 0).

## 4. Rollback e recuperação

- **Checkpoints duráveis** → "time-travel rewind" para recuperar de falha; rastrear mutações de
  estado, rationale de decisão e eventos de rollback.
- **Cuidado**: rollback tem superfície de ataque própria (ACRFence — semantic rollback attacks;
  "Safe to Resume?" — rollback quebrando continuidade). Rollback é mecanismo de segurança, não bala de prata.
- Amarra com dead-letter + replay da orquestração (Trilha B) e com `git revert`/reabrir issue (Trilha A).

## 5. Observabilidade e custo (serve o objetivo de token)

- Capturar o ciclo completo: prompts, completions, tool calls (I/O/latência), reasoning, **token
  counts e custo**.
- **Custo por run, eficiência de token e latência por tipo de tool**; **alertas de anomalia para
  runs descontrolados** (agente que entra em loop é caro).
- Atribuição de custo por feature/modelo → permite verificar o right-sizing (Trilha I) e o ganho
  da ferramentificação (Trilha F). *Não dá para otimizar token sem medir token.*
- Por que é essencial: sistema não-determinístico + autônomo + metered → falha não se reproduz só
  do código, não se localiza sem trace, não se orça sem custo por request.

## Perguntas em aberto
- [ ] Primeiras dimensões de eval e fonte inicial do golden set (começa das falhas de quem?).
- [ ] Plataforma de observabilidade (self-host vs. SaaS) e orçamento de token por tipo de agente.
- [ ] Catálogo de ações que **exigem** gate humano (lista explícita de "irreversível/alto impacto").
- [ ] Mecanismo de checkpoint/rollback concreto (git + estado da issue? ferramenta dedicada?).

---

### Fontes
- [Evaluating AI Agents: Evals That Predict Production — Agentic Academy](https://agentic-academy.ai/posts/evaluating-ai-agents-evals/)
- [Golden Datasets for AI Agents — Prefactor](https://prefactor.tech/learn/golden-datasets-for-agents)
- [When AIs Judge AIs: Agent-as-a-Judge (arXiv)](https://arxiv.org/pdf/2508.02994)
- [OWASP Top 10 for Agentic Applications 2026 — Teleport](https://goteleport.com/blog/owasp-top-10-agentic-applications/)
- [Prompt Injection on Agentic Coding Assistants: Skills, Tools, Protocols (arXiv)](https://arxiv.org/pdf/2601.17548)
- [Loopjacking: Hijacking Human-in-the-Loop Approval (arXiv)](https://arxiv.org/pdf/2609.21081)
- [AI Agent Observability: Best Practices 2026 — Expanso](https://expanso.io/blog/ai-agent-observability-best-practices/)
- [ACRFence: Preventing Semantic Rollback Attacks in Agent Checkpoint-Restore (arXiv)](https://arxiv.org/pdf/2603.20625)
