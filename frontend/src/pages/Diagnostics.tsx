/** Diagnóstico: salud de cada fuente y últimas ejecuciones. */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CollectionRun, SourceHealth, Stats } from '../api/types'
import { Layout } from '../components/Layout'
import { Loading, formatDateTime } from '../components/ui'
import { useApp } from '../state/AppContext'

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  sana: { text: 'Sana', className: 'ok' },
  degradada: { text: 'Con avisos', className: 'warn' },
  caida: { text: 'Caída', className: 'bad' },
  'sin-datos': { text: 'Sin datos aún', className: '' },
}

export function Diagnostics() {
  const { notify } = useApp()
  const [health, setHealth] = useState<SourceHealth[]>([])
  const [runs, setRuns] = useState<CollectionRun[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<number | 'all' | null>(null)

  const load = useCallback(async () => {
    try {
      const [h, r, s] = await Promise.all([
        api.sourcesHealth(7), api.runs(8), api.stats(),
      ])
      setHealth(h); setRuns(r); setStats(s)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo cargar el diagnóstico')
    } finally {
      setLoading(false)
    }
  }, [notify])

  useEffect(() => { load() }, [load])

  const run = async (columnistId?: number) => {
    setBusy(columnistId ?? 'all')
    try {
      await api.triggerRun(columnistId)
      notify('Recolección lanzada. Vuelve a mirar en un minuto.')
      window.setTimeout(load, 20000)
    } finally {
      setBusy(null)
    }
  }

  if (loading) return <Layout title="Fuentes"><Loading /></Layout>

  return (
    <Layout
      title="Fuentes"
      actions={
        <button className="btn small" onClick={() => run()} disabled={busy === 'all'}>
          {busy === 'all' ? 'Lanzando…' : '↻ Recolectar'}
        </button>
      }
    >
      {stats && (
        <div className="card">
          <div className="row" style={{ gap: '1.2rem' }}>
            <div>
              <div className="faint">Artículos</div>
              <strong className="mono">{stats.articles_total}</strong>
            </div>
            <div>
              <div className="faint">Sin leer</div>
              <strong className="mono">{stats.articles_unread}</strong>
            </div>
            <div>
              <div className="faint">Audios listos</div>
              <strong className="mono">{stats.audios_ready}</strong>
            </div>
            <div>
              <div className="faint">Audios con error</div>
              <strong className="mono" style={{ color: stats.audios_error ? 'var(--danger)' : undefined }}>
                {stats.audios_error}
              </strong>
            </div>
          </div>
          {stats.audios_error > 0 && (
            <button
              className="btn small"
              style={{ marginTop: '.8rem' }}
              onClick={() => api.generateMissingAudio().then(() => notify('Reintentando los audios pendientes'))}
            >
              Reintentar audios pendientes
            </button>
          )}
        </div>
      )}

      <div className="section-title">Salud de cada fuente (7 días)</div>

      {health.map((source) => {
        const badge = STATUS_LABEL[source.status] ?? STATUS_LABEL['sin-datos']
        return (
          <div className="card" key={source.columnist_id}>
            <div className="spread">
              <div>
                <strong>{source.name}</strong>
                <div className="faint">{source.outlet}</div>
              </div>
              <div className="row">
                {!source.active && <span className="pill">inactiva</span>}
                <span className={`pill ${badge.className}`}>{badge.text}</span>
              </div>
            </div>

            <div className="health-days" title="Un cuadro por ejecución, de la más antigua a la más reciente">
              {source.last_days.length === 0
                ? <span className="faint">sin ejecuciones registradas</span>
                : source.last_days.map((day, index) => (
                  <span
                    key={index}
                    className={day.status}
                    title={`${day.date} · ${day.status} · ${day.new} nuevos · ${day.ms} ms${day.error ? `\n${day.error}` : ''}`}
                  />
                ))}
            </div>

            <div className="faint" style={{ marginTop: '.5rem' }}>
              Último éxito: {formatDateTime(source.last_success_at)}
              {source.consecutive_failures > 0 &&
                ` · ${source.consecutive_failures} fallos seguidos`}
            </div>

            {source.last_error && <div className="error-text">{source.last_error}</div>}

            <button
              className="btn small"
              style={{ marginTop: '.7rem' }}
              onClick={() => run(source.columnist_id)}
              disabled={busy === source.columnist_id}
            >
              {busy === source.columnist_id ? 'Probando…' : 'Recolectar solo esta'}
            </button>
          </div>
        )
      })}

      <div className="section-title">Últimas ejecuciones</div>

      {runs.map((item) => (
        <div className="card" key={item.id}>
          <div className="spread">
            <div>
              <strong>{formatDateTime(item.started_at)}</strong>
              <div className="faint">
                {item.trigger === 'scheduled' ? 'programada' : 'manual'} ·{' '}
                {item.articles_new} nuevos ·{' '}
                {item.sources_total - item.sources_failed}/{item.sources_total} fuentes bien
              </div>
            </div>
            <span className={`pill ${item.status === 'ok' ? 'ok' : item.status === 'error' ? 'bad' : 'warn'}`}>
              {item.status}
            </span>
          </div>

          {item.source_runs.filter((s) => s.error_message).map((source) => (
            <div className="error-text" key={source.id}>
              {source.columnist_name}: {source.error_message}
            </div>
          ))}
        </div>
      ))}
    </Layout>
  )
}
