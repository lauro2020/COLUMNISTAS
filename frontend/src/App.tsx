import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Diagnostics } from './pages/Diagnostics'
import { Inbox } from './pages/Inbox'
import { Login } from './pages/Login'
import { Reader } from './pages/Reader'
import { Search } from './pages/Search'
import { Settings } from './pages/Settings'
import { AppProvider, useApp } from './state/AppContext'
import { PlayerProvider } from './state/PlayerContext'

function Router() {
  const { authenticated } = useApp()

  if (!authenticated) return <Login />

  return (
    <PlayerProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Inbox />} />
          <Route path="/articulo/:id" element={<Reader />} />
          <Route path="/buscar" element={<Search />} />
          <Route path="/diagnostico" element={<Diagnostics />} />
          <Route path="/configuracion" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </PlayerProvider>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Router />
    </AppProvider>
  )
}
