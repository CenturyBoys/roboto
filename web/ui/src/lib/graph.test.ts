import { describe, expect, it } from 'vitest'
import { rootOpenBlockers, unblockCounts } from './graph'

// cadeia real do épico #73: #398(T2) → #286 → #287 → … → #293; #281 fechado.
function chain(): { blockers: Map<number, number[]>; closed: Set<number> } {
  const blockers = new Map<number, number[]>([
    [286, [281, 398]],
    [287, [286]],
    [288, [287]],
    [289, [288]],
    [290, [289]],
    [291, [290]],
    [292, [291]],
    [293, [292]],
  ])
  return { blockers, closed: new Set([281]) } // #281 já fechado; o resto aberto
}

describe('rootOpenBlockers', () => {
  it('aponta o #398 como raiz ABERTA de toda a cadeia', () => {
    const { blockers, closed } = chain()
    const r = rootOpenBlockers(blockers, (n) => closed.has(n))
    expect(r.get(293)).toEqual([398]) // o fundo da cadeia é o #398
    expect(r.get(287)).toEqual([398])
    expect(r.get(286)).toEqual([398]) // #281 fechado não é raiz; #398 sim
  })

  it('não propaga por bloqueador fechado', () => {
    // #286 fechado → #287 deixa de ser bloqueado transitivamente pelo #398
    const { blockers } = chain()
    const r = rootOpenBlockers(blockers, (n) => n === 281 || n === 286)
    expect(r.get(287) ?? []).toEqual([]) // #286 resolvido → #287 livre
  })
})

describe('unblockCounts', () => {
  it('#398 destrava 8 em cascata; #286 destrava 7', () => {
    const { blockers, closed } = chain()
    const u = unblockCounts(blockers, (n) => closed.has(n))
    expect(u.get(398)).toBe(8) // #286..#293
    expect(u.get(286)).toBe(7) // #287..#293
    expect(u.get(292)).toBe(1) // só #293
  })

  it('issue folha não destrava ninguém', () => {
    const { blockers, closed } = chain()
    const u = unblockCounts(blockers, (n) => closed.has(n))
    expect(u.get(293)).toBeUndefined()
  })
})
