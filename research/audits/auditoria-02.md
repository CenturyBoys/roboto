# Auditoria 02 — Rodada 2 (auditor independente)

> Fase: **PESQUISA**. Documento de auditoria externa. O auditor não escreveu a pesquisa e não
> edita os docs de trilha — apenas emite findings e recomendações. Vale a regra do projeto:
> quem gera não valida a si mesmo.
> Executado: 2026-10-18 · Épico: #13 · Rodada-01: PR #14 · Escopo desta rodada abaixo.

## Escopo desta rodada

1. **Verificar a remediação da rodada-01** (commits `c945dc8` altos + `09a2aa7` médios/baixos):
   para cada finding, status resolvido/parcial/aberto no doc atual.
2. **Auditar o material NOVO**: `L-modelo-de-custo.md` (orçamento, base = 1 Max ≈ R$550,
   decisão API-via-OpenRouter) e as adições à `I-roteamento-de-modelos.md` (Jev via OpenRouter/CTO,
   provedores chineses, "Mapa modelo → tarefa por benchmark").
3. **Regressões/contradições novas** e consistência cross-trilha (B/I/K/L sobre cobrança e runtime).

Régua: 6 princípios + "disciplina de fontes".

---

## (a) Sumário executivo

**Veredito geral:** a remediação da rodada-01 foi **séria e majoritariamente efetiva** — raro ver
uma segunda rodada endereçar tantos findings com cirurgia precisa (números de vendor marcados como
"indicativos", evidência acadêmica verificada em D, Jev isolado atrás de interface em I, política de
gate humano em H, Orquestrador adicionado à Trilha 0, formato de memória em G). A criação da
**Trilha L** fecha a lacuna econômica #1 da rodada-01 de forma direta, e a decisão de cobrança
(API pay-per-token via OpenRouter, com o valor Max como teto-alvo em $) é **coerente e bem
reconciliada** — justamente o ponto que a rodada-01 deixou em aberto.

**O que melhorou (vs rodada-01):** disciplina de fontes aplicada de forma transversal; a lacuna de
modelo de custo agregado deixou de ser slogan; Jev desacoplado por interface; gate humano com
política concreta (risk-tiering/amostragem/lote); runner JIT/efêmero reconciliado com K; cache de
índice restrito a read-only/não-compartilhado; PR externo exige isolamento forte.

**O que ainda falta (foco desta rodada):** (1) a reconciliação Max-assinatura-vs-API é **textualmente
clara mas numericamente frágil** — o "~R$550 ≈ US$100 → ~20M in / 4M out de Opus" trata orçamento
de assinatura e orçamento de API como fungíveis sem justificar a conversão; (2) **OpenRouter virou
ponto único de falha operacional** em B/I/K/L (billing, roteamento, fallback, *e* o acesso ao Jev)
sem plano de contingência se o OpenRouter cair/mudar preço/for bloqueado; (3) risco de
**privacidade/jurisdição dos provedores chineses** está nomeado mas tratado como "tranquilo para o
`roboto`" sem política operacional de qual tier vê qual código; (4) o próprio modelo de custo **não
tem baseline numérico nenhum** — define a estrutura ("teto por agente", "budget por issue") mas todo
número concreto está em perguntas em aberto, então ainda não é verificável.

A pesquisa segue em **rascunho forte pronto para refino**. Nenhuma regressão grave foi introduzida;
há uma inconsistência cross-trilha nova (K ainda cita "API do modelo/OpenRouter" na allowlist de
egress enquanto L fixa OpenRouter como único substrato — menor) e um resíduo de número de vendor
aceito literalmente em L (Jev "output grátis" e "0% erro de estrutura" propagados sem a ressalva
cética que a própria rodada-01 pediu).

---

## (b) Tabela de verificação da rodada-01

Legenda: **resolvido** / **parcial** / **aberto**. Finding → status + nota (cita o doc atual).

### Top 5 riscos da rodada-01

