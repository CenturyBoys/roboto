import { useEffect, useState } from 'react'
import { getHealth, getToken, setToken } from '@/lib/api'
import { useInstallPrompt } from '@/lib/use-install-prompt'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ToastProvider } from '@/components/ui/toast'
import { ExecList } from '@/components/ExecList'
import { ExecDetail } from '@/components/ExecDetail'
import { Costs } from '@/components/Costs'
import { FleetMonitor } from '@/components/FleetMonitor'
import { Interactions } from '@/components/Interactions'
import { IssuesList } from '@/components/IssuesList'
import { IssueRefine } from '@/components/IssueRefine'
import { ReviewPr } from '@/components/ReviewPr'
import { Setup } from '@/components/Setup'

type View = 'monitor' | 'execs' | 'issues' | 'interactions' | 'costs' | 'reviewpr'
type Mode = 'loading' | 'setup' | 'running'

const NAV: [View, string][] = [
  ['monitor', 'Monitor'],
  ['execs', 'Execuções'],
  ['issues', 'Issues'],
  ['interactions', 'Interações'],
  ['costs', 'Custos'],
  ['reviewpr', 'Revisar PR'],
]

export default function App() {
  const [token, setTok] = useState(getToken())
  const [saved, setSaved] = useState(false)
  const [view, setView] = useState<View>('execs')
  const [selected, setSelected] = useState<number | null>(null)
  const [selectedIssue, setSelectedIssue] = useState<number | null>(null)
  const [auto, setAuto] = useState(false)
  const [mode, setMode] = useState<Mode>('loading')
  const [settingsOpen, setSettingsOpen] = useState(false)
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
    setSelectedIssue(null)
    setAuto(false)
    setView(v)
  }
  const isActive = (v: View) => (v === 'execs' ? view === 'execs' && selected === null : view === v)

  return (
    <ToastProvider>
      <div className="min-h-full">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-background px-4 py-4 sm:px-6">
          <span className="text-2xl" style={{ filter: 'drop-shadow(0 0 6px rgba(255,210,30,.5))' }}>
            ⚡
          </span>
          <div className="text-xl font-extrabold tracking-wide">
            Potter <span className="text-sm font-normal text-muted">· console</span>
          </div>

          {/* Config (e token = segredo) sai da barra principal e vira um menu (regra 10). */}
          <div className="relative ml-auto">
            <Button
              variant="ghost"
              size="icon"
              aria-label="configurações"
              data-testid="settings-toggle"
              onClick={() => setSettingsOpen((o) => !o)}
            >
              ⚙
            </Button>
            {settingsOpen && (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setSettingsOpen(false)} />
                <div className="absolute right-0 top-11 z-30 w-72 rounded-xl border border-border bg-surface p-3 shadow-xl">
                  <label className="text-xs text-muted">Token do console</label>
                  <input
                    value={token}
                    onChange={(e) => {
                      setTok(e.target.value)
                      setSaved(false)
                    }}
                    type="password"
                    placeholder="CONSOLE_TOKEN"
                    className="mt-1 w-full rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
                  />
                  <div className="mt-2 flex items-center gap-2">
                    <Button variant="default" size="sm" onClick={save}>
                      salvar
                    </Button>
                    {saved && <span className="text-xs text-green-300">ok ✓</span>}
                    {canInstall && (
                      <Button variant="outline" size="sm" onClick={install}>
                        Instalar app
                      </Button>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </header>

        <main className="mx-auto max-w-5xl px-4 py-5 sm:px-6">
          {mode === 'loading' && <p className="text-muted">carregando…</p>}

          {mode === 'setup' && <Setup token={token} onReady={() => window.location.reload()} />}

          {mode === 'running' && (
            <>
              <div className="mb-5 flex flex-wrap items-center gap-1">
                {NAV.map(([v, label]) => (
                  <Button
                    key={v}
                    variant={isActive(v) ? 'default' : 'ghost'}
                    size="sm"
                    data-testid={`nav-${v}`}
                    onClick={() => go(v)}
                  >
                    {label}
                  </Button>
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto text-muted"
                  data-testid="auto-refresh"
                  onClick={() => setAuto((a) => !a)}
                  title="recarrega a lista a cada 4s"
                >
                  <span
                    className={cn('inline-block h-2 w-2 rounded-full', auto ? 'bg-green-400' : 'bg-border')}
                  />
                  Auto-refresh {auto ? 'on' : 'off'}
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
                <ExecDetail id={selected} onBack={() => setSelected(null)} onOpenRun={setSelected} />
              )}
              {view === 'issues' && selectedIssue === null && (
                <IssuesList onSelect={setSelectedIssue} />
              )}
              {view === 'issues' && selectedIssue !== null && (
                <IssueRefine
                  number={selectedIssue}
                  onBack={() => setSelectedIssue(null)}
                  onOpenRun={(runId) => {
                    setSelectedIssue(null)
                    setView('execs')
                    setSelected(runId)
                  }}
                />
              )}
              {view === 'monitor' && <FleetMonitor />}
              {view === 'interactions' && <Interactions />}
              {view === 'costs' && <Costs />}
              {view === 'reviewpr' && <ReviewPr />}
            </>
          )}
        </main>
      </div>
    </ToastProvider>
  )
}
