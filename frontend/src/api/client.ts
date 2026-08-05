/** Cliente de la API. Guarda el token de sesión en el navegador. */

import type {
  ArticleDetail, ArticleListItem, CollectionRun, Columnist, Credential,
  Inbox, Preferences, SearchResult, SourceHealth, Stats, TtsProvider,
} from './types'

const TOKEN_KEY = 'columnistas.token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }
  if (options.body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(path, { ...options, headers })

  // Un 401 al entrar significa "contraseña incorrecta", no "sesión caducada":
  // ahí todavía no hay sesión que caducar. Se deja pasar para que el mensaje
  // que llega del servidor sea el que se vea.
  const esInicioDeSesion = path.startsWith('/api/auth/login')

  if (response.status === 401 && !esInicioDeSesion) {
    setToken(null)
    window.dispatchEvent(new CustomEvent('columnistas:logout'))
    throw new ApiError(401, 'La sesión caducó. Vuelve a entrar con tu contraseña.')
  }
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch { /* respuesta sin JSON */ }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

/** Añade el token a una URL: lo necesita <audio>, que no manda cabeceras. */
export function withToken(url: string): string {
  const token = getToken()
  if (!token) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}

export const api = {
  // -- sesión ---------------------------------------------------------------
  login: (password: string) =>
    request<{ token: string; expires_days: number }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  // -- bandeja y artículos ---------------------------------------------------
  inbox: (date?: string) =>
    request<Inbox>(`/api/articles/inbox${date ? `?date=${date}` : ''}`),

  article: (id: number) => request<ArticleDetail>(`/api/articles/${id}`),

  search: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value))
    })
    return request<SearchResult>(`/api/articles?${query.toString()}`)
  },

  setState: (id: number, patch: Partial<Pick<ArticleListItem,
    'is_read' | 'is_listened' | 'is_archived' | 'is_favorite'>>) =>
    request<ArticleListItem>(`/api/articles/${id}/state`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  saveProgress: (id: number, body: {
    audio_position_seconds?: number
    reading_paragraph_index?: number
    mark_listened?: boolean
  }) =>
    request<ArticleListItem>(`/api/articles/${id}/progress`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  markAllRead: (date?: string) =>
    request<{ updated: number }>(
      `/api/articles/mark-all-read${date ? `?date=${date}` : ''}`, { method: 'POST' }),

  offlineBundle: (date?: string) =>
    request<{ date: string; count: number; resources: string[] }>(
      `/api/articles/offline/bundle${date ? `?date=${date}` : ''}`),

  // -- audio -----------------------------------------------------------------
  regenerateAudio: (articleId: number, voice?: string, provider?: string) => {
    const query = new URLSearchParams()
    if (voice) query.set('voice', voice)
    if (provider) query.set('provider', provider)
    return request<{ queued: boolean }>(
      `/api/audio/article/${articleId}/regenerate?${query}`, { method: 'POST' })
  },

  generateMissingAudio: () =>
    request<{ queued: boolean }>('/api/audio/generate-missing', { method: 'POST' }),

  // -- columnistas -----------------------------------------------------------
  columnists: () => request<Columnist[]>('/api/columnists'),

  createColumnist: (body: Partial<Columnist>) =>
    request<Columnist>('/api/columnists', { method: 'POST', body: JSON.stringify(body) }),

  updateColumnist: (id: number, body: Partial<Columnist>) =>
    request<Columnist>(`/api/columnists/${id}`, {
      method: 'PATCH', body: JSON.stringify(body),
    }),

  deleteColumnist: (id: number) =>
    request<void>(`/api/columnists/${id}`, { method: 'DELETE' }),

  testColumnist: (id: number) =>
    request<Record<string, unknown>>(`/api/columnists/${id}/test`, { method: 'POST' }),

  extractors: () => request<string[]>('/api/columnists/extractors'),

  // -- configuración ---------------------------------------------------------
  preferences: () => request<Preferences>('/api/settings/preferences'),

  savePreferences: (body: Partial<Preferences>) =>
    request<Preferences>('/api/settings/preferences', {
      method: 'PATCH', body: JSON.stringify(body),
    }),

  ttsProviders: () => request<TtsProvider[]>('/api/settings/tts-providers'),

  credentials: () => request<Credential[]>('/api/settings/credentials'),

  saveCredential: (body: {
    outlet: string; kind: string; label?: string
    cookies_raw?: string; username?: string; password?: string
  }) =>
    request<Credential>('/api/settings/credentials', {
      method: 'PUT', body: JSON.stringify(body),
    }),

  deleteCredential: (id: number) =>
    request<void>(`/api/settings/credentials/${id}`, { method: 'DELETE' }),

  // -- diagnóstico -----------------------------------------------------------
  sourcesHealth: (days = 7) =>
    request<SourceHealth[]>(`/api/health/sources?days=${days}`),

  runs: (limit = 15) => request<CollectionRun[]>(`/api/health/runs?limit=${limit}`),

  triggerRun: (columnistId?: number) =>
    request<{ queued: boolean }>(
      `/api/health/runs${columnistId ? `?columnist_id=${columnistId}` : ''}`,
      { method: 'POST' }),

  stats: () => request<Stats>('/api/health/stats'),
}
