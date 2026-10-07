/** Piezas pequeñas reutilizables. */

import type { ReactNode } from 'react'

export function Spinner() {
  return <span className="spinner" aria-label="Cargando" />
}

export function Loading({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div className="empty">
      <div className="row" style={{ justifyContent: 'center' }}>
        <Spinner /> <span>{label}</span>
      </div>
    </div>
  )
}

export function Empty({ glyph, title, hint }: { glyph: string; title: string; hint?: ReactNode }) {
  return (
    <div className="empty">
      <div className="big">{glyph}</div>
      <div style={{ fontWeight: 560, color: 'var(--text-soft)' }}>{title}</div>
      {hint && <div style={{ marginTop: '.4rem', fontSize: '.85rem' }}>{hint}</div>}
    </div>
  )
}

export function Toast({ message }: { message: string | null }) {
  if (!message) return null
  return <div className="toast" role="status">{message}</div>
}

/** 125 -> "2:05" */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatDate(iso: string | null, options?: Intl.DateTimeFormatOptions): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('es-MX', options ?? { day: 'numeric', month: 'long' })
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('es-MX', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

/** Fecha de hoy en formato YYYY-MM-DD, sin desfase de zona horaria. */
export function todayISO(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}
