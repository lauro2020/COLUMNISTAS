/** Una fila de la pantalla de inicio: un columnista de un vistazo.
 *
 * La idea es poder recorrer la lista casi a renglón seguido y ver enseguida
 * quién publicó hoy, quién publicó hace poco y quién lleva tiempo callado.
 * El histórico completo queda plegado hasta que se pide.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ArticleListItem, ColumnistOverview } from '../api/types'
import { usePlayer } from '../state/PlayerContext'
import { Spinner, formatDate, formatTime } from './ui'

interface Props {
  fila: ColumnistOverview
  /** Los últimos artículos de todos, para la cola de reproducción continua. */
  cola: ArticleListItem[]
}

function antiguedad(dias: number | null): string {
  if (dias === null) return 'nunca'
  if (dias === 0) return 'hoy'
  if (dias === 1) return 'ayer'
  if (dias < 30) return `hace ${dias} días`
  if (dias < 60) return 'hace un mes'
  if (dias < 365) return `hace ${Math.round(dias / 30)} meses`
  return 'hace más de un año'
}

function Historicos({ fila, abierto, alternar }: {
  fila: ColumnistOverview
  abierto: boolean
  alternar: () => void
}) {
  return (
    <button className="col-historico-tab" onClick={alternar}>
      <span className={`col-flecha${abierto ? ' abierta' : ''}`}>›</span>
      históricos
      {fila.total_articles > 0 && <span className="faint"> ({fila.total_articles})</span>}
    </button>
  )
}


export function ColumnistRow({ fila, cola }: Props) {
  const navigate = useNavigate()
  const player = usePlayer()
  const [abierto, setAbierto] = useState(false)
  const [historico, setHistorico] = useState<ArticleListItem[] | null>(null)
  const [cargando, setCargando] = useState(false)

  const ultimo = fila.latest

  const alternarHistorico = async () => {
    const abriendo = !abierto
    setAbierto(abriendo)
    if (!abriendo || historico !== null) return
    setCargando(true)
    try {
      const resultado = await api.columnistArticles(fila.columnist_id)
      setHistorico(resultado.items)
    } catch {
      setHistorico([])
    } finally {
      setCargando(false)
    }
  }

  const reproducible = ultimo?.audio_status === 'ready'
  const sonando = player.current?.id === ultimo?.id

  return (
    <div className={`col-row${fila.published_today ? ' hoy' : ''}${ultimo ? '' : ' callado'}`}>
      {/* Cabecera: quién es */}
      <div className="col-head">
        <div className="col-quien">
          <span className="col-nombre">{fila.name}</span>
          <span className="col-medio">{fila.outlet}</span>
        </div>
        {fila.published_today && <span className="pill accent">hoy</span>}
        {fila.consecutive_failures > 0 && (
          <span
            className="pill bad"
            title={fila.last_error ?? 'La fuente está fallando'}
          >
            fuente con error
          </span>
        )}
      </div>

      {/* El último artículo, o la leyenda de que no hay nada reciente */}
      {ultimo ? (
        <div className="col-ultimo">
          <button
            className="col-titulo"
            onClick={() => navigate(`/articulo/${ultimo.id}`)}
            title="Abrir el artículo"
          >
            {ultimo.is_read ? null : <span className="col-punto" aria-label="sin leer" />}
            {ultimo.title}
          </button>

          <div className="col-meta">
            <span className="col-fecha">{formatDate(ultimo.published_at)}</span>
            <span>·</span>
            <span>{ultimo.reading_minutes} min</span>
            {ultimo.is_paywalled && <span className="pill warn">de pago</span>}
            {reproducible && <span className="mono">{formatTime(ultimo.audio_duration || 0)}</span>}

            <span className="col-acciones">
              <Historicos fila={fila} abierto={abierto} alternar={alternarHistorico} />
              <button
                className="play-inline"
                disabled={!reproducible}
                title={reproducible ? 'Escuchar' : 'El audio todavía no está listo'}
                onClick={() => ultimo && player.play(ultimo, cola)}
              >
                {sonando && player.playing ? '❚❚' : '▶'}
              </button>
            </span>
          </div>
        </div>
      ) : (
        <div className="col-meta">
          <span className="col-sin-reciente">
            Sin artículos recientes
            {fila.last_published_at && ` · el último, ${antiguedad(fila.days_since_last)}`}
          </span>
          <span className="col-acciones">
            <Historicos fila={fila} abierto={abierto} alternar={alternarHistorico} />
          </span>
        </div>
      )}

      {abierto && (
        <div className="col-historico">
          {cargando ? (
            <div className="row" style={{ padding: '.4rem 0' }}>
              <Spinner /> <span className="faint">cargando…</span>
            </div>
          ) : !historico || historico.length === 0 ? (
            <div className="faint" style={{ padding: '.3rem 0' }}>
              Todavía no se ha recopilado nada de este columnista.
            </div>
          ) : (
            <ol className="col-lista">
              {historico.map((art) => (
                <li key={art.id}>
                  <button
                    className={`col-item${art.is_read ? ' leido' : ''}`}
                    onClick={() => navigate(`/articulo/${art.id}`)}
                  >
                    <span className="col-item-fecha mono">
                      {formatDate(art.published_at, { day: '2-digit', month: '2-digit', year: '2-digit' })}
                    </span>
                    <span className="col-item-titulo">{art.title}</span>
                  </button>
                  <button
                    className="play-inline"
                    disabled={art.audio_status !== 'ready'}
                    title={art.audio_status === 'ready' ? 'Escuchar' : 'Sin audio'}
                    onClick={() => player.play(art, historico)}
                  >
                    ▶
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}
