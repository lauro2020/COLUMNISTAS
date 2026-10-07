/** El reproductor.
 *
 * Un único elemento <audio> vive aquí, fuera del árbol de páginas, para que
 * la reproducción no se corte al navegar. Se encarga de:
 *   · cola continua con los artículos de la bandeja del día
 *   · velocidad de 0.75× a 2×
 *   · saltos de ±15 segundos
 *   · reanudar donde te quedaste (posición guardada en el servidor)
 *   · controles en la pantalla de bloqueo (Media Session API)
 *   · sincronizar la posición cada pocos segundos, para poder seguir en otro
 *     dispositivo
 */

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react'
import { api, withToken } from '../api/client'
import type { ArticleListItem } from '../api/types'
import { useApp } from './AppContext'

const SKIP_SECONDS = 15
const SYNC_EVERY_MS = 8000

export interface PlayerState {
  current: ArticleListItem | null
  queue: ArticleListItem[]
  playing: boolean
  loading: boolean
  position: number
  duration: number
  rate: number
  error: string | null
  play: (article: ArticleListItem, queue?: ArticleListItem[]) => void
  toggle: () => void
  seek: (seconds: number) => void
  skip: (delta: number) => void
  setRate: (rate: number) => void
  next: () => void
  previous: () => void
  close: () => void
}

const Ctx = createContext<PlayerState | null>(null)

