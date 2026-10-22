# Auditoria independente — `ARCHITECTURE-C4.md` (vistas C4 + esboços)

> Auditor externo (postura adversarial, cética). Fase: **PESQUISA**. Não edito o doc — emito
> findings e recomendações. Régua: os 6 princípios do projeto + **disciplina de fontes**.
> Alvo: `research/ARCHITECTURE-C4.md`. Cross-check: README, SYNTHESIS, trilhas 0/B/C/G/H/I/K/M.

## Sumário executivo

**Veredito: C4 PARCIALMENTE bem aplicado — serve ao projeto como comunicação, mas tem um erro de
abstração estrutural no Nível 2 e omissões que o tornam enganoso em pontos de segurança.**

O que está certo: os três níveis existem e, no geral, não se misturam grosseiramente (Contexto =
pessoas/sistemas; Contêiner = unidades executáveis/armazenamento; Componente = partes de UM
contêiner). A sintaxe mermaid C4 é válida (`C4Context`/`C4Container`/`C4Component`, `Person`,
`Person_Ext`, `System_Ext`, `Container`, `ContainerDb`, `Container_Boundary`, `Rel`). As relações
têm verbo + direção. Os esboços estão **marcados como esboço** (bom) e o gate server-side, a
minimização de dados e o estado-na-issue aparecem corretamente.

O que está errado ou falta (top 5):
1. **"Fleet de agentes" como contêiner irmão do Runner contradiz a Trilha K** — K diz que o runner
   "hospeda os agentes" (eles rodam DENTRO do container efêmero). No C4 eles são contêineres
   separados com `Rel(runner, agents, "Executa")`. Abstração trocada: agentes são **componentes
   dentro do runner**, não um contêiner paralelo. (alta)
2. **O caminho de PR externo não-confiável desaparece no Nível 2** — K marca gVisor/Firecracker
   para código não-confiável como **"não é opcional-MVP"**; o Contexto tem `Person_Ext(contrib)`,
   mas o Contêiner mostra um único "container efêmero" uniforme, sem a fronteira de isolamento
   forte. Esboço/vista enganosa num ponto de segurança crítico. (alta)
3. **Feeds de segurança e o agente ambiente somem no Nível 2** — presentes no Contexto
   (`Rel(feeds, cd, ...)`), ausentes no Contêiner: nenhum `System_Ext(feeds)`, nenhum gatilho
   `schedule`/ambiente para o orquestrador. O gatilho **ambiente** (Trilha B/0) não é representado. (média)
4. **Observabilidade + bot Telegram fundidos num contêiner contraria o princípio da Trilha M** — M
   insiste que são **três capacidades distintas** ("a auditoria pegou a confusão original"). Juntar
   comunicação e observabilidade num único contêiner reintroduz exatamente a confusão que M desfez. (média)
5. **Anti-loop do esboço é o "filtro-por-actor cego" que a Trilha B proíbe** — o YAML usa
   `if: github.actor != 'roboto-bot'`, mas B exige "filtrar por actor **com exceções** (preserva o
   loop desejado fix→review)" e alerta contra o filtro cego "que mataria o loop fix→review". O
   esboço ilustra o anti-padrão. (média)

Conclusão de utilidade: as vistas comunicam bem o desenho de alto nível, mas **um leitor que confie
no Nível 2 concluiria que (a) agentes e runner são deploys separados e (b) todo PR roda no mesmo
sandbox** — ambos falsos pelas decisões já tomadas. Precisa de correção antes de virar referência.

---

## Findings

### Nível 1 — Contexto

```
[C4 | cross I] abstração-trocada · média · 0.7
Evidência: System_Ext(orr, "OpenRouter", "Gateway de LLMs: Claude, chineses, Jev")  +  (Nível 2)
  Container(gw, "Gateway de modelos", "interface", "roteia p/ OpenRouter + fallback ...")
Problema: Dois objetos chamados "gateway" (OpenRouter rotulado "Gateway de LLMs" no externo; e o
  contêiner interno "Gateway de modelos"). Colisão de rótulo que embaralha a abstração central da
  Trilha I — a arquitetura fala com UMA INTERFACE (gateway interno); OpenRouter é só UMA
  implementação. Chamar o externo de "gateway" apaga justamente esse desacoplamento.
Recomendação: Rotular o externo como "OpenRouter (provedor de inferência / substrato)", reservando
  a palavra "gateway" para o contêiner interno — e, no Nível 1, mostrar Jev como capacidade do
  substrato é OK, mas note que I diz que Jev também tem API direta (fallback).
```

