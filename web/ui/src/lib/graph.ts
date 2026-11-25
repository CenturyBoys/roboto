// Transitividade de dependências (bloqueador-raiz / destrava N) — DERIVADA das arestas, não
// materializada nas issues (duplicar "depende de #N" nos corpos desincroniza). Determinístico: o
// grafo guarda só a aresta DIRETA; aqui computamos o fecho transitivo pela cadeia de bloqueios.
//
// Convenção (igual ao IssueTree): `blockers.get(X)` = issues das quais X DEPENDE (que bloqueiam X).
// Bloqueador FECHADO está resolvido → não propaga (a cadeia só anda por nós ABERTOS).

/** Bloqueador(es)-RAIZ ABERTO(s) de cada nó: o fundo ABERTO da cadeia que de fato o segura (#287 →
 * raiz #398). Raiz = bloqueador aberto que não tem bloqueador aberto próprio. Vazio = nada o trava. */
export function rootOpenBlockers(
  blockers: Map<number, number[]>,
  isClosed: (n: number) => boolean,
): Map<number, number[]> {
  const openBlockers = (n: number) => (blockers.get(n) ?? []).filter((b) => !isClosed(b))
  const memo = new Map<number, number[]>()
  const onPath = new Set<number>()
  function roots(n: number): number[] {
    const cached = memo.get(n)
    if (cached) return cached
    if (onPath.has(n)) return [] // guarda de ciclo (o mapa é best-effort)
    onPath.add(n)
    const acc = new Set<number>()
    for (const b of openBlockers(n)) {
      if (openBlockers(b).length === 0) acc.add(b) // b é raiz (sem bloqueador aberto)
      else for (const r of roots(b)) acc.add(r)
    }
    onPath.delete(n)
    const arr = [...acc].sort((a, z) => a - z)
    memo.set(n, arr)
    return arr
  }
  const out = new Map<number, number[]>()
  for (const n of blockers.keys()) {
    const r = roots(n)
    if (r.length) out.set(n, r)
  }
  return out
}

/** Quantas issues ABERTAS cada nó destrava em CASCATA (fecho transitivo reverso) — a alavanca dele
 * (#398 → destrava 8). Só conta nós abertos; bloqueador/dependente fechado não entra. */
export function unblockCounts(
  blockers: Map<number, number[]>,
  isClosed: (n: number) => boolean,
): Map<number, number> {
  // grafo REVERSO "b bloqueia n" (só arestas abertas→abertas)
  const blocks = new Map<number, number[]>()
  for (const [n, bs] of blockers) {
    if (isClosed(n)) continue
    for (const b of bs) {
      if (isClosed(b)) continue
      const arr = blocks.get(b) ?? []
      arr.push(n)
      blocks.set(b, arr)
    }
  }
  const out = new Map<number, number>()
  for (const b of blocks.keys()) {
    const seen = new Set<number>()
    const stack = [...(blocks.get(b) ?? [])]
    while (stack.length) {
      const x = stack.pop()!
      if (seen.has(x)) continue
      seen.add(x)
      for (const y of blocks.get(x) ?? []) stack.push(y)
    }
    if (seen.size) out.set(b, seen.size)
  }
  return out
}