| # | Risco rodada-01 | Status | Nota |
|---|-----------------|--------|------|
| 1 | Números-âncora frágeis (D/F/I/J/K) | **resolvido** | Todos marcados "indicativos/ilustrativos" com ⚠️ nos 5 docs. D troca blog por acadêmico verificado; F "múltiplos ilustrativos"; I RouteLLM com fonte primária LMSYS; K Okta/23x "ilustrativo". |
| 2 | Jev como quase-decisão/SPOF em 4 trilhas | **parcial** | I agora diz "degrau 2 é interface; Jev é implementação plugável, com fallback de judge frontier"; seção Riscos diz "não alucina/CTO não são evidência". **Mas** L ainda lista Jev com "output grátis" como fato na tabela de preços, e I mantém "0% erro de estrutura, não alucina" no corpo (linha 16) — ver finding novo [I]. |
| 3 | Escada de validação sem orçamento de custo/latência | **parcial** | L cria o modelo de custo agregado (resolve o eixo custo). **Latência da escada encadeada (det→Jev→frontier) continua sem tratamento** em I/H/L — ver finding novo [L/cross]. |
| 4 | Custo de LLM não batcheia vs merge queue (D/J/I) | **resolvido** | D (item 8 + "Impacto em token"), J ("custo de LLM do review NÃO batcheia → Trilha L") e L (seção "Por que existe" + Unidades de custo) fecham o loop explicitamente. |
| 5 | Gate humano sem modelo de escala | **resolvido** | H §3 "Escala do gate": risk-tiering + amostragem + aprovação em lote; "humano é recurso escasso → gate seletivo por design". |

### Findings por trilha (rodada-01)

