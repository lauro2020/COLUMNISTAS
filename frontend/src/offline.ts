/** Descarga del día para usar sin conexión.
 *
 * Cómo funciona:
 *   1. Se le pregunta al servidor qué recursos componen el día.
 *   2. Los JSON de los artículos se piden con `fetch` normal: el service
 *      worker los cachea al vuelo (estrategia "red primero, caché si falla").
 *   3. Los MP3 se le pasan al service worker, que los descarga enteros y los
 *      guarda para poder servir después peticiones parciales (saltos).
 */

import { api, withToken } from './api/client'

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // En desarrollo sin HTTPS puede fallar; la app funciona igual.
    })
  })
}

export async function cacheDayOffline(date?: string): Promise<{ count: number }> {
  const bundle = await api.offlineBundle(date)

  const articleUrls = bundle.resources.filter((url) => url.startsWith('/api/articles/'))
  const audioUrls = bundle.resources.filter((url) => url.includes('/api/audio/'))

  // Los artículos: basta con pedirlos para que el service worker los guarde.
  await Promise.all(articleUrls.map((url) =>
    fetch(url, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('columnistas.token') ?? ''}`,
      },
    }).catch(() => undefined)
  ))

  // Los audios: los descarga el service worker (con el token en la URL).
  const registration = await navigator.serviceWorker?.ready.catch(() => undefined)
  if (registration?.active && audioUrls.length > 0) {
    registration.active.postMessage({
      type: 'CACHE_AUDIO',
      urls: audioUrls.map((url) => withToken(url)),
    })
  }

  return { count: bundle.count }
}

export async function clearOffline() {
  const registration = await navigator.serviceWorker?.ready.catch(() => undefined)
  registration?.active?.postMessage({ type: 'CLEAR_OFFLINE' })
}
