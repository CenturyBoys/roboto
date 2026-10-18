# Auditoria 01 — Rodada 1 (auditor independente)

> Fase: **PESQUISA**. Documento de auditoria externa. O auditor não escreveu a pesquisa e não
> edita os docs de trilha — apenas emite findings e recomendações.
> Executado: 2026-10-18 · Épico: #13 · Escopo: README + 12 trilhas (`research/`).

## Sumário executivo

**Veredito geral:** a pesquisa é **sólida, coerente com os próprios princípios e bem-grounded** —
raro ver tanta disciplina de "determinismo primeiro" e amarração cross-trilha. A estrutura de 6
seções por doc é consistente e os cross-links em geral fecham. **Porém**, a pesquisa tem uma
fraqueza transversal séria: **muitos números de alto impacto são citados como fato sem qualidade
de fonte verificável**, e **várias fontes/produtos citados têm cheiro de "futuro/inventado"**
(datas de 2026 em arXiv, produtos muito novos tratados como decisão tomada). Além disso, há
**lacunas de decisão importantes** (custo/latência da própria escada de validação, concorrência
entre merge queue e per-PR CI do fleet, e ausência de qualquer tratamento de custo humano de gate).

A pesquisa está em nível de **rascunho forte pronto para refino**, não de spec fechada — o que é
coerente com o status declarado ("RASCUNHO PARA REVISÃO"). As perguntas em aberto de cada trilha
são boas, mas algumas **escondem decisões de arquitetura que deveriam estar no corpo**, não como
checkbox.

### Top 5 riscos/fraquezas

