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

/** ¿Puede este navegador guardar cosas para usarlas sin conexión?
 *
 * El service worker solo existe en un «contexto seguro»: HTTPS, o localhost.
 * Si abres la app desde el teléfono por la IP de tu computadora
 * (http://192.168.x.x:8080) el navegador lo desactiva, y con él se van la
 * descarga para uso sin conexión, la instalación en la pantalla de inicio y
 * los controles en la pantalla de bloqueo.
 */
export function offlineSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    window.isSecureContext
  )
}

export const OFFLINE_UNSUPPORTED_REASON =
  'Para descargar y escuchar sin conexión, la app tiene que abrirse por HTTPS ' +
  '(o en localhost). Por IP de red local el navegador lo desactiva.'

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // En desarrollo sin HTTPS puede fallar; la app funciona igual.
    })
  })
}

export async function cacheDayOffline(date?: string): Promise<{ count: number }> {
  if (!offlineSupported()) throw new Error(OFFLINE_UNSUPPORTED_REASON)

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
