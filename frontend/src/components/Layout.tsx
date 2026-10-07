import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useApp } from '../state/AppContext'
import { PlayerBar } from './PlayerBar'
import { Toast } from './ui'

const TABS = [
  { to: '/', glyph: '📥', label: 'Columnistas', end: true },
  { to: '/buscar', glyph: '🔍', label: 'Buscar', end: false },
  { to: '/diagnostico', glyph: '📊', label: 'Fuentes', end: false },
  { to: '/configuracion', glyph: '⚙️', label: 'Ajustes', end: false },
]

interface Props {
  title: string
  actions?: ReactNode
  children: ReactNode
}

export function Layout({ title, actions, children }: Props) {
  const { toast } = useApp()

  return (
    <div className="app">
      <header className="topbar">
        <h1>{title}</h1>
        {actions}
      </header>

      <main className="content">{children}</main>

      <PlayerBar />
      <Toast message={toast} />

      <nav className="tabbar">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            <span className="glyph">{tab.glyph}</span>
            <span>{tab.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