1. **[alta] Números-âncora frágeis e não auditáveis** (Trilhas D, F, I, J, K). Métricas decisivas
   ("FP cai de 32% para 8%", "3.400 vs 412.000 tokens", "RouteLLM >75% de economia a 95% de
   qualidade", "-92% de roubo com token de 300s", "MTTR -40–60%") são apresentadas como fato e
   usadas para fundamentar recomendações, mas vêm de blogs/vendor ou de papers não verificáveis.
   Risco: decisões de arquitetura ancoradas em números que podem não se sustentar.

2. **[alta] Dependência forte de um vendor novíssimo (Jev/TypeSafe) tratada como quase-decisão**
   (Trilha I, e propagada para A, D, H). O Jev aparece como o degrau 2 da escada de validação e como
   guardrail de tool call (`jev-guard`) em 4 trilhas, mas é um produto de set/2026 ("vendor novo",
   admitido no próprio doc) com acesso que depende de "autorização do CTO via OpenRouter". É um
   **single point of failure conceitual** espalhado pela arquitetura.

3. **[alta] A própria escada de validação não tem orçamento de custo/latência** (Trilha I/H). O
   princípio "right-sizing" é defendido, mas não há análise do **custo acumulado de rodar
   check determinístico + judge barato + às vezes frontier** por operação, nem do **custo de
   latência** de encadear 3 tiers. Multi-pass/voto (Trilha D) e multi-agente também multiplicam
   custo — o objetivo de "economia de token" pode ser violado pela própria arquitetura de validação.

4. **[média-alta] Conflito latente entre "Review ≠ implementador" + per-PR review e a economia de
   merge queue** (cross: A/D/J). A Trilha J aposta em merge queue (batch de N PRs = 1 CI) e two-step
   CI, mas D/B disparam review multi-agente + re-review a cada `synchronize`. Ninguém reconcilia o
   custo de LLM por PR (que NÃO batcheia) com a economia de CI por batch — o gargalo/custo migra do
   CI para o LLM e isso não é tratado.

5. **[média-alta] Gate humano é invocado em toda parte sem modelo de custo/escala humana** (cross:
   0/A/H/J). Priorização, decisão arquitetural, merge, conflito, mudança de credencial — todos "gate
   humano". Num fleet de alto volume (premissa da Trilha J), isso recria o gargalo humano que o
   projeto quer superar. "Approval fatigue" é citado (H) mas não há política concreta de como manter
   o volume de gates humano sustentável.

---

## Trilha 0 — Mapa de papéis → agentes

**[Trilha 0] claim-sem-evidência · média · 0.8**
Evidência: "MTTR caindo 40–60%" e "2026 foi o ponto de virada — Azure SRE Agent e AWS DevOps Agent
em GA (mar/2026)" (seção Estado da arte).
Problema: número de MTTR e datas de GA específicas são afirmados como fato a partir de blogs
(Sherlocks, beri.net), não de fonte primária (release notes do fornecedor / Gartner original).
Recomendação: rebaixar para "relatado por [fonte]" ou substituir por fonte primária; o número não
deve sustentar nenhuma decisão de escopo até ser verificado.

**[Trilha 0] lacuna · média · 0.75**
Evidência: lista canônica de 9 agentes + "Dissolvidos em processo". Não há um agente/mecanismo de
**orquestração** na lista canônica, embora Trilhas B, C, J, F o assumam ("orquestrador mantém
contexto global", "WIP limit no orquestrador").
Problema: o orquestrador é peça central em 4 trilhas mas não aparece no mapa de papéis — é agente?
processo? híbrido? Fica indefinido de onde nasce.
Recomendação: adicionar explicitamente "Orquestração/Dispatcher" ao mapa com decisão (processo
determinístico vs. agente) e gatilho — é a peça que todas as outras trilhas penduram.

**[Trilha 0] ângulo-faltando · baixa · 0.65**
Evidência: "Começamos com o fleet completo (9 agentes) ou um MVP?" (perguntas em aberto).
Problema: a decisão de MVP vs. fleet completo é a decisão mais consequente do doc e está relegada a
checkbox, sem análise de dependências entre agentes que justifique uma ordem.
Recomendação: mover para o corpo um grafo mínimo de dependência entre agentes (quem precisa de quem)
para fundamentar o MVP sugerido, em vez de apenas sugeri-lo.

## Trilha A — Contratos de trabalho

**[Trilha A] claim-sem-evidência · alta · 0.7**
Evidência: "GitHub Spec Kit implementa SDD num pipeline de 7 fases: Constitution → Specify → Clarify
→ Plan → Analyze → Tasks → Implement" e fontes como `arxiv.org/html/2607.00711v2` (ClarifyCodeBench),
`2605.25284`, `2603.26233`, `2606.03135`, `2607.25152`.
Problema: múltiplos IDs de arXiv têm prefixo de ano/mês **no futuro** (26xx = 2026+) e títulos muito
convenientes ("ClarifyCodeBench", "Ambig-SWE", "Ask or Assume?"). Para um auditor cético, isso é
bandeira vermelha de fonte não verificável/alucinada. A arquitetura do gate de prontidão se apoia
nelas.
Recomendação: verificar cada arXiv ID contra o site real antes de usar como grounding; marcar as
que não resolverem como "não verificado" e não deixá-las sustentar a decisão de "gate forçado".

**[Trilha A] contradição · média · 0.7**
Evidência: DoD exige "Review aprovado — por agente diferente do que implementou"; máquina de estados
tem `in_review → verifying` feito pelo "Agente Review (≠ implementador)".
Problema: a regra "quem gera não valida" é aplicada ao código, mas a própria issue/spec é gerada
pelo Agente Refinamento e validada pelo "validador em camadas" que inclui o mesmo loop de
refinamento (Refinamento propõe → revalida). Não fica claro que o validador da DoR seja independente
do Refinamento — pode haver auto-validação na fase de spec, exatamente o que o princípio proíbe.
Recomendação: explicitar que o validador da DoR (checklist + Jev) é independente do agente de
Refinamento, ou assumir que a independência aqui é só o checklist determinístico (e dizer isso).

**[Trilha A] under-spec · média · 0.6**
Evidência: máquina de estados inclui `blocked`, `rejected/reopened`, mas "Loop breaker: contador
máximo de iterações" (bounded loop) está só na Trilha B.
Problema: a máquina de estados não modela o limite de iterações do loop de definição nem o que
acontece quando o loop breaker estoura (vira `blocked`? escala a humano?). Estado terminal de falha
indefinido.
Recomendação: adicionar transição explícita "loop de definição excedeu N → blocked/escala humano" na
própria máquina de estados.

## Trilha B — Orquestração e gatilhos

**[Trilha B] under-spec · média · 0.7**
Evidência: "Começar com GitHub Actions disparando um self-hosted runner no nosso container (Trilha
K)". Trilha K recomenda "container não-root, efêmero, 1 por task + git worktree".
Problema: self-hosted runner + container efêmero por task tem tensão real não resolvida: o runner do
Actions normalmente é persistente/registrado; "efêmero por task" exige ephemeral runners
(just-in-time), o que muda o wiring. O doc não trata como o runner se registra/desregistra por task.
Recomendação: especificar o modelo de runner (JIT/ephemeral runners do GitHub) e como ele casa com o
container 1-por-task da Trilha K, ou reconhecer que são dois níveis (runner persistente que spawna
containers efêmeros).

**[Trilha B] risco · média · 0.65**
Evidência: "Idempotency key = X-GitHub-Delivery (event id); grava antes de processar; se já visto,
descarta."
Problema: `X-GitHub-Delivery` é por entrega de webhook, mas a recomendação é começar com GitHub
Actions (não webhook server). Em Actions, não há `X-GitHub-Delivery` no mesmo sentido; a chave de
idempotência precisa ser outra (run_id/sha/evento). O mecanismo de idempotência está escrito para a
opção 2 (webhook), mas a recomendação é a opção 1/3.
Recomendação: separar a estratégia de idempotência por arquitetura escolhida; para Actions, definir a
chave real (ex.: dedupe por `head_sha` + tipo de evento + número da issue).

**[Trilha B] lacuna · baixa · 0.6**
Evidência: "Filtrar por actor: ignorar eventos originados pelo nosso machine-user/bot."
Problema: filtrar por actor quebra o próprio loop fix→review que é desejado (o bot faz commit → CI →
bot corrige). Se todos os eventos do bot são ignorados, o loop automático também morre. A distinção
entre "loop desejado (bounded)" e "loop infinito" não está operacionalizada além do contador.
Recomendação: definir quais eventos do bot ainda disparam agentes (loop desejado) vs. quais são
filtrados, não um filtro-por-actor cego.

## Trilha C — Design de skills

**[Trilha C] claim-sem-evidência · média · 0.6**
Evidência: "≤ 5000 tokens / ≤ 500 linhas" para Tier 2; "~50–100 tokens/skill" para Tier 1.
Problema: números apresentados como limites canônicos da plataforma sem citar onde na fonte (best
practices) eles aparecem; podem ser diretriz, não limite técnico. Se vira regra de projeto, precisa
de origem.
Recomendação: citar explicitamente a origem do limite (doc da plataforma) ou marcar como heurística
do projeto, não como spec externa.

**[Trilha C] inconsistência-cross-trilha · média · 0.7**
Evidência: catálogo lista skills para "os 9 agentes", mas só enumera skills para 7 papéis
(Refinamento, Planejamento/Arquitetura, Implementação, Review, Testes, Segurança, Docs). Faltam
SRE/Incidente e o agente de Arquitetura aparece fundido com Planejamento.
Problema: diz "9 agentes (Trilha 0)" mas cobre 7; SRE/Incidente e a separação Arquitetura não têm
skills — inconsistência direta com a lista canônica da Trilha 0.
Recomendação: alinhar a contagem (ou cobrir os 9, ou dizer explicitamente "MVP cobre 7, SRE fica
fora do escopo inicial").

**[Trilha C] under-spec · baixa · 0.55**
Evidência: "Onde as skills vivem (...)?" fica em perguntas em aberto.
Problema: a decisão de localização (repo/plugin/compartilhadas) afeta diretamente a supply chain de
skills (CompoSkill, citado no mesmo doc) e o versionamento — é decisão de segurança, não detalhe.
Recomendação: elevar a decisão de hosting de skills ao corpo, amarrada ao risco de composição.

## Trilha D — Review de PR

**[Trilha D] claim-sem-evidência · alta · 0.8**
Evidência: "captura ~89% das vulnerabilidades vs 43% de passagem única, e FP cai de 32% para 8%";
"resolução sobe de ~52% para >70%"; "Greptile ~82% de captura, ~11 FP por run"; "CodeRabbit #1 em
benchmark da Martian (~300k PRs)".
Problema: todos os números-âncora que justificam o desenho recomendado (multi-pass + multi-agente +
verificação) vêm de blogs de vendor (Greptile sobre si mesmo, designkey, CodeAnt) ou de um arXiv de
2026. Viés de fonte óbvio (Greptile avaliando ferramentas de review é parte interessada).
Recomendação: tratar esses números como ilustrativos, não como fundamentação. A recomendação de
"viés para precisão" é boa por argumento; não precisa pendurar em números frágeis de vendor.

**[Trilha D] risco · média · 0.7**
Evidência: desenho recomendado = review multi-agente por dimensão + verificação adversarial +
voto/consenso + Jev de scoring.
Problema: isso é caro em token/latência por PR e colide frontalmente com o objetivo de primeira
classe (economia de token) e com o volume da Trilha J. Multi-agente × multi-pass × re-leitura da
fonte pode custar mais que o próprio patch. Não há orçamento nem gatilho de "quando NÃO fazer o
pipeline pesado".
Recomendação: definir tiering do próprio review (PR pequeno/baixo risco → 1 passagem barata; PR
grande/sensível → pipeline completo), coerente com o right-sizing da Trilha I.

## Trilha E — AGENTS.md e padrões

**[Trilha E] viola-princípio · baixa · 0.55**
Evidência: "Naming vs comentários — hipótese do dono VALIDADA" com "Hierarquia de clareza (pesquisa
2026)".
Problema: o doc declara a hipótese do dono "VALIDADA" — postura confirmatória, não cética. Validar a
hipótese de quem pediu a pesquisa contraria "quem gera não valida" no espírito. A evidência (um
HackerNoon + um arXiv) é fraca para "validado".
Recomendação: rebaixar de "VALIDADA" para "suportada pela literatura disponível, com fontes fracas";
registrar o contra-argumento (há domínios onde comentário-o-quê ajuda, ex. código denso/algorítmico).

**[Trilha E] lacuna · média · 0.6**
Evidência: "< 500 linhas, sweet spot 200–500 — o arquivo entra no contexto a cada ação". Monorepo:
"o mais próximo vence".
Problema: afirma que o AGENTS.md "entra no contexto a cada ação" mas não reconcilia isso com a
progressive disclosure da Trilha C (Tier 1 catálogo barato). Se o AGENTS.md inteiro entra sempre,
200–500 linhas × cada ação é custo de token fixo não contabilizado no orçamento da Trilha F.
Recomendação: cross-link com Trilha F/C e decidir se o AGENTS.md também sofre carregamento
progressivo ou é custo fixo aceito (e quantificar).

## Trilha F — Token e ferramentas

**[Trilha F] claim-sem-evidência · alta · 0.8**
Evidência: "~3.400 tokens via grafo vs ~412.000 via grep+read (10× menos)"; "~40% menos token";
"MCP-native 84–88% menos"; "ripgrep 2,6× (5–20×, até 100×)"; "compaction 208K → 86K (-58,6%)";
"rustygrep comprime 60–95%".
Problema: a trilha que fundamenta a economia de token do projeto inteiro é a mais densa em números
precisos de blogs (particula.tech, HackerNoon, Medium) sem metodologia. "3.400 vs 412.000" é
suspeito de cherry-pick (caso ideal de busca estrutural).
Recomendação: manter o argumento qualitativo (busca semântica/estrutural >> grep+read para
símbolos — isso é robusto), mas marcar os múltiplos como "ilustrativos de uma medição específica";
e, como a própria trilha pede, **medir no nosso caso** antes de citar número.

**[Trilha F] over-spec · baixa · 0.5**
Evidência: "em abr/2026 passou a ugrep + bfs em builds nativos" (nota sobre o Grep do Claude Code).
Problema: detalhe de implementação volátil e verificável-no-futuro, apresentado com data específica;
se errado, corrói confiança no resto. Não afeta nenhuma decisão.
Recomendação: remover a data/detalhe específico ou marcar como "sujeito a versão"; é ruído.

## Trilha G — Memória e second brain

**[Trilha G] claim-sem-evidência · média · 0.7**
Evidência: tabela com "Mem0 LongMemEval 49,0%", "Zep/Graphiti 63,8%", "~48K stars"; menção a "Manus,
OpenClaw", "padrão HERMES", "VibeMemBench (arXiv 2609.23570)".
Problema: scores de benchmark específicos e nomes de produtos/padrões (OpenClaw, HERMES, memweave)
pouco conhecidos, citados como fato; arXiv 2609 é futuro. Decisão de "não usar vector DB como
primário" é boa por princípio, mas os números de acurácia que rankeiam Zep acima de Mem0 precisam de
fonte primária.
Recomendação: a recomendação (markdown-first) se sustenta pelo princípio de determinismo sem os
números; marcar os scores como não verificados e não rankear vendors com base neles.

**[Trilha G] lacuna · média · 0.6**
Evidência: "Formato canônico dos .md de memória do fleet (...) e onde vivem" em aberto.
Problema: sem formato canônico definido, a "memória determinística greppável" é aspiracional. É a
peça que dá continuidade sem sessão gigante (objetivo central) e está indefinida.
Recomendação: propor um esqueleto mínimo de `.md` de memória (decisões/handoff/fatos) já na pesquisa,
mesmo que provisório — é fundação, não detalhe.

## Trilha H — Qualidade, segurança, recuperação

**[Trilha H] claim-sem-evidência · média · 0.65**
Evidência: "Checks determinísticos cobrem 60–70% da superfície de eval"; "LLM-as-judge calibrado
para 85–90% de concordância"; "golden ~50 casos / 150–200".
Problema: números apresentados como regras de engenharia sem fonte primária (blogs Agentic Academy,
Prefactor). São plausíveis mas viram alvos de projeto sem base verificável.
Recomendação: apresentar como heurísticas iniciais a calibrar com dados próprios, não como targets
fixos.

**[Trilha H] lacuna · alta · 0.75**
Evidência: gates humanos para "merge, deploy, mudança de credencial, decisão arquitetural" +
"approval fatigue" citado como desafio.
Problema: reconhece o problema de approval fatigue mas não oferece **nenhuma política concreta** de
como escalar gates humanos num fleet de alto volume (Trilha J). Num sistema que roda muitos PRs, "gate
humano em merge/conflito/arquitetura" recria o gargalo humano que o projeto quer dissolver.
Recomendação: desenvolver uma política de orçamento de atenção humana (batching de aprovações,
amostragem baseada em risco/confiança, auto-approve abaixo de threshold) — é decisão de arquitetura,
não pergunta em aberto.

**[Trilha H] contradição · baixa · 0.55**
Evidência: "rollback tem superfície de ataque própria (ACRFence, Safe to Resume?)" e ao mesmo tempo
"checkpoints duráveis → time-travel rewind" é recomendado.
Problema: o doc recomenda rollback/checkpoint e no mesmo parágrafo diz que rollback tem superfície de
ataque e "não é bala de prata", sem resolver quando usar vs. quando `git revert` simples basta.
Recomendação: decidir o mecanismo default (git revert + reabrir issue) e reservar checkpoint
sofisticado como exceção — alinhado com a filosofia determinista/git-first da Trilha G.

## Trilha I — Roteamento de modelos

**[Trilha I] risco · alta · 0.8**
Evidência: Jev/System One como degrau 2 da escada e `jev-guard` como guardrail; "Acesso LIBERADO via
OpenRouter, com autorização do CTO"; "vendor novo → manter fallback".
Problema: dependência de um produto de set/2026 em 4 trilhas (A/D/H/I) é risco concentrado. "Input
~$0.042/M, output grátis" e "0% erro de estrutura, não alucina" são claims de vendor aceitos
literalmente ("não alucina" é afirmação forte demais para qualquer LLM-based). O detalhe "autorizado
pelo CTO" é operacional-interno, não evidência técnica.
Recomendação: desacoplar a arquitetura do Jev — especificar o degrau 2 por **interface** (classificador
estruturado com confiança calibrada) e tratar Jev como UMA implementação possível, com fallback de
judge frontier barato como caminho primário testado, não secundário.

**[Trilha I] claim-sem-evidência · média · 0.7**
Evidência: "RouteLLM corta gasto >75% mantendo ~95% da qualidade (MT-Bench -85%, MMLU -45%, GSM8K
-35% a 95%)".
Problema: números de economia misturam métricas (os -85/-45/-35% parecem ser reduções de custo por
benchmark, não quedas de qualidade, mas a redação é ambígua e pode ser lida como perda de qualidade).
A citação é de blog, não do paper RouteLLM original.
Recomendação: desambiguar a frase (o que é redução de custo vs. retenção de qualidade) e citar o paper
primário; sem isso o número não deve guiar a decisão de adotar RouteLLM.

