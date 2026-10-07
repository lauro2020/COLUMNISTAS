/** Barra del reproductor, siempre visible mientras suene algo. */

import { useNavigate } from 'react-router-dom'
import { usePlayer } from '../state/PlayerContext'
import { formatTime, Spinner } from './ui'

const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2]

export function PlayerBar() {
  const player = usePlayer()
  const navigate = useNavigate()

  if (!player.current) return null

  const nextRate = () => {
    const index = RATES.indexOf(player.rate)
    player.setRate(RATES[(index + 1) % RATES.length] ?? 1)
  }

  return (
    <div className="player">
      <div className="player-inner">
        <div className="spread">
          <div
            className="player-title"
            onClick={() => navigate(`/articulo/${player.current!.id}`)}
            style={{ cursor: 'pointer', flex: 1 }}
            title="Abrir el artículo"
          >
            {player.current.title}
          </div>
          <button
            className="btn ghost small"
            onClick={player.close}
            title="Cerrar el reproductor"
          >
            ✕
          </button>
        </div>

        {player.error && (
          <div className="faint" style={{ color: 'var(--danger)' }}>{player.error}</div>
        )}

        <input
          className="bar"
          type="range"
          min={0}
          max={player.duration || 0}
          step={1}
          value={Math.min(player.position, player.duration || 0)}
          onChange={(event) => player.seek(Number(event.target.value))}
          aria-label="Posición"
        />

        <div className="times mono">
          <span>{formatTime(player.position)}</span>
          <span>-{formatTime(Math.max(0, (player.duration || 0) - player.position))}</span>
        </div>

        <div className="player-controls">
          <button onClick={player.previous} title="Anterior de la cola">⏮</button>
          <button onClick={() => player.skip(-15)} title="Atrás 15 segundos">↺15</button>

          <button className="main" onClick={player.toggle} title={player.playing ? 'Pausa' : 'Reproducir'}>
            {player.loading ? <Spinner /> : player.playing ? '❚❚' : '▶'}
          </button>

          <button onClick={() => player.skip(15)} title="Adelante 15 segundos">15↻</button>
          <button onClick={player.next} title="Siguiente de la cola">⏭</button>

          <button className="rate-btn" onClick={nextRate} title="Velocidad de reproducción">
            {player.rate}×
          </button>
        </div>
      </div>
    </div>
  )
}