| Trilha | Finding rodada-01 | Status | Nota (doc atual) |
|--------|-------------------|--------|------------------|
| 0 | MTTR/GA como fato | **resolvido** | "MTTR -40–60% (número de blog… → indicativo, a verificar)"; GA "relatado". |
| 0 | Orquestrador ausente do mapa | **resolvido** | Bloco "Orquestrador / Dispatcher" add; "majoritariamente processo determinístico… não é um dos 9". |
| 0 | MVP vs fleet em checkbox | **resolvido** | "DECIDIDO: fleet completo" + grafo de dependência mínimo no corpo. |
| A | arXiv futuros não verificados | **parcial** | Nota "Fontes verificadas": ClarifyCodeBench/Ambig-SWE conferem; os outros 4 "não foram verificados… indicativos". Honesto, mas os IDs não-verificados seguem citados como grounding. |
| A | Auto-validação da DoR | **resolvido** | "Independência do validador: checklist + Jev independente do Refinamento; garantia dura é o checklist". |
| A | Estado de falha do loop | **resolvido** | Máquina de estados: "loop excede N → blocked + escala ao humano". |
| B | Runner persistente vs container efêmero | **resolvido** | "ephemeral/JIT runners… ou runner persistente que spawna containers efêmeros (dois níveis)". |
| B | Idempotência X-GitHub-Delivery vs Actions | **resolvido** | "por arquitetura: webhook=X-GitHub-Delivery; Actions=head_sha+tipo+nº". |
| B | Filtro-por-actor mata loop fix→review | **resolvido** | "Filtrar por actor com exceções… distinguir loop desejado por tipo de evento". |
| C | Limites de token como spec externa | **resolvido** | ⚠️ "diretriz das best practices / heurística, não limite técnico". |
| C | 9 agentes vs 7 skills | **resolvido** | SRE/Incidente add ao catálogo; nota "Arquitetura fundida c/ Planejamento… decisão explícita". |
| C | Hosting de skills em aberto | **parcial** | Elevado a "decisão de segurança" com proposta `.claude/skills/`, mas ainda em "perguntas em aberto" (coerente c/ fase). |
| D | Números de vendor como fundamentação | **resolvido** | ⚠️ vendor "indicativos"; evidência acadêmica verificada (QASecClaw/Sifting/CodeX-Verify). |
| D | Pipeline de review caro sem tiering | **resolvido** | Item 8 "Tiering do próprio review" (PR pequeno→1 passagem; grande→pipeline). |
| E | Hipótese "VALIDADA" (confirmatória) | **resolvido** | "SUPORTADA (fontes fracas)" + contra-argumento (código denso/algorítmico). |
| E | AGENTS.md custo fixo não contabilizado | **resolvido** | Cross-link L: "custo de token fixo → contabilizar no orçamento ou carregamento progressivo". |
| F | Múltiplos de blog como fato | **resolvido** | ⚠️ "múltiplos ilustrativos… medir no nosso caso (Trilha L)". |
| F | Data do ugrep volátil | **resolvido** | Suavizado p/ "detalhe sujeito a versão". |
| G | Scores de benchmark/nomes não verificados | **resolvido** | ⚠️ "scores/nomes não verificados… não rankear vendors". |
| G | Formato canônico de memória ausente | **resolvido** | "Esboço de formato": frontmatter tipo/data/ref + FTS5, provisório. |
| H | Números de eval como target | **resolvido** | ⚠️ "heurísticas iniciais de blogs, a calibrar". |
| H | Gate humano sem política | **resolvido** | §3 risk-tiering/amostragem/lote (= risco #5). |
| H | Rollback: checkpoint vs git revert | **resolvido** | "Default decidido: git revert + reabrir issue; checkpoint só exceção". |
| I | Jev dependência concentrada | **parcial** | Interface + fallback (ver risco #2); resíduo de claim de vendor permanece. |
| I | RouteLLM número ambíguo de blog | **resolvido** | Fonte primária LMSYS arXiv 2406.18665; números desambiguados (26% das queries, 95% qualidade). |
| J | Merge queue ~N× otimista | **resolvido** | Ressalva "~N× otimista; falha/flaky força re-split; 50–70% a validar". |
| J | Custo de LLM fora da política de escala | **resolvido** | "custo de LLM do review NÃO batcheia → Trilha L" (= risco #4). |
| K | Okta -92% / cache 23× sem fonte | **resolvido** | Ambos marcados "ilustrativo / sem fonte primária". |
| K | Cache warm fura isolamento | **resolvido** | "read-only / por-projeto-confiável / assinado, nunca compartilhado entre tasks não-confiáveis". |
| K | Repo público vs isolamento MVP | **resolvido** | "PR externo exige isolamento forte (gVisor/Firecracker) — não é opcional-MVP". |

### Cross-trilha (rodada-01)

| Finding cross | Status | Nota |
|---------------|--------|------|
| 0↔C contagem de agentes | **resolvido** | Ambos citam 9; C explicita fusão Arquitetura+Planejamento e SRE adiado. |
| A↔B idempotência/estados | **resolvido** | Estados de falha em A; idempotência por arquitetura em B. |
| D↔J↔I custo de LLM não orçado | **resolvido** | Trilha L é a resposta direta. |
| H↔J↔0 gate humano sem escala | **resolvido** | H §3. |
| I↔todas Jev não isolado | **parcial** | Interface declarada; resíduo de claim de vendor (ver [I] novo). |
| Geral qualidade de fonte datada no futuro | **parcial** | Disciplina aplicada e marcada; princípio no README. Resíduo: arXiv 26xx ainda citados como grounding em A/D/G/H (marcados, mas não removidos do argumento). |

**Placar:** de ~31 itens rastreáveis da rodada-01 → **~24 resolvidos, ~7 parciais, 0 abertos.**

---

## (c) Findings NOVOS por trilha

### Trilha L — Modelo de custo

**[Trilha L] claim-sem-evidência · alta · 0.75**
Evidência: "A unidade de orçamento do fleet é 1 assinatura Max ≈ R$ 550/mês (~US$100 na ordem de
grandeza → tier Max 5x…)" e "A Max (~R$550/mês) vira o teto mensal-alvo em $/token" + tabela
"Ordem de grandeza do que ~US$100/mês compra: Opus ≈ 20M in / 4M out…".
Problema: a conversão **assinatura Max → orçamento de API em dólar** é tratada como fungível sem
justificativa. Uma assinatura Max (valor fixo com rate limits, uso interativo — o próprio doc diz
isso) **não equivale** a "~US$100 de crédito de API/mês": o valor que a Anthropic cobra por uma
assinatura não é o custo de inferência que ela embute, e R$550 a ~US$5,5/USD dá ~US$100 só numa
taxa de câmbio específica não declarada. O número-âncora de todo o orçamento (20M in / 4M out de
Opus) está pendurado nessa equivalência não demonstrada.
Recomendação: declarar explicitamente que "R$550/mês" é um **teto de gasto arbitrado pelo dono em
dólar de API**, desacoplado do preço da assinatura Max (que serve só de referência de ordem de
grandeza); fixar a taxa de câmbio usada; e marcar os "20M in / 4M out" como ilustrativos de um blend
hipotético (o doc já diz "ilustrativo", mas a frase de abertura ainda apresenta a equivalência como
fato). Sem isso, o orçamento pode ser 1,5–2× off já na premissa.

**[Trilha L] under-spec · alta · 0.8**
Evidência: "Política de orçamento (proposta)" + "Perguntas em aberto (precisam do dono): ratear em
teto por tipo de agente… budget-alvo por issue… custo/issue aceitável… ".
Problema: a trilha define a **estrutura** do modelo de custo (unidades, alavancas, política) mas
**nenhum número concreto** — nem um teto por agente, nem um budget por issue, nem um custo/issue de
baseline. O objetivo declarado da trilha é "a economia seja comprovável e o gasto previsível"; sem
um único baseline numérico, o modelo ainda não é verificável — exatamente a crítica que originou a
trilha, agora um nível mais acima.
Recomendação: colocar no corpo pelo menos **um baseline estimado** (ex.: custo/issue grosseiro =
refino + plano + impl + review, com um blend de modelos assumido) mesmo que provisório, para que o
teto mensal possa ser aterrissado. É a diferença entre "temos um lugar para o número" e "temos o
número".

**[Trilha L] claim-sem-evidência · média · 0.6**
Evidência: tabela "Jev (judge) ~0,042 in / grátis out" apresentada na seção "Referência de preço de
API (verificado — claude-api…)".
Problema: a seção está sob o rótulo "verificado (claude-api)", mas a skill claude-api **só cobre
modelos Claude** — ela não verifica o preço do Jev. O "output grátis" do Jev é claim de vendor
(TypeSafe), que a própria rodada-01 pediu para marcar como indicativo e que I já ressalva. Aqui ele
aparece colado na tabela verificada, herdando credibilidade que não tem.
Recomendação: separar a linha do Jev da tabela "verificada" e marcá-la "indicativo (vendor TypeSafe,
a confirmar)", coerente com a disciplina de fontes e com a ressalva já presente em I.

### Trilha I — Roteamento de modelos (adições)

**[Trilha I] contradição · média · 0.7**
Evidência: linha 16 (corpo, degrau 2): "Saída type-safe (0% erro de estrutura, não alucina) +
confiança calibrada." vs. seção Riscos (linha 94): "'Não alucina (por construção)' … não são
evidência técnica… são premissas a testar."
Problema: o corpo afirma "não alucina" como característica do degrau, enquanto a seção de riscos
diz que isso não é evidência. Um leitor que para no corpo toma como fato o que a seção de riscos
desautoriza. É um resíduo da remediação do finding [I]-rodada-01 (a ressalva foi adicionada em
Riscos mas o claim original ficou no corpo).
Recomendação: no corpo, trocar "(0% erro de estrutura, não alucina)" por "(saída estruturada
type-safe; alegação de 'não alucina' do vendor — a validar, ver Riscos)". Alinha corpo e Riscos.