## Trilha J — Escala CI/build/review

**[Trilha J] claim-sem-evidência · média · 0.65**
Evidência: "merge queue: batch de N PRs usa 1 run de CI → custo por PR cai ~N-vezes"; "test impact
analysis economia típica 50–70%".
Problema: "custo cai ~N-vezes" é otimista — merge queue com falha força re-split e re-run, e flaky (o
próprio doc admite) corrói o ganho. Números de economia de blogs (Mergify/SitePoint).
Recomendação: qualificar o ganho do merge queue com o custo de re-run por falha/flaky; apresentar
50–70% como faixa observada por terceiros, a validar.

**[Trilha J] inconsistência-cross-trilha · média-alta · 0.75**
Evidência: Trilha J otimiza **CI** via batching (1 run para N PRs), mas Trilha D/B rodam **review de
LLM por PR e re-review a cada synchronize**.
Problema: a economia de escala é modelada só para o CI determinístico; o custo de LLM (review
multi-agente) **não batcheia** e não é contabilizado na política de escala. Com volume, o gargalo e o
custo migram do CI para o LLM — exatamente onde o projeto é mais caro e menos determinístico.
Recomendação: estender a política de escala da Trilha J para incluir orçamento/tiering do review de
LLM (cross com D e I), não só do CI.

