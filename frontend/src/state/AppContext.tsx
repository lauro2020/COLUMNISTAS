/** Sesión, preferencias y avisos. Es el estado "global" de la app. */

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from 'react'
import { api, getToken, setToken } from '../api/client'
import type { Preferences } from '../api/types'

const DEFAULT_PREFS: Preferences = {
  collect_hour: 6,
  collect_minute: 0,
  timezone: 'America/Mexico_City',
  tts_provider: 'openai',
  tts_voice: 'onyx',
  auto_generate_audio: true,
  playback_rate: 1,
  retention_months: 12,
  theme: 'system',
  font_size: 18,
}

interface AppState {
  authenticated: boolean
  login: (password: string) => Promise<void>
  logout: () => void
  prefs: Preferences
  savePrefs: (patch: Partial<Preferences>) => Promise<void>
  toast: string | null
  notify: (message: string) => void
}

const Ctx = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(() => Boolean(getToken()))
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS)
  const [toast, setToast] = useState<string | null>(null)

  const notify = useCallback((message: string) => {
    setToast(message)
    window.setTimeout(() => setToast((current) => (current === message ? null : current)), 4000)
  }, [])

  // Si el token caduca, el cliente avisa y volvemos a la pantalla de entrada.
  useEffect(() => {
    const onLogout = () => setAuthenticated(false)
    window.addEventListener('columnistas:logout', onLogout)
    return () => window.removeEventListener('columnistas:logout', onLogout)
  }, [])

  useEffect(() => {
    if (!authenticated) return
    api.preferences()
      .then(setPrefs)
      .catch(() => { /* sin conexión: se usan los valores por defecto */ })
  }, [authenticated])

  // Tema claro / oscuro y tamaño de letra
  useEffect(() => {
    const root = document.documentElement
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = prefs.theme === 'dark' || (prefs.theme === 'system' && media.matches)
      root.dataset.theme = dark ? 'dark' : 'light'
      const color = dark ? '#111214' : '#faf9f7'
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', color)
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [prefs.theme])

  useEffect(() => {
    document.documentElement.style.setProperty('--reader-size', `${prefs.font_size}px`)
  }, [prefs.font_size])

  const login = useCallback(async (password: string) => {
    const { token } = await api.login(password)
    setToken(token)
    setAuthenticated(true)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setAuthenticated(false)
  }, [])

  const savePrefs = useCallback(async (patch: Partial<Preferences>) => {
    setPrefs((current) => ({ ...current, ...patch }))  // respuesta inmediata
    try {
      const saved = await api.savePreferences(patch)
      setPrefs(saved)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo guardar')
    }
  }, [notify])

  const value = useMemo<AppState>(
    () => ({ authenticated, login, logout, prefs, savePrefs, toast, notify }),
    [authenticated, login, logout, prefs, savePrefs, toast, notify],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppState {
  const value = useContext(Ctx)
  if (!value) throw new Error('useApp debe usarse dentro de <AppProvider>')
  return value
}