**[Trilha I] risco · alta · 0.75**
Evidência: "Provedores chineses + dados sensíveis/jurisdição: para o `roboto` (público/estudo) é
tranquilo; para código privado futuro, avaliar residência de dados…". Candidatos: "DeepSeek, Qwen,
GLM/Zhipu, Kimi/Moonshot" como workhorse de implementação/testes.
Problema: o risco está nomeado mas **a mitigação é adiada para "projetos privados futuros"**,
enquanto o mapa de tiers já coloca os modelos chineses como **workhorse de implementação/testes
agora**. Mesmo em repo público, o agente de Implementação pode ver: segredos em teste, trechos de
código de PRs de terceiros ainda não públicos, e o próprio conteúdo do `AGENTS.md`/regras internas.
"Público" não é o mesmo que "pode ir para qualquer jurisdição sem política". Não há regra operacional
de **qual tier vê qual dado**.
Recomendação: adicionar uma regra de roteamento por sensibilidade já no `roboto`: nenhum segredo,
token ou credencial em prompt de provedor chinês (reforça K §secrets); e definir que o tier de
geração barata recebe **diff + contexto público**, não dumps de ambiente. Classificar o dado, não só
o repo.

**[Trilha I] under-spec · média · 0.55**
Evidência: "Mapa modelo → tarefa (por benchmark)" + "Candidatos por tier (indicativo, a validar)…
flash tiers ~$0,15–0,60/MTok".
Problema: a tabela de benchmarks por tarefa é boa, mas a única ponte entre "benchmark" e "decisão"
é "validar no nosso golden set (Trilha H)". O golden set da Trilha H ainda é pergunta em aberto
("fonte inicial do golden set?"). Então o mecanismo de pin de modelo depende de um artefato que não
existe — a decisão de modelo fica circularmente dependente de H, que depende de dados reais, que
dependem do fleet rodar. Não é erro, mas o caminho crítico não está explícito.
Recomendação: marcar explicitamente a dependência circular (mapa→golden set→fleet rodando) e propor
um bootstrap: para o MVP, pinar por **relato de mercado + custo** e re-pinar após o primeiro golden
set, em vez de bloquear o pin na existência do golden set.

### Trilha K — Runtime (interação com a decisão de cobrança)

**[Trilha K] inconsistência-cross-trilha · baixa · 0.6**
Evidência: K §Egress: "deny-all + allowlist (GitHub, API do modelo/OpenRouter, feeds de segurança)".
vs. L/I: "OpenRouter é o substrato (único billing/roteamento)".
Problema: K lista "API do modelo/OpenRouter" como se fossem alternativas na allowlist, mas L/I
decidiram que **todo** tráfego de modelo passa por OpenRouter. Menor, mas se a allowlist permitir
"API do modelo" direto (api.anthropic.com etc.), abre um caminho que fura o billing único e a
contabilidade da Trilha L (gasto que não aparece no OpenRouter).
Recomendação: K deve dizer "egress de modelo = **somente** endpoint do OpenRouter" para preservar o
billing único de L; API direta de provedor só como exceção explícita e contabilizada.