## Trilha K — Runtime containerizado

**[Trilha K] claim-sem-evidência · média · 0.7**
Evidência: "Okta: -92% de roubo de credencial com token de 300s vs. sessão de 24h"; "cache do
code-intel ~23×".
Problema: o "-92%" é número de marketing de vendor (Okta) usado para justificar injeção runtime; o
"~23×" de cache não tem origem. Ambos sustentam recomendações concretas.
Recomendação: o argumento de credencial curta é sólido por princípio (least privilege / blast radius)
sem precisar do -92%; marcar os números como ilustrativos de vendor.

**[Trilha K] contradição · média · 0.65**
Evidência: "Container descartável por task (segurança) vs. warm para cache (code-intel ~23×).
Resolver por tipo: efêmero para execução; camada/volume de cache reaproveitável para índices."
Problema: volume de cache compartilhado reaproveitável entre tasks **fura o isolamento efêmero** que é
o argumento de segurança central do doc (um task pode envenenar o cache de outro — e o próprio doc
tem Trilha H com prompt injection/código não-confiável). A "resolução" não trata a superfície de
ataque do cache compartilhado.
Recomendação: especificar o cache como read-only/assinado ou por-projeto-confiável, e proibir cache
compartilhado entre tasks de código não-confiável (coerente com gVisor/Firecracker para untrusted).

