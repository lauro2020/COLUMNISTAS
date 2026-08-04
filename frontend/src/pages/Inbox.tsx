/** Bandeja del día: pantalla de inicio. */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ArticleListItem, Inbox as InboxData } from '../api/types'
import { ArticleCard } from '../components/ArticleCard'
import { Layout } from '../components/Layout'
import { Empty, Loading, formatDate, formatDateTime, todayISO } from '../components/ui'
import { useApp } from '../state/AppContext'
import { usePlayer } from '../state/PlayerContext'
import { cacheDayOffline } from '../offline'

export function Inbox() {
  const { notify } = useApp()
  const player = usePlayer()
  const [date, setDate] = useState(todayISO())
  const [data, setData] = useState<InboxData | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true)
    try {
      setData(await api.inbox(date))
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo cargar la bandeja')
    } finally {
      setLoading(false)
    }
  }, [date, notify])

  useEffect(() => { load() }, [load])

  // Mientras haya audios generándose, se refresca solo cada 20 segundos.
  useEffect(() => {
    const pending = data?.groups.some((group) =>
      group.articles.some((a) => a.audio_status === 'pending' || a.audio_status === 'processing'))
    if (!pending) return
    const timer = window.setInterval(() => load(false), 20000)
    return () => window.clearInterval(timer)
  }, [data, load])

  const allArticles: ArticleListItem[] =
    data?.groups.flatMap((group) => group.articles) ?? []
  const playable = allArticles.filter((a) => a.audio_status === 'ready')

  const shiftDay = (delta: number) => {
    const next = new Date(`${date}T12:00:00`)
    next.setDate(next.getDate() + delta)
    setDate(next.toISOString().slice(0, 10))
  }

  const collectNow = async () => {
    setBusy('collect')
    try {
      await api.triggerRun()
      notify('Recolección lanzada. Tarda uno o dos minutos.')
      window.setTimeout(() => load(false), 15000)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo lanzar la recolección')
    } finally {
      setBusy(null)
    }
  }

  const download = async () => {
    setBusy('offline')
    try {
      const result = await cacheDayOffline(date)
      notify(`Descargados ${result.count} artículos para leer y escuchar sin conexión.`)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo descargar el día')
    } finally {
      setBusy(null)
    }
  }

  const markAll = async () => {
    await api.markAllRead(date)
    load(false)
  }

  return (
    <Layout
      title={date === todayISO() ? 'Hoy' : formatDate(`${date}T12:00:00`, {
        weekday: 'long', day: 'numeric', month: 'long',
      })}
      actions={
        <div className="row">
          <button className="btn ghost small" onClick={() => shiftDay(-1)} title="Día anterior">‹</button>
          <button
            className="btn ghost small"
            onClick={() => shiftDay(1)}
            disabled={date >= todayISO()}
            title="Día siguiente"
          >›</button>
        </div>
      }
    >
      {loading ? <Loading /> : !data || data.total === 0 ? (
        <Empty
          glyph="☕"
          title="No hay columnas para este día"
          hint={
            <>
              La recolección corre automáticamente cada mañana.
              <div style={{ marginTop: '.8rem' }}>
                <button className="btn" onClick={collectNow} disabled={busy === 'collect'}>
                  {busy === 'collect' ? 'Buscando…' : 'Buscar ahora'}
                </button>
              </div>
            </>
          }
        />
      ) : (
        <>
          <div className="card">
            <div className="spread">
              <div>
                <strong>{data.total}</strong> {data.total === 1 ? 'columna' : 'columnas'}
                {data.unread > 0 && <span className="muted"> · {data.unread} sin leer</span>}
                <div className="faint">
                  Última recolección: {formatDateTime(data.last_run_at)}
                </div>
              </div>
              <button
                className="btn primary small"
                disabled={playable.length === 0}
                onClick={() => player.play(playable[0], playable)}
                title="Escuchar todas, una tras otra"
              >
                ▶ Escuchar todo
              </button>
            </div>

            <div className="row" style={{ marginTop: '.8rem' }}>
              <button className="btn small" onClick={download} disabled={busy === 'offline'}>
                {busy === 'offline' ? 'Descargando…' : '⤓ Descargar para sin conexión'}
              </button>
              <button className="btn small" onClick={markAll}>Marcar todo como leído</button>
              <button className="btn small ghost" onClick={collectNow} disabled={busy === 'collect'}>
                {busy === 'collect' ? 'Buscando…' : '↻ Buscar ahora'}
              </button>
            </div>
          </div>

          {data.groups.map((group) => (
            <section key={group.columnist_id}>
              <div className="section-title">
                {group.columnist_name} · {group.outlet}
              </div>
              {group.articles.map((article) => (
                <ArticleCard key={article.id} article={article} queue={playable} />
              ))}
            </section>
          ))}
        </>
      )}
    </Layout>
  )
}
