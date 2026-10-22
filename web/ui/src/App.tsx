import { useEffect, useState } from 'react'
import { getHealth, getToken, setToken } from '@/lib/api'
import { useInstallPrompt } from '@/lib/use-install-prompt'
import { Button } from '@/components/ui/button'
import { ExecList } from '@/components/ExecList'
import { ExecDetail } from '@/components/ExecDetail'
import { Costs } from '@/components/Costs'
import { Interactions } from '@/components/Interactions'
import { Setup } from '@/components/Setup'

type View = 'execs' | 'interactions' | 'costs'
type Mode = 'loading' | 'setup' | 'running'

export default function App() {
  const [token, setTok] = useState(getToken())
  const [saved, setSaved] = useState(false)
  const [view, setView] = useState<View>('execs')
  const [selected, setSelected] = useState<number | null>(null)
  const [auto, setAuto] = useState(false)
  const [mode, setMode] = useState<Mode>('loading')
  const [canInstall, install] = useInstallPrompt()

  // /healthz diz se o daemon está em modo setup (falta config) ou normal. Falha = assume normal.
  useEffect(() => {
    getHealth()
      .then((h) => setMode(h.mode))
      .catch(() => setMode('running'))
  }, [])

  function save() {
    setToken(token)
    setSaved(true)
  }
  function go(v: View) {
    setSelected(null)
    setAuto(false)
    setView(v)
  }

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-background px-4 py-4 sm:px-6">
        <span className="text-2xl" style={{ filter: 'drop-shadow(0 0 6px rgba(255,210,30,.5))' }}>
          ⚡
        </span>
        <div className="text-xl font-extrabold tracking-wide">
          Potter <span className="text-sm font-normal text-muted">· console</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-5 sm:px-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <input
            value={token}
            onChange={(e) => {
              setTok(e.target.value)
              setSaved(false)
            }}
            placeholder="CONSOLE_TOKEN"
            className="w-full rounded-lg border border-border bg-surface px-2.5 py-2 text-sm outline-none focus:border-accent sm:w-60"
          />
          <Button variant="outline" onClick={save}>
            salvar token
          </Button>
          {saved && <span className="text-sm text-muted">ok ✓</span>}
          {canInstall && <Button onClick={install}>Instalar app</Button>}
        </div>

        {mode === 'loading' && <p className="text-muted">carregando…</p>}

        {mode === 'setup' && <Setup token={token} onReady={() => window.location.reload()} />}

        {mode === 'running' && (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Button
                variant={view === 'execs' && selected === null ? 'default' : 'outline'}
                onClick={() => go('execs')}
              >
                Execuções
              </Button>
              <Button
                variant={view === 'interactions' ? 'default' : 'outline'}
                onClick={() => go('interactions')}
              >
                Interações pendentes
              </Button>
              <Button variant={view === 'costs' ? 'default' : 'outline'} onClick={() => go('costs')}>
                Custos
              </Button>
              <Button variant={auto ? 'default' : 'outline'} onClick={() => setAuto((a) => !a)}>
                Auto-refresh: {auto ? 'on' : 'off'}
              </Button>
            </div>

            {view === 'execs' && selected === null && (
              <ExecList
                auto={auto}
                onSelect={(id) => {
                  setAuto(false)
                  setSelected(id)
                }}
              />
            )}
            {view === 'execs' && selected !== null && (
              <ExecDetail id={selected} onBack={() => setSelected(null)} />
            )}
            {view === 'interactions' && <Interactions />}
            {view === 'costs' && <Costs />}
          </>
        )}
      </main>
    </div>
  )
}
