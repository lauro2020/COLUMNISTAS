import { useState, type FormEvent } from 'react'
import { useApp } from '../state/AppContext'
import { Spinner } from '../components/ui'

export function Login() {
  const { login } = useApp()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo entrar')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form className="box" onSubmit={submit}>
        <h1>Columnistas</h1>
        <div className="sub">Tus columnas del día, para leer o escuchar.</div>

        <div className="field">
          <label htmlFor="pwd">Contraseña</label>
          <input
            id="pwd"
            type="password"
            autoFocus
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <span className="hint">Es la que pusiste en APP_PASSWORD dentro del archivo .env</span>
        </div>

        {error && (
          <div className="faint" style={{ color: 'var(--danger)', marginBottom: '.8rem' }}>
            {error}
          </div>
        )}

        <button className="btn primary" style={{ width: '100%' }} disabled={busy || !password}>
          {busy ? <Spinner /> : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
