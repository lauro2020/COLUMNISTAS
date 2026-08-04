import { useNavigate } from 'react-router-dom'
import type { ArticleListItem } from '../api/types'
import { usePlayer } from '../state/PlayerContext'
import { formatDate, formatTime } from './ui'

interface Props {
  article: ArticleListItem
  queue?: ArticleListItem[]
  showAuthor?: boolean
}

export function ArticleCard({ article, queue, showAuthor }: Props) {
  const navigate = useNavigate()
  const player = usePlayer()

  const audioReady = article.audio_status === 'ready'
  const isCurrent = player.current?.id === article.id

  const audioLabel = () => {
    if (audioReady) return formatTime(article.audio_duration || 0)
    if (article.audio_status === 'processing') return 'generando audio…'
    if (article.audio_status === 'error') return 'audio falló'
    return 'audio en cola'
  }

  return (
    <div
      className={`article-card${article.is_read ? ' read' : ''}`}
      onClick={() => navigate(`/articulo/${article.id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter') navigate(`/articulo/${article.id}`)
      }}
    >
      <h3>{article.title}</h3>
      {article.summary && <p>{article.summary}</p>}

      <div className="article-meta">
        {showAuthor && article.author && <span>{article.author}</span>}
        <span>{article.outlet}</span>
        <span>·</span>
        <span>{formatDate(article.published_at)}</span>
        <span>·</span>
        <span>{article.reading_minutes} min de lectura</span>
        {article.is_favorite && <span className="pill accent">★</span>}
        {article.is_paywalled && <span className="pill warn">de pago</span>}
        {article.is_listened && <span className="pill ok">escuchado</span>}

        <span className={`pill${audioReady ? '' : ' warn'}`}>{audioLabel()}</span>

        <button
          className="play-inline"
          title={audioReady ? 'Escuchar' : 'El audio todavía no está listo'}
          disabled={!audioReady}
          onClick={(event) => {
            event.stopPropagation()
            player.play(article, queue)
          }}
        >
          {isCurrent && player.playing ? '❚❚' : '▶'}
        </button>
      </div>
    </div>
  )
}