**[Trilha K] lacuna · baixa · 0.55**
Evidência: perguntas em aberto incluem "gVisor/Firecracker desde o MVP?".
Problema: o doc diz que `roboto` é público (Trilhas I/H/B tratam PR não-confiável como risco), mas
aqui sugere "container padrão basta no começo (repo nosso, confiável)" — tensão com o fato de que PR
de terceiros em repo público é justamente o vetor não-confiável citado nas outras trilhas.
Recomendação: reconciliar: se o repo é público e aceita PR externo, o isolamento forte não é
opcional-MVP para o caminho de PR externo; separar "código nosso" de "PR de terceiro" na decisão.

---

## Seção cross-trilha (contradições e incoerências)

**[Cross 0↔C] contagem de agentes inconsistente · média · 0.75**
Trilha 0 define 9 agentes; Trilha C diz "os 9 agentes" mas cataloga skills para 7 e funde
Arquitetura em Planejamento. SRE/Incidente e Documentação aparecem/somem de forma inconsistente entre
os dois docs. Fixar a lista canônica única e referenciá-la.

**[Cross A↔B] idempotência e estados descasados · média · 0.7**
Trilha A define a máquina de estados mas o loop breaker (bounded loop), a idempotency key e o
filtro-por-actor vivem só em B — e a chave de idempotência (`X-GitHub-Delivery`) é da arquitetura
webhook, não da recomendação (Actions). Os estados de falha (loop estourado) não têm destino na
máquina de A. Unificar.

