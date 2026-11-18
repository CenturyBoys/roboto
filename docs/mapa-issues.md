# Mapa de issues (árvore/DAG)

> Documento **operacional** (como funciona hoje). A aba **Mapa** do cockpit mostra o grafo das
> issues abertas — quem é épico, quem é filha de quê e o que bloqueia o quê — cruzando as
> dependências que **nós** gravamos com as **nativas** do GitHub.
> **Princípio-âncora:** determinismo primeiro — o grafo é montado por **código** (parse + GraphQL),
> sem decisão de LLM; as nossas deps são a **fonte primária**, as nativas **enriquecem**.

## 1. Para que serve

O operador abre a aba **Mapa** e vê, num golpe, a topologia do backlog aberto:

- **Épicos** (guarda-chuva) com suas **filhas** aninhadas (épico → filha → folha);
- **Bloqueios**: uma issue que *depende de* outra aparece marcada (`⛔ depende de #N`);
- **Cross-references** nativas do GitHub (`↔ N`) como enriquecimento.

Clicar num nó abre o **refino** daquela issue (vai para a aba *Issues*).

## 2. Fontes de dados (cruza as duas)

### 2.1 Nossas (fonte primária — gravadas no corpo da issue)

Determinísticas, parseadas do **corpo** de cada issue aberta:

| Sinal no corpo | De onde vem | Vira aresta |
|---|---|---|
| `Parte do épico #N` | `app/breakdown_apply.py` grava isso nas sub-issues ao materializar um breakdown | `epic-child` (N → filha) |
| `Depende de #N` / `blocked by #N` | gate de scheduling; parse reusa `app/deps.py:blocked_by` | `depends-on` (filha → bloqueadora) |

A detecção de **épico** reusa `agents/breakdown.py:is_epic(title, body)` (heurística determinística,
não LLM).

### 2.2 Nativas do GitHub (enriquecimento — via GraphQL)

O cliente GitHub (`github/app.py`) ganhou `native_issue_links(repo, numbers)`, que consulta via
**GraphQL** (token já configurado), em lotes:

- **sub-issues**: `parent` / `subIssues` → `subissue-native` (pai → filha);
- **task-lists**: `trackedIssues` / `trackedInIssues` → `subissue-native`;
- **cross-references**: `timelineItems(CROSS_REFERENCED_EVENT)` → `xref` (origem → esta).

**Degrada gracioso:** se a API nativa recusar os campos (preview/indisponível) ou o GraphQL
retornar `errors`, o mapa sai **só com as nossas deps** — nunca quebra.

## 3. Backend

- **Função pura** `app/issue_graph.py:build_graph(issues, native_edges)` — recebe as issues
  (`RawIssue` com corpo) + as arestas nativas já resolvidas e devolve `IssueGraph`
  (`nodes` + `edges` + `has_cycle`). Sem I/O, 100% testável. Faz o **merge** e deduplica por
  `(source, target, kind)` — a mesma aresta nativa vinda de dois caminhos colapsa; kinds distintos
  (nossa `epic-child` × nativa `subissue-native`) convivem.
- **Corte de ruído:** `xref` só entra se **ambas** as pontas forem issues conhecidas (descarta PRs e
  issues fechadas).
- **Ciclos:** detectados por DFS (3 cores) e sinalizados em `has_cycle` — o grafo **não quebra**
  (DAG best-effort); a UI avisa e evita repetir ramo infinitamente.
- **Endpoint** `GET /issues/tree` (em `web/console.py`, mesmo padrão de auth bearer / isolamento por
  empresa dos handlers `overview`/`list_issues`): lista as abertas com
  `IssueSource.list_open_issues_full` (nº, título, **corpo**, labels, state), puxa as nativas e
  devolve o grafo.

### Shape da resposta

```json
{
  "repo": "org/app",
  "nodes": [{ "number": 1, "title": "Épico X", "labels": ["epic"], "is_epic": true, "state": "open" }],
  "edges": [{ "from": 1, "to": 2, "kind": "epic-child" }],
  "has_cycle": false
}
```

`kind` ∈ `epic-child` | `depends-on` | `subissue-native` | `xref`, sempre no sentido
**pai/bloqueador → dependente**.

## 4. Frontend

Aba **Mapa** (`web/ui/src/App.tsx`) → componente `components/IssueTree.tsx`, consome `GET /issues/tree`
via `lib/api.ts` (`getIssueTree`; tipos em `types.ts`). Render em **árvore indentada**: hierarquia
`epic-child` + `subissue-native` vira o aninhamento; `depends-on` vira o badge de bloqueio; cor do
nó por estado (épico / bloqueada / livre / fechada). SVG não foi necessário — a árvore indentada é
mais legível e sem dependência nova.

## 5. Testes

- Backend: `tests/test_issue_graph.py` — função pura (épico→filhas, depends-on, ciclo, merge
  nossas+nativas, corte de xref) e o endpoint (merge + auth + degrade quando o GraphQL falha).
- Front: `web/ui/src/components/IssueTree.test.tsx` — aninhamento épico→filhas, badge de bloqueio,
  clique abre o refino, aviso de ciclo.
