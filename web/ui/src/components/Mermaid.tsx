import { useEffect, useRef, useState } from 'react'

// Renderiza um bloco ```mermaid como diagrama. O `mermaid` é pesado (~vários MB) → carrega
// SOB DEMANDA (dynamic import) só quando um diagrama aparece, p/ não inflar o bundle principal.
let _seq = 0
let _mermaidP: Promise<typeof import('mermaid').default> | null = null
function loadMermaid() {
  if (!_mermaidP) {
    _mermaidP = import('mermaid').then((m) => {
      m.default.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' })
      return m.default
    })
  }
  return _mermaidP
}

export function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    const id = `mmd-${_seq++}`
    loadMermaid()
      .then((mermaid) => mermaid.render(id, chart.trim()))
      .then(({ svg }) => {
        if (alive && ref.current) ref.current.innerHTML = svg
      })
      .catch((e) => alive && setErr(String(e?.message || e)))
    return () => {
      alive = false
    }
  }, [chart])
  // erro de sintaxe no diagrama → cai pro código cru (não quebra a leitura do resto)
  if (err)
    return (
      <pre className="overflow-auto whitespace-pre-wrap text-xs text-red-300">{chart}</pre>
    )
  return <div ref={ref} className="my-2 overflow-auto" />
}
