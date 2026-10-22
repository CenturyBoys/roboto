import { useEffect, useState } from 'react'

// O browser dispara `beforeinstallprompt` quando o PWA é instalável; guardamos o evento p/ o botão.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
}

export function useInstallPrompt(): [boolean, () => void] {
  const [evt, setEvt] = useState<BeforeInstallPromptEvent | null>(null)
  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      setEvt(e as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])
  const install = () => {
    if (evt) {
      void evt.prompt()
      setEvt(null)
    }
  }
  return [evt !== null, install]
}