```
[C4 | cross B/0] ator/container-faltando · média · 0.6
Evidência: Nível 1 tem Rel(feeds, cd, "Alimenta agente de seguranca (ambiente)"); Nível 2 NÃO tem
  o System_Ext(feeds) nem relação equivalente.
Problema: O gatilho **ambiente** (feed/schedule — caso canônico do agente de Segurança, Trilhas 0 e
  B) existe no Contexto e evapora no Contêiner. Fica parecendo que só há caminho reativo (webhook).
Recomendação: No Nível 2, incluir System_Ext(feeds) → orch com rótulo "schedule/feed (ambiente)",
  ou um Rel no orquestrador representando o dispatch por cron/feed.
```

### Nível 2 — Contêineres

```
[C4 | cross K] abstração-trocada · alta · 0.85
Evidência: Container(runner, "Runner + runtime", "container efemero + git worktree", "1 por task,
  hospeda os agentes") ao lado de Container(agents, "Fleet de agentes", ...) com
  Rel(runner, agents, "Executa").
Problema: O próprio rótulo do runner diz "hospeda os agentes" — i.e., os agentes rodam DENTRO do
  container efêmero (confirmado em K: "cada agente = container efêmero + git worktree"). Em C4, um
  contêiner é uma unidade executável/deployável independente. "Fleet de agentes" NÃO é deployável
  separado do runner; é o processo que roda nele. Logo é **componente(s) dentro do runner**, não um
  contêiner irmão. O Rel "runner Executa agents" denuncia a inversão (contêiner não "executa" outro
  contêiner como se fosse código seu).
Recomendação: Fundir em um contêiner "Runner + agente (container efêmero, 1/ task)" e mover o "Fleet
  de agentes" para o Nível 3 (já é o zoom "Agente de Implementação"). Se quiser mostrar o fleet como
  tipos, use Component no Nível 3, não Container no Nível 2.
```

```
[C4 | cross K/H] under-spec · alta · 0.8
Evidência: Container(runner, "Runner + runtime", "container efemero + git worktree", "1 por task...")
  — único, uniforme. Nível 1 declara Person_Ext(contrib, "Contribuidor externo", "Abre PR no repo
  publico").
Problema: K é explícito: "o caminho de PR externo **exige isolamento forte (gVisor/Firecracker) —
  não é opcional-MVP**; container padrão só para código confiável nosso." A vista de contêiner
  mostra UM runner para tudo, apagando a fronteira de confiança. Para um doc de arquitetura isso é
  enganoso num ponto de segurança — exatamente o tipo de omissão que vira decisão errada de deploy.
Recomendação: Representar dois perfis de runner (ou uma nota de boundary): "runner confiável
  (código nosso)" vs "runner microVM/gVisor (PR externo não-confiável)", com o Person_Ext(contrib)
  roteado para o segundo.
```

```
[C4 | cross M] viola-princípio · média · 0.7
Evidência: Container(obs, "Observabilidade + bot Telegram", "monitor", "duracao/custo/erros;
  notifica/aprova").
Problema: A Trilha M foi reescrita justamente para separar **três capacidades** ("A auditoria pegou
  a confusão original. São três coisas separadas: comunicação/aprovação (Telegram); observabilidade
  (monitor); continuidade"). Fundir Telegram + observabilidade num contêiner reintroduz a confusão.
  Além disso M diz que o dono da plataforma de observabilidade é a **Trilha H** (uma escolha única
  que M e L consomem) — o C4 a trata como peça nova própria do sistema.
Recomendação: Separar em "Bot/Notificador Telegram (comunicação + gatilho de conveniência)" e
  "Observabilidade (plataforma decidida na H)". Deixar claro que a observabilidade é consumida, não
  um contêiner inventado aqui.
```

```
[C4 | cross M] ator/container-faltando · média · 0.65
Evidência: Nível 2 não representa continuidade/estado durável. ContainerDb(mem) é escrito por
  agents; orquestrador não tem relação com mem nem com nenhum store de estado/checkpoint.
Problema: M decide que **"o estado durável vive FORA do container efêmero" (store externo / camada
  do orquestrador); um container novo retoma do checkpoint externo**. No diagrama, o orquestrador
  (peça que M responsabiliza pela persistência/resume) não toca nenhum armazenamento. Falta o
  "run journal / estado durável" como relação do orquestrador — senão o leitor não vê onde o
  resume-pós-falha (K efêmero) ancora.
Recomendação: Adicionar relação orch → (mem ou store de estado) com rótulo "persiste estado /
  checkpoint (fora do container efêmero)"; ou um ContainerDb separado "Estado/run journal".
```

