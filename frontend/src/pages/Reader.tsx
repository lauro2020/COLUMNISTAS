/** Modo lectura.
 *
 * El texto y el audio están sincronizados: mientras suena, el párrafo que se
 * está leyendo queda resaltado; si tocas un párrafo, el audio salta ahí. Así
 * puedes pasar de leer a escuchar (y al revés) sin perder el punto.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ArticleDetail } from '../api/types'
import { Layout } from '../components/Layout'
import { Empty, Loading, formatDate } from '../components/ui'
import { useApp } from '../state/AppContext'
import { usePlayer } from '../state/PlayerContext'

export function Reader() {
  const { id } = useParams<{ id: string }>()
  const articleId = Number(id)
  const navigate = useNavigate()
  const { notify, prefs, savePrefs } = useApp()
  const player = usePlayer()

  const [article, setArticle] = useState<ArticleDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const paragraphRefs = useRef<(HTMLElement | null)[]>([])
  const savedIndexRef = useRef(-1)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.article(articleId)
      setArticle(data)
      if (!data.is_read) {
        api.setState(articleId, { is_read: true }).catch(() => undefined)
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo abrir el artículo')
    } finally {
      setLoading(false)
    }
  }, [articleId, notify])

  useEffect(() => { load() }, [load])

  // Mientras el audio se genera, se comprueba cada 15 s si ya está listo.
  useEffect(() => {
    if (!article) return
    if (article.audio_status === 'ready' || article.audio_status === 'error') return
    const timer = window.setInterval(() => {
      api.article(articleId).then(setArticle).catch(() => undefined)
    }, 15000)
    return () => window.clearInterval(timer)
  }, [article, articleId])

  const isPlayingThis = player.current?.id === articleId

  // Párrafo que corresponde al segundo actual del audio
  const activeIndex = useMemo(() => {
    if (!isPlayingThis || !article?.audio?.marks?.length) return -1
    const mark = article.audio.marks.find(
      (m) => player.position >= m.start && player.position < m.end)
    return mark ? mark.paragraph_index : -1
  }, [isPlayingThis, article, player.position])

  // Sigue el párrafo activo con un desplazamiento suave
  useEffect(() => {
    if (activeIndex < 0) return
    const node = paragraphRefs.current[activeIndex]
    if (!node) return
    const rect = node.getBoundingClientRect()
    if (rect.top < 80 || rect.bottom > window.innerHeight - 220) {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [activeIndex])

  // Guarda por dónde vas leyendo (se sincroniza entre dispositivos)
  useEffect(() => {
    if (!article || isPlayingThis) return
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .map((entry) => Number((entry.target as HTMLElement).dataset.index))
        .sort((a, b) => a - b)
      const first = visible[0]
      if (first === undefined || first === savedIndexRef.current) return
      savedIndexRef.current = first
      api.saveProgress(articleId, { reading_paragraph_index: first }).catch(() => undefined)
    }, { rootMargin: '-80px 0px -60% 0px' })

    paragraphRefs.current.forEach((node) => node && observer.observe(node))
    return () => observer.disconnect()
  }, [article, articleId, isPlayingThis])

  const seekToParagraph = (index: number) => {
    if (!article?.audio?.marks?.length) return
    const mark = article.audio.marks.find((m) => m.paragraph_index === index)
    if (!mark) return
    if (!isPlayingThis) player.play(article)
    window.setTimeout(() => player.seek(mark.start), isPlayingThis ? 0 : 400)
  }

  const listenFromHere = () => {
    if (!article) return
    const index = article.reading_paragraph_index || 0
    player.play(article)
    const mark = article.audio?.marks?.find((m) => m.paragraph_index === index)
    if (mark) window.setTimeout(() => player.seek(mark.start), 400)
  }

  const toggleFlag = async (field: 'is_favorite' | 'is_archived') => {
    if (!article) return
    const value = !article[field]
    setArticle({ ...article, [field]: value })
    await api.setState(article.id, { [field]: value }).catch(() => undefined)
    if (field === 'is_archived' && value) {
      notify('Artículo archivado')
      navigate('/')
    }
  }

  const regenerate = async () => {
    if (!article) return
    await api.regenerateAudio(article.id)
    notify('Regenerando el audio. Tarda alrededor de un minuto.')
    setArticle({ ...article, audio_status: 'processing' })
  }

  if (loading) return <Layout title="Artículo"><Loading /></Layout>
  if (!article) {
    return (
      <Layout title="Artículo">
        <Empty glyph="🗞" title="No se encontró el artículo" />
      </Layout>
    )
  }

  return (
    <Layout
      title={article.outlet || 'Artículo'}
      actions={
        <div className="row">
          <button className="btn ghost small" onClick={() => navigate(-1)}>‹ Atrás</button>
        </div>
      }
    >
      <article className="reader">
        <header>
          <div className="row" style={{ marginBottom: '.4rem' }}>
            <span className="pill">{article.reading_minutes} min</span>
            {article.is_paywalled && <span className="pill warn">de pago</span>}
            {article.is_listened && <span className="pill ok">escuchado</span>}
          </div>

          <h1>{article.title}</h1>

          <div className="byline">
            <span>{article.author}</span>
            <span>·</span>
            <span>{article.outlet}</span>
            <span>·</span>
            <span>{formatDate(article.published_at, {
              weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
            })}</span>
          </div>

          <div className="row" style={{ marginTop: '1rem' }}>
            {article.audio_status === 'ready' ? (
              <button className="btn primary small" onClick={listenFromHere}>
                ▶ Escuchar desde donde voy
              </button>
            ) : article.audio_status === 'error' ? (
              <button className="btn small danger" onClick={regenerate}>
                ↻ Reintentar el audio
              </button>
            ) : (
              <span className="pill warn">generando audio…</span>
            )}

            <button className="btn small" onClick={() => toggleFlag('is_favorite')}>
              {article.is_favorite ? '★ Favorito' : '☆ Favorito'}
            </button>
            <button className="btn small" onClick={() => toggleFlag('is_archived')}>
              Archivar
            </button>
            {article.audio_status === 'ready' && (
              <button className="btn small ghost" onClick={regenerate} title="Volver a generar el audio">
                ↻ Audio
              </button>
            )}
            <a
              className="btn small ghost"
              href={article.original_url || article.canonical_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Ver en el medio ↗
            </a>
          </div>

          <div className="row" style={{ marginTop: '.6rem' }}>
            <span className="faint">Tamaño de letra</span>
            <button
              className="btn ghost small"
              onClick={() => savePrefs({ font_size: Math.max(14, prefs.font_size - 1) })}
            >A−</button>
            <button
              className="btn ghost small"
              onClick={() => savePrefs({ font_size: Math.min(28, prefs.font_size + 1) })}
            >A+</button>
          </div>
        </header>

        {article.is_paywalled && (
          <div className="paywall-note">
            Esta columna es de pago y solo se pudo recuperar una parte.
            Guarda las cookies de tu suscripción a <strong>{article.outlet}</strong> en
            Ajustes › Credenciales para obtener el texto completo.
          </div>
        )}

        {article.audio?.error_message && (
          <div className="error-text">Audio: {article.audio.error_message}</div>
        )}

        <div className="reader-body">
          {article.body.map((block, index) => {
            const className = `blk${activeIndex === index ? ' active' : ''}`
            const props = {
              key: index,
              className,
              'data-index': index,
              ref: (node: HTMLElement | null) => { paragraphRefs.current[index] = node },
              onClick: () => seekToParagraph(index),
              dangerouslySetInnerHTML: { __html: block.html || block.text },
            }
            if (block.type === 'h2') return <h2 {...props} />
            if (block.type === 'h3') return <h3 {...props} />
            if (block.type === 'quote') return <blockquote {...props} />
            if (block.type === 'li') return <p {...props} style={{ paddingLeft: '1rem' }} />
            return <p {...props} />
          })}
        </div>

        <p className="faint" style={{ marginTop: '2rem' }}>
          Recopilado para lectura personal. Fuente:{' '}
          <a href={article.canonical_url} target="_blank" rel="noopener noreferrer">
            {article.outlet}
          </a>
        </p>
      </article>
    </Layout>
  )
}
