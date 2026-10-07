/* Service worker de Columnistas.
 *
 * Hace tres cosas:
 *  1. Sirve la app aunque no haya conexión (cachea el "esqueleto" y los assets).
 *  2. Guarda las respuestas de la API para poder leer los artículos del día sin red.
 *  3. Guarda los MP3 completos y responde peticiones parciales (Range) desde la
 *     caché, que es lo que permite reproducir y saltar sin conexión.
 */

const VERSION = 'v1';
const SHELL_CACHE = `shell-${VERSION}`;
const ASSET_CACHE = `assets-${VERSION}`;
const API_CACHE = `api-${VERSION}`;
const AUDIO_CACHE = `audio-${VERSION}`;

const SHELL_URLS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png',
];

// ---------------------------------------------------------------------------
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => !key.endsWith(VERSION))
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// ---------------------------------------------------------------------------
// El token de sesión viaja como ?token=... en las peticiones del <audio>.
// Se quita para que la clave de caché sea siempre la misma.
function cacheKey(url) {
  const clean = new URL(url);
  clean.searchParams.delete('token');
  return clean.toString();
}

async function networkFirst(request, cacheName) {
  const key = cacheKey(request.url);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(key, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(key);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) {
    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
  }
  return response;
}

// Devuelve un trozo del MP3 guardado, como haría el servidor.
async function sliceFromCache(cached, rangeHeader) {
  const buffer = await cached.arrayBuffer();
  const total = buffer.byteLength;
  const match = /bytes=(\d*)-(\d*)/.exec(rangeHeader || '');
  let start = 0;
  let end = total - 1;
  if (match) {
    if (match[1]) start = parseInt(match[1], 10);
    if (match[2]) end = parseInt(match[2], 10);
  }
  end = Math.min(end, total - 1);
  if (start > end) start = 0;

  return new Response(buffer.slice(start, end + 1), {
    status: 206,
    statusText: 'Partial Content',
    headers: {
      'Content-Type': 'audio/mpeg',
      'Content-Length': String(end - start + 1),
      'Content-Range': `bytes ${start}-${end}/${total}`,
      'Accept-Ranges': 'bytes',
    },
  });
}

async function handleAudio(request) {
  const key = cacheKey(request.url);
  const cache = await caches.open(AUDIO_CACHE);
  const cached = await cache.match(key);

  if (cached) {
    const range = request.headers.get('range');
    return range ? sliceFromCache(cached.clone(), range) : cached.clone();
  }
  return fetch(request);
}

// ---------------------------------------------------------------------------
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/api/audio/') && url.pathname.endsWith('/file')) {
    event.respondWith(handleAudio(request));
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, API_CACHE));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/index.html'))
    );
    return;
  }

  event.respondWith(cacheFirst(request, ASSET_CACHE));
});

// ---------------------------------------------------------------------------
// La app pide explícitamente "descargar el día".
self.addEventListener('message', (event) => {
  const data = event.data || {};

  if (data.type === 'CACHE_AUDIO' && Array.isArray(data.urls)) {
    event.waitUntil((async () => {
      const cache = await caches.open(AUDIO_CACHE);
      let saved = 0;
      for (const url of data.urls) {
        try {
          // Sin cabecera Range: se guarda el archivo entero.
          const response = await fetch(url, { cache: 'no-store' });
          if (response.ok) {
            await cache.put(cacheKey(url), response.clone());
            saved += 1;
          }
        } catch (_) { /* si falla uno, seguimos con los demás */ }
      }
      const clients = await self.clients.matchAll();
      clients.forEach((client) => client.postMessage({
        type: 'CACHE_AUDIO_DONE', saved, total: data.urls.length,
      }));
    })());
  }

  if (data.type === 'CLEAR_OFFLINE') {
    event.waitUntil(Promise.all([
      caches.delete(AUDIO_CACHE),
      caches.delete(API_CACHE),
    ]));
  }

  if (data.type === 'SKIP_WAITING') self.skipWaiting();
});
