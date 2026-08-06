/** Pantalla de inicio: todos los columnistas, uno por fila.
 *
 * De un vistazo se ve quién publicó hoy, quién publicó hace poco y quién lleva
 * tiempo callado. El último artículo solo aparece si es de los últimos días
 * (15 por defecto); si es más viejo, en su lugar va la leyenda correspondiente.
 * Cada fila lleva plegado su histórico completo, del más reciente al más
 * antiguo.
 */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ArticleListItem, Overview } from '../api/types'
import { ColumnistRow } from '../components/ColumnistRow'
import { Layout } from '../components/Layout'
import { Empty, Loading, formatDateTime } from '../components/ui'
import { cacheDayOffline, offlineSupported, OFFLINE_UNSUPPORTED_REASON } from '../offline'
import { useApp } from '../state/AppContext'
import { usePlayer } from '../state/PlayerContext'

export function Inbox() {
  const { notify } = useApp()
  const player = usePlayer()
  const [data, setData] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true)
    try {
      setData(await api.overview())
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo cargar la lista')
    } finally {
      setLoading(false)
    }
  }, [notify])

  useEffect(() => { load() }, [load])

  // Mientras haya audios generándose, se refresca solo cada 20 segundos.
  useEffect(() => {
    const pendiente = data?.columnists.some(
      (c) => c.latest?.audio_status === 'pending' || c.latest?.audio_status === 'processing')
    if (!pendiente) return
    const timer = window.setInterval(() => load(false), 20000)
    return () => window.clearInterval(timer)
  }, [data, load])

  const recientes: ArticleListItem[] =
    data?.columnists.map((c) => c.latest).filter((a): a is ArticleListItem => a !== null) ?? []
  const reproducibles = recientes.filter((a) => a.audio_status === 'ready')
  const deHoy = data?.columnists.filter((c) => c.published_today) ?? []

  const collectNow = async () => {
    setBusy('collect')
    try {
      await api.triggerRun()
      notify('Recolección lanzada. Con todas las fuentes tarda unos diez minutos.')
      window.setTimeout(() => load(false), 20000)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo lanzar la recolección')
    } finally {
      setBusy(null)
    }
  }

  const download = async () => {
    setBusy('offline')
    try {
      const result = await cacheDayOffline()
      notify(`Descargados ${result.count} artículos para leer y escuchar sin conexión.`)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo descargar el día')
    } finally {
      setBusy(null)
    }
  }

  const markAll = async () => {
    await api.markAllRead()
    load(false)
  }

  if (loading) return <Layout title="Columnistas"><Loading /></Layout>

  if (!data || data.columnists.length === 0) {
    return (
      <Layout title="Columnistas">
        <Empty
          glyph="📰"
          title="No hay columnistas activos"
          hint="Añádelos en Ajustes › Columnistas."
        />
      </Layout>
    )
  }

  return (
    <Layout title="Columnistas">
      <div className="card">
        <div className="spread">
          <div>
            <strong>{data.published_today}</strong>
            {data.published_today === 1 ? ' publicó hoy' : ' publicaron hoy'}
            <span className="muted">
              {' '}· {data.with_recent} de {data.total_columnists} con algo reciente
            </span>
            <div className="faint">
              Última recolección: {formatDateTime(data.last_run_at)}
            </div>
          </div>
          <button
            className="btn primary small"
            disabled={reproducibles.length === 0}
            onClick={() => player.play(reproducibles[0], reproducibles)}
            title="Escuchar la última columna de cada uno, una tras otra"
          >
            ▶ Escuchar todo
          </button>
        </div>

        <div className="row" style={{ marginTop: '.8rem' }}>
          {offlineSupported() ? (
            <button className="btn small" onClick={download} disabled={busy === 'offline'}>
              {busy === 'offline' ? 'Descargando…' : '⤓ Descargar para sin conexión'}
            </button>
          ) : (
            <button
              className="btn small"
              onClick={() => notify(OFFLINE_UNSUPPORTED_REASON)}
              title={OFFLINE_UNSUPPORTED_REASON}
            >
              ⤓ Sin conexión no disponible
            </button>
          )}
          <button className="btn small" onClick={markAll}>Marcar hoy como leído</button>
          <button className="btn small ghost" onClick={collectNow} disabled={busy === 'collect'}>
            {busy === 'collect' ? 'Buscando…' : '↻ Buscar ahora'}
          </button>
        </div>
      </div>

      {deHoy.length > 0 && <div className="section-title">Publicaron hoy</div>}

      {data.columnists.map((fila, index) => (
        <div key={fila.columnist_id}>
          {/* Separador entre los que publicaron hoy y el resto */}
          {index === deHoy.length && deHoy.length > 0 && (
            <div className="section-title">El resto</div>
          )}
          <ColumnistRow fila={fila} cola={reproducibles} />
        </div>
      ))}

      <p className="faint" style={{ marginTop: '1.2rem', textAlign: 'center' }}>
        Se muestra el último artículo de cada columnista publicado en los
        últimos {data.recent_days} días.
      </p>
    </Layout>
  )
}