---

## (d) Seção cross-trilha

**[Cross I↔L↔B↔K] OpenRouter como ponto único de falha não mitigado · alta · 0.8**
OpenRouter agora carrega: billing único (L), roteamento+fallback (I), acesso ao Jev (I: "rodamos o
Jev através do OpenRouter"), e é endpoint de egress (K). A decisão é coerente e reduz ops — mas
concentra **quatro funções críticas num terceiro**. Não há plano se o OpenRouter: cair, mudar preço,
remover um provedor chinês, ou bloquear a conta. O "fallback out-of-the-box" citado em I é fallback
**entre modelos dentro do OpenRouter**, não fallback **do OpenRouter**. A rodada-01 pediu para
desacoplar o Jev de um vendor; a rodada-02 o reacoplou a outro (OpenRouter) ao resolver o acesso.
Recomendação: registrar OpenRouter como dependência crítica com plano de contingência mínimo
(ex.: capacidade de apontar o cliente para API direta de 1 provedor Claude em emergência; o billing
degrada mas o fleet não para). Coerente com o princípio de não casar a arquitetura com um vendor.

**[Cross I↔L↔H] latência da escada encadeada ainda sem orçamento · média · 0.7**
A rodada-01 (risco #3) pediu custo **e latência** da escada det→Jev→frontier. L fecha o eixo custo;
**latência continua sem tratamento** em lugar nenhum. Encadear check determinístico + Jev + às vezes
frontier + (em review) multi-pass tem custo de latência por operação que afeta throughput do fleet
(Trilha J) e a experiência de gate humano. L mede "latência por tipo de tool" na observabilidade (H)
mas não há orçamento/alvo de latência por operação.
Recomendação: adicionar à L (ou H) um alvo de latência por etapa, ou ao menos reconhecer o trade-off
custo↔latência da escada (mais degraus = mais barato em $ mas mais lento em wall-clock).

**[Cross L↔I consistência de cobrança/runtime] · informativo · 0.6**
Positivo a registrar: B/I/K/L estão **coerentes** sobre o eixo central — API pay-per-token via
OpenRouter, Max como teto em $, modelos chineses nos tiers de geração, Claude no topo, Jev no judge.
Os cross-links fecham. As divergências acima são de grau (PUF do OpenRouter, latência, jurisdição),
não de direção. É uma melhora clara vs rodada-01, onde a cobrança não existia como eixo.

---

## (e) Lista priorizada de melhorias

1. **Aterrissar o orçamento da Trilha L com ≥1 baseline numérico** (custo/issue estimado + teto por
   agente), e **desacoplar textualmente** o teto em $ do preço da assinatura Max (fixar câmbio,
   marcar 20M/4M como ilustrativo). Sem isso a trilha ainda não cumpre "gasto previsível". [L, alta]
2. **Plano de contingência para OpenRouter como ponto único** (billing+roteamento+Jev+egress num
   terceiro). Caminho de emergência para API direta de 1 provedor. [cross I/L/B/K, alta]
3. **Política de roteamento por sensibilidade de dado** (não só por repo): nenhum segredo/credencial
   a provedor chinês; geração barata recebe diff+contexto público. Resolve o risco de jurisdição
   *agora*, não só "no futuro". [I, alta]
4. **Alinhar corpo e Riscos em I** sobre o Jev ("não alucina" → claim a validar no corpo) e **tirar
   o Jev da tabela "verificada" em L** (marcar indicativo). Resíduo da remediação do risco #2. [I/L, média]
5. **Orçamento/alvo de latência da escada encadeada** (det→Jev→frontier→multi-pass) — o eixo que a
   rodada-01 pediu junto com custo e que L só cobriu pela metade. [cross I/L/H, média]
6. **K: egress de modelo = somente OpenRouter** (preservar billing único da L). [K, baixa]
7. **I: marcar a dependência circular mapa→golden set→fleet** e propor bootstrap de pin por
   mercado+custo no MVP. [I, média-baixa]

---

> Nota de disciplina: nenhum finding marca issue como `done`; nenhuma mudança de fase é proposta.
> Cada finding cita trecho real do doc atual. As recomendações são para os autores decidirem — o
> auditor não edita os docs de trilha. Fato (verificável) separado de opinião (recomendação).
