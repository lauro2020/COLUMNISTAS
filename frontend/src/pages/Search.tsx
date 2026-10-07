/** Búsqueda de texto completo y filtros sobre todo el histórico. */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ArticleListItem, Columnist } from '../api/types'
import { ArticleCard } from '../components/ArticleCard'
import { Layout } from '../components/Layout'
import { Empty, Loading } from '../components/ui'
import { useApp } from '../state/AppContext'

const STATES = [
  { value: '', label: 'Cualquier estado' },
  { value: 'unread', label: 'Sin leer' },
  { value: 'read', label: 'Leídos' },
  { value: 'listened', label: 'Escuchados' },
  { value: 'favorite', label: 'Favoritos' },
  { value: 'archived', label: 'Archivados' },
  { value: 'paywalled', label: 'De pago (incompletos)' },
]

export function Search() {
  const { notify } = useApp()
  const [query, setQuery] = useState('')
  const [columnistId, setColumnistId] = useState('')
  const [state, setState] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)

  const [columnists, setColumnists] = useState<Columnist[]>([])
  const [items, setItems] = useState<ArticleListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.columnists().then(setColumnists).catch(() => undefined)
  }, [])

  const search = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.search({
        q: query || undefined,
        columnist_id: columnistId || undefined,
        state: state || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        size: 20,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'La búsqueda falló')
    } finally {
      setLoading(false)
    }
  }, [query, columnistId, state, dateFrom, dateTo, page, notify])

  // Búsqueda con pequeño retardo mientras escribes
  useEffect(() => {
    const timer = window.setTimeout(search, 350)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => { setPage(1) }, [query, columnistId, state, dateFrom, dateTo])

  const pages = Math.max(1, Math.ceil(total / 20))

  return (
    <Layout title="Buscar">
      <div className="card">
        <div className="field">
          <label htmlFor="q">Texto</label>
          <input
            id="q"
            type="search"
            placeholder="Palabras en el título o en el cuerpo…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className="row">
          <div className="field" style={{ flex: 1, minWidth: '10rem' }}>
            <label htmlFor="col">Columnista</label>
            <select id="col" value={columnistId} onChange={(e) => setColumnistId(e.target.value)}>
              <option value="">Todos</option>
              {columnists.map((c) => (
                <option key={c.id} value={c.id}>{c.name} — {c.outlet}</option>
              ))}
            </select>
          </div>

          <div className="field" style={{ flex: 1, minWidth: '10rem' }}>
            <label htmlFor="st">Estado</label>
            <select id="st" value={state} onChange={(e) => setState(e.target.value)}>
              {STATES.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="row">
          <div className="field" style={{ flex: 1, minWidth: '9rem' }}>
            <label htmlFor="df">Desde</label>
            <input id="df" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1, minWidth: '9rem' }}>
            <label htmlFor="dt">Hasta</label>
            <input id="dt" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        </div>
      </div>

      {loading ? <Loading /> : items.length === 0 ? (
        <Empty glyph="🔍" title="Sin resultados" hint="Prueba con otras palabras o quita algún filtro." />
      ) : (
        <>
          <div className="faint" style={{ margin: '.5rem 0 1rem' }}>
            {total} {total === 1 ? 'resultado' : 'resultados'}
          </div>

          {items.map((article) => (
            <ArticleCard key={article.id} article={article} queue={items} showAuthor />
          ))}

          {pages > 1 && (
            <div className="row" style={{ justifyContent: 'center', marginTop: '1rem' }}>
              <button className="btn small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                ‹ Anterior
              </button>
              <span className="faint mono">{page} / {pages}</span>
              <button className="btn small" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Siguiente ›
              </button>
            </div>
          )}
        </>
      )}
    </Layout>
  )
}