export function audioUrl(article: ArticleListItem): string | null {
  if (!article.audio_id || article.audio_status !== 'ready') return null
  return withToken(`/api/audio/${article.audio_id}/file`)
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const { prefs, savePrefs, notify } = useApp()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const lastSyncRef = useRef(0)

  const [current, setCurrent] = useState<ArticleListItem | null>(null)
  const [queue, setQueue] = useState<ArticleListItem[]>([])
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [position, setPosition] = useState(0)
  const [duration, setDuration] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [rate, setRateState] = useState(prefs.playback_rate || 1)

  // -- elemento <audio> ------------------------------------------------------
  if (audioRef.current === null && typeof Audio !== 'undefined') {
    audioRef.current = new Audio()
    audioRef.current.preload = 'metadata'
  }

  const syncProgress = useCallback((seconds: number, finished = false) => {
    if (!current) return
    api.saveProgress(current.id, {
      audio_position_seconds: seconds,
      mark_listened: finished,
    }).catch(() => { /* sin conexión: se reintenta en la siguiente sincronía */ })
  }, [current])

  const playNextRef = useRef<() => void>(() => {})

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const onTime = () => {
      setPosition(audio.currentTime)
      const now = Date.now()
      if (now - lastSyncRef.current > SYNC_EVERY_MS) {
        lastSyncRef.current = now
        syncProgress(audio.currentTime)
      }
    }
    const onMeta = () => { setDuration(audio.duration || 0); setLoading(false) }
    const onPlay = () => { setPlaying(true); setError(null) }
    const onPause = () => { setPlaying(false); syncProgress(audio.currentTime) }
    const onEnded = () => { syncProgress(audio.duration || 0, true); playNextRef.current() }
    const onError = () => {
      setLoading(false)
      setPlaying(false)
      setError('No se pudo reproducir el audio. Si estás sin conexión, descarga el día primero.')
    }
    const onWaiting = () => setLoading(true)
    const onPlaying = () => setLoading(false)

    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)
    audio.addEventListener('error', onError)
    audio.addEventListener('waiting', onWaiting)
    audio.addEventListener('playing', onPlaying)
    return () => {
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
      audio.removeEventListener('error', onError)
      audio.removeEventListener('waiting', onWaiting)
      audio.removeEventListener('playing', onPlaying)
    }
  }, [syncProgress])

  // -- acciones --------------------------------------------------------------
  const play = useCallback((article: ArticleListItem, newQueue?: ArticleListItem[]) => {
    const audio = audioRef.current
    if (!audio) return
    const url = audioUrl(article)
    if (!url) {
      notify(article.audio_status === 'error'
        ? 'El audio de este artículo falló. Puedes regenerarlo desde el artículo.'
        : 'El audio todavía se está generando.')
      return
    }

    if (newQueue) setQueue(newQueue.filter((a) => a.audio_status === 'ready'))
    setCurrent(article)
    setError(null)
    setLoading(true)
    audio.src = url
    audio.playbackRate = rate
    audio.currentTime = article.audio_position_seconds || 0
    audio.play().catch(() => setError('El navegador bloqueó la reproducción automática. Pulsa play.'))
  }, [notify, rate])

  const toggle = useCallback(() => {
    const audio = audioRef.current
    if (!audio || !current) return
    if (audio.paused) audio.play().catch(() => undefined)
    else audio.pause()
  }, [current])

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = Math.max(0, Math.min(seconds, audio.duration || seconds))
    setPosition(audio.currentTime)
  }, [])

  const skip = useCallback((delta: number) => {
    const audio = audioRef.current
    if (audio) seek(audio.currentTime + delta)
  }, [seek])

  const setRate = useCallback((value: number) => {
    setRateState(value)
    if (audioRef.current) audioRef.current.playbackRate = value
    savePrefs({ playback_rate: value })
  }, [savePrefs])

  const step = useCallback((delta: number) => {
    if (!current) return
    const index = queue.findIndex((a) => a.id === current.id)
    const target = queue[index + delta]
    if (target) play(target)
    else if (delta > 0) {
      setPlaying(false)
      notify('Terminaste la cola del día.')
    }
  }, [current, queue, play, notify])

  const next = useCallback(() => step(1), [step])
  const previous = useCallback(() => step(-1), [step])
  useEffect(() => { playNextRef.current = next }, [next])

  const close = useCallback(() => {
    const audio = audioRef.current
    if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load() }
    setCurrent(null)
    setPlaying(false)
    setPosition(0)
  }, [])

  // -- controles del sistema (pantalla de bloqueo, auriculares) --------------
  useEffect(() => {
    if (!('mediaSession' in navigator) || !current) return
    navigator.mediaSession.metadata = new MediaMetadata({
      title: current.title,
      artist: current.author || '',
      album: current.outlet || 'Columnistas',
      artwork: [
        { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
        { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
      ],
    })
    navigator.mediaSession.setActionHandler('play', () => toggle())
    navigator.mediaSession.setActionHandler('pause', () => toggle())
    navigator.mediaSession.setActionHandler('seekbackward', () => skip(-SKIP_SECONDS))
    navigator.mediaSession.setActionHandler('seekforward', () => skip(SKIP_SECONDS))
    navigator.mediaSession.setActionHandler('previoustrack', () => previous())
    navigator.mediaSession.setActionHandler('nexttrack', () => next())
    navigator.mediaSession.setActionHandler('seekto', (details) => {
      if (details.seekTime != null) seek(details.seekTime)
    })
  }, [current, toggle, skip, next, previous, seek])

  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    navigator.mediaSession.playbackState = playing ? 'playing' : 'paused'
    if (duration > 0 && Number.isFinite(duration)) {
      try {
        navigator.mediaSession.setPositionState({
          duration, position: Math.min(position, duration), playbackRate: rate,
        })
      } catch { /* algunos navegadores no lo soportan */ }
    }
  }, [playing, position, duration, rate])

  // Guarda la posición al cerrar la pestaña o mandar la app a segundo plano.
  useEffect(() => {
    const onHide = () => {
      const audio = audioRef.current
      if (audio && current && !audio.paused) syncProgress(audio.currentTime)
    }
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('pagehide', onHide)
    return () => {
      document.removeEventListener('visibilitychange', onHide)
      window.removeEventListener('pagehide', onHide)
    }
  }, [current, syncProgress])

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate
  }, [rate, current])

  const value = useMemo<PlayerState>(() => ({
    current, queue, playing, loading, position, duration, rate, error,
    play, toggle, seek, skip, setRate, next, previous, close,
  }), [current, queue, playing, loading, position, duration, rate, error,
    play, toggle, seek, skip, setRate, next, previous, close])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function usePlayer(): PlayerState {
  const value = useContext(Ctx)
  if (!value) throw new Error('usePlayer debe usarse dentro de <PlayerProvider>')
  return value
}
