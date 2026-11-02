// Tempo relativo curto ("agora", "3 min", "2 h", "5 d") — legível (Nielsen #2), não ISO cru.
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const s = Math.max(0, (Date.now() - then) / 1000)
  if (s < 45) return 'agora'
  if (s < 90) return '1 min'
  const m = s / 60
  if (m < 60) return `${Math.round(m)} min`
  const h = m / 60
  if (h < 24) return `${Math.round(h)} h`
  const d = h / 24
  if (d < 30) return `${Math.round(d)} d`
  return new Date(iso).toLocaleDateString()
}