```
[C4 | cross I] under-spec · baixa · 0.55
Evidência: Rel(gw, orr, "HTTPS") é a única saída do gateway; o fallback (APIs diretas / LiteLLM
  self-host / Jev direto) só aparece em comentário no esboço do Nível 4.
Problema: A Trilha I trata o fallback como mitigação de **ponto único** (OpenRouter concentra 4
  funções) — decisão de desenho, não detalhe. No Nível 2 ele some. Sub-especificado para algo que a
  pesquisa marca como risco resolvido pela arquitetura.
Recomendação: Desenhar Rel(gw -. fallback .-> <APIs diretas / LiteLLM / Jev direto>) como no
  SYNTHESIS §8 (que já mostra o fallback). Manter paridade entre SYNTHESIS e C4.
```

```
[C4] c4-mal-aplicado · baixa · 0.5
Evidência: Container(orch, "Orquestrador / Dispatcher", "processo deterministico", ...).
Problema: O 2º argumento do Container em C4 é a **tecnologia** (ex.: "Python/worker", "Celery").
  "processo deterministico" é uma característica/decisão, não tecnologia. Idem runner ("container
  efemero + git worktree" mistura tech + característica). Rótulo de tecnologia impreciso (regra C4).
Recomendação: Separar tecnologia (ex.: "Python + fila") da nota de característica (campo descrição).
  Baixa severidade — é qualidade de rótulo, não erro estrutural.
```

### Nível 3 — Componentes (zoom no Agente)

```
[C4 | cross 0/I] c4-mal-aplicado · média · 0.65
Evidência: Component(router, "Escada de validacao", "right-sizing", "check deterministico -> Jev ->
  frontier") DENTRO do Container_Boundary(agent).
Problema: A escada atravessa fronteiras de contêiner — o tier 1 (check determinístico: lint/test/
  type/build, SEM LLM) é **CI/processo** (Trilha 0: "o gate de 'done' é determinístico... rodar
  teste é CI, não LLM"; Trilha I tier 1). Modelar a escada inteira como componente INTERNO do agente
  sugere que o agente roda os próprios checks determinísticos — o que viola "determinismo primeiro /
  CI é o juiz". O tier 3 (frontier) também não vive no agente: vai pelo contêiner Gateway.
Recomendação: Dentro do agente, o componente é "decisor de tier / cliente da escada" (decide e
  delega); deixar explícito que o check determinístico é o CI (externo) e o frontier é o Gateway
  (externo). Não desenhar a escada como lógica proprietária do agente.
```

```
[C4] c4-mal-aplicado · baixa · 0.4
Evidência: Component(memc, "Cliente de memoria", "", ...) e Rel(memc, mem, "") — tecnologia vazia e
  relação sem rótulo (verbo).
Problema: C4 recomenda relações rotuladas com verbo + direção. Rel sem label e tech vazia reduzem a
  legibilidade (válido em sintaxe, fraco em padrão).
Recomendação: Rotular (ex.: Rel(memc, mem, "lê/escreve .md + consulta FTS5")); preencher ou omitir a
  tech de forma consistente.
```

### Nível 4 — Esboços de implementação

```
[C4 | cross B] inconsistência-cross-trilha · média · 0.8
Evidência: # .github/workflows/refine.yml  →  if: github.actor != 'roboto-bot'   # anti-loop (Trilha B)
Problema: B diz literalmente: "Filtrar por actor **com exceções**: ignorar eventos do bot EXCETO os
  que alimentam o loop desejado (bot commita → CI → bot corrige)... não um filtro-por-actor cego
  (que mataria o loop fix→review)." O esboço rotulado "anti-loop (Trilha B)" implementa exatamente o
  filtro cego que B rejeita. Pior: está marcado como se fosse a aplicação correta de B.
Recomendação: Ajustar o esboço para refletir B — filtro por actor + exceção por tipo de evento +
  loop breaker bounded (contador por issue/PR). Ou remover o comentário "anti-loop (Trilha B)" para
  não dar a impressão de que isto É o anti-loop da B.
```

```
[C4 | cross I/H] over-spec · baixa · 0.5
Evidência: interface ModelGateway { deterministic(task): Result; // (na verdade: nem chama LLM) ... }
Problema: Pôr "deterministic" como método do ModelGateway mistura o tier 1 (que NÃO é LLM e NÃO é
  do gateway de modelos — é CI/check) dentro da interface do gateway. O próprio comentário admite a
  contradição ("nem chama LLM"). Conceitualmente embaralha quem é dono do tier 1.
Recomendação: Tirar `deterministic` da interface do gateway; o roteador decide "é check
  determinístico? → chama CI/runner de teste; senão → gateway.judge/generate". Mantém determinismo
  primeiro limpo.
```

```
[C4 | cross M/H] (positivo / sem ação) · — · 0.9
Evidência: gate sketch → persistState("PENDING_APPROVAL") na issue; notifyTelegram(idsResumoSemCodigo);
  await waitApprovalRevalidatedServerSide(); // autoridade verificada no servidor.
Problema: Nenhum — o esboço do gate está coerente com M/H (estado na issue, dados mínimos, GitHub
  canônico, revalidação server-side, anti-loopjacking implícito).
Recomendação: Manter. Registrado como contraste: o gate está certo; o anti-loop (acima) não.
```