**[Cross D↔J↔I] custo de LLM não entra na política de escala · alta · 0.8**
J otimiza CI; D desenha review caro de LLM por PR; I define a escada mas não orça o custo acumulado.
Nenhuma trilha fecha o loop "quanto custa, em token/$, rodar o fleet por PR sob volume". É a lacuna
econômica central — o objetivo de primeira classe (economia de token) não tem um modelo de custo
agregado em lugar nenhum.

**[Cross H↔J↔0] gate humano sem modelo de escala · alta · 0.75**
Gate humano é invocado em 0 (priorização), H (merge/deploy/credencial/arquitetura), J (conflito,
prioridade de build). Com o volume premissado em J, a soma de gates humanos vira o novo gargalo.
"Approval fatigue" é nomeado (H) mas não resolvido. Precisa de uma política única de atenção humana.

**[Cross I↔todas] Jev como dependência transversal não isolada · alta · 0.8**
Jev/`jev-guard` aparece como peça de A (classificador de prontidão), D (scoring), H (policy
deny/ask/allow) e I (degrau 2). Um vendor novo tratado como infraestrutura em 4 trilhas. Deveria ser
abstraído por interface, com o Jev como implementação plugável — hoje a arquitetura casa demais com
um produto específico e recém-nascido.

**[Cross geral] qualidade de fonte heterogênea e datada no futuro · alta · 0.7**
Vários arXiv IDs com prefixo 26xx (2026+) e produtos/padrões muito novos (Jev, OpenClaw, HERMES,
memweave, CompoSkill, ACRFence, Loopjacking) são citados como grounding estabelecido. Para um
auditor cético, isso exige verificação-fonte-a-fonte antes de qualquer número sustentar decisão.
Recomendação transversal: criar uma política "número de terceiro = ilustrativo até medirmos; fonte
não verificada = marcada como tal".

