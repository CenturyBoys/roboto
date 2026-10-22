import { useCallback, useEffect, useState } from 'react'
import { getHealth, getSetupStatus, saveSetup } from '@/lib/api'
import type { SetupStatus } from '@/types'
import { Button } from './ui/button'
import { Card, CardTitle } from './ui/card'

// Campos que a tela oferece (origem alternativa ao .env; tudo persiste no banco). GitHub aqui é
// via PAT (modo App pode ser adicionado depois). DATABASE_URL/CONSOLE_TOKEN são bootstrap (via env).
interface Field {
  key: string
  label: string
  required?: boolean
  secret?: boolean
  placeholder?: string
}
const FIELDS: Field[] = [
  { key: 'ROBOTO_TENANT', label: 'Tenant (empresa)', required: true },
  { key: 'ROBOTO_DEFAULT_REPO', label: 'Repo padrão (owner/nome)', required: true },
  { key: 'TELEGRAM_BOT_TOKEN', label: 'Telegram bot token', required: true, secret: true },
  { key: 'OPENROUTER_API_KEY', label: 'OpenRouter API key', required: true, secret: true },
  { key: 'GITHUB_API_TOKEN', label: 'GitHub token (PAT)', required: true, secret: true },
  { key: 'TELEGRAM_ALLOWLIST', label: 'Telegram allowlist (IDs, vírgula)' },
  { key: 'ROBOTO_ENGINE', label: 'Motor', placeholder: 'stub | claude_code' },
  { key: 'ROBOTO_CHAT_ID', label: 'Chat ID padrão (perguntas do motor)' },
  { key: 'TTYD_BASE', label: 'URL do terminal (ttyd), opcional' },
]

async function waitRunning(): Promise<void> {
  for (let i = 0; i < 40; i++) {
    try {
      const h = await getHealth()
      if (h.mode === 'running') return
    } catch {
      /* o daemon está reiniciando (setup -> running): tolera a janela sem servidor */
    }
    await new Promise((r) => setTimeout(r, 1500))
  }
}

export function Setup({ token, onReady }: { token: string; onReady: () => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await getSetupStatus())
      setMsg(null)
    } catch {
      setStatus(null)
      setMsg('não autorizado — salve o CONSOLE_TOKEN acima e tente de novo')
    }
  }, [])

  useEffect(() => {
    if (token) void loadStatus()
  }, [token, loadStatus])

  async function submit() {
    setSaving(true)
    try {
      const nonEmpty = Object.fromEntries(
        Object.entries(values).filter(([, v]) => v.trim()),
      )
      const res = await saveSetup(nonEmpty)
      setStatus(res)
      if (res.configured) {
        setMsg('Config completa — iniciando o fleet…')
        await waitRunning()
        onReady()
      } else {
        setMsg(`Salvo. Ainda falta: ${res.missing.join(', ')}`)
      }
    } catch {
      setMsg('erro ao salvar (CONSOLE_TOKEN correto?)')
    } finally {
      setSaving(false)
    }
  }

  const isSet = (key: string) => status?.present.includes(key) ?? false

  return (
    <Card>
      <CardTitle>Configuração do fleet</CardTitle>
      <p className="mb-3 text-sm text-muted">
        O fleet ainda não está configurado. Preencha abaixo (vai para o banco — mesma coisa que o{' '}
        <span className="font-mono">.env</span>, só muda a origem). Campos já definidos podem ficar
        em branco para manter.
      </p>

      {!token && (
        <p className="mb-3 text-sm text-accent">Salve o CONSOLE_TOKEN na barra acima primeiro.</p>
      )}

      <div className="flex flex-col gap-3">
        {FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">
            <span className="text-sm">
              {f.label}
              {f.required && <span className="text-accent"> *</span>}
              {isSet(f.key) && <span className="ml-2 text-xs text-green-300">✓ definido</span>}
            </span>
            <input
              type={f.secret ? 'password' : 'text'}
              value={values[f.key] ?? ''}
              placeholder={isSet(f.key) ? '(definido — em branco p/ manter)' : (f.placeholder ?? '')}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              className="rounded-lg border border-border bg-background px-2.5 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Button variant="default" onClick={() => void submit()} disabled={saving || !token}>
          {saving ? 'salvando…' : 'Salvar e iniciar'}
        </Button>
        {msg && <span className="text-sm text-muted">{msg}</span>}
      </div>
    </Card>
  )
}