```
[C4] esboço-enganoso · baixa · 0.3
Evidência: "> ⚠️ Esboços para comunicar o desenho — não é código de produção (fase de pesquisa)."
Problema: A marcação de "esboço" existe e é clara (bom). Risco residual baixo: o YAML tem aparência
  de workflow pronto-para-colar e já carrega um anti-padrão (o filtro cego). Esboço errado é mais
  perigoso que esboço genérico.
Recomendação: Além do aviso global, anotar inline o que é simplificação deliberada vs o que seria a
  forma correta (sobretudo no anti-loop).
```

---

## Consistência cross-trilha (resumo)

| Trilha | Decisão/princípio | O C4 reflete? | Observação |
|--------|-------------------|---------------|------------|
| 0 | 9 agentes + orquestrador como processo determinístico | Parcial | Orquestrador OK; "fleet" como contêiner é abstração trocada (ver alta) |
| B | gatilhos reativo/ambiente/sob demanda; anti-loop COM exceções | Não | Ambiente some no N2; esboço de anti-loop é o filtro cego que B proíbe |
| C | skills + subagents + MCP como peças do agente | Sim | N3 reflete bem (skill/tools/router/clientes) |
| G | separar STORAGE (.md+git) de SEARCH (FTS5) | Sim | ContainerDb(mem) "markdown+git + FTS5" casa com G |
| H | output=proposta; gate por impacto; isolamento obrigatório | Parcial | Gate N4 OK; isolamento forte p/ não-confiável ausente no N2 |
| I | gateway = interface; OpenRouter uma impl; fallback; Jev isolado | Parcial | Interface OK no N2; colisão de rótulo "gateway"; fallback só no N4 |
| K | runner efêmero 1/ task hospeda agentes; gVisor p/ externo; Vault | Parcial | "hospeda agentes" contradiz contêiner separado; isolamento forte ausente |
| M | 3 capacidades distintas; estado durável FORA do efêmero; GitHub canônico | Parcial | Telegram+obs fundidos (contra M); estado durável do orquestrador não desenhado |

**Contradições internas do próprio C4:**
- `runner "hospeda os agentes"` (texto) vs `agents` como contêiner separado com `runner Executa agents` (grafo).
- `Person_Ext(contrib)` no N1 sem caminho de isolamento correspondente no N2.
- `feeds → cd` no N1 sem contrapartida no N2.
- Fallback do gateway presente no SYNTHESIS §8 e no esboço N4, ausente no grafo N2 (SYNTHESIS e C4 divergem).

**Disciplina de fontes:** o doc C4 não introduz claims numéricos novos (bom) — herda as decisões das
trilhas. Nenhum número de vendor não-marcado foi inserido. Sem violação de disciplina de fontes aqui.

---

## Lista priorizada de melhorias (o que endereçar primeiro)

1. **(alta)** Corrigir a abstração do Nível 2: fundir runner+agentes (runner "hospeda os agentes");
   mover "fleet de agentes" para o Nível 3. — resolve a contradição-raiz com K.
2. **(alta)** Representar o caminho de PR externo não-confiável com isolamento forte
   (gVisor/Firecracker) no Nível 2 — K marca como não-opcional-MVP; é segurança.
3. **(média)** Reintroduzir, no Nível 2, o gatilho **ambiente** (feeds/schedule) e o fallback do
   gateway; alinhar com SYNTHESIS §8.
4. **(média)** Separar Telegram (comunicação) de Observabilidade (plataforma da H) — honrar a
   distinção que M estabeleceu.
5. **(média)** Desenhar o estado durável/checkpoint do orquestrador FORA do container efêmero (M).
6. **(média)** Corrigir o esboço de anti-loop para o padrão da B (filtro com exceções + loop breaker);
   ou remover o rótulo "(Trilha B)" que o legitima.
7. **(baixa)** Nível 3: a escada como "decisor/cliente de tier", não lógica proprietária do agente;
   deixar claro que tier 1 = CI e tier 3 = Gateway (externos ao agente).
8. **(baixa)** Higiene C4: rótulos de tecnologia reais (não características) nos Container; relações
   do Nível 3 com verbo; desfazer a colisão de rótulo "gateway" (externo vs interno).

### Contagem por severidade
- Alta: 2
- Média: 6
- Baixa: 5
- (positivo registrado: 1)

---

> Fase PESQUISA. Nenhuma issue marcada como `done`. Findings são proposta de auditoria externa, não
> edição dos documentos. Épico de referência: **#13**.