---

## Lista priorizada de melhorias (o que endereçar primeiro)

1. **Modelo de custo agregado do fleet por PR/issue sob volume** (cross D/I/J/F). Sem isso, "economia
   de token" é slogan, não engenharia. É a lacuna #1.
2. **Abstrair o degrau 2 da escada por interface e desacoplar do Jev** (I, propaga A/D/H). Remove o
   single-point-of-failure conceitual; mantém Jev como implementação plugável com fallback primário.
3. **Política de atenção humana / orçamento de gates** (H, cross 0/J). Batching, amostragem por risco,
   auto-approve sob threshold de confiança — resolver o gargalo humano explicitamente.
4. **Auditoria de fontes e números**: verificar cada arXiv ID e cada número-âncora; rebaixar vendor
   numbers a "ilustrativo"; marcar não verificados. Barato e aumenta muito a credibilidade.
5. **Fixar a lista canônica única de agentes** e referenciá-la de C, B, J (inclui o Orquestrador, hoje
   ausente do mapa 0).
6. **Reconciliar runner (B) × container efêmero (K)** e **cache warm × isolamento** (K/H) — duas
   tensões de arquitetura concretas.
7. **Tiering do próprio review** (D) alinhado ao right-sizing (I): PR pequeno/baixo risco não paga o
   pipeline multi-agente completo.
8. **Formato canônico de memória `.md`** (G) e **estados de falha do loop de definição** (A) — fundações
   hoje relegadas a perguntas em aberto.

---

> Nota de disciplina: nenhum finding marca issue como `done`; nenhuma mudança de fase é proposta.
> As recomendações são para os autores decidirem — o auditor não edita os docs de trilha.
