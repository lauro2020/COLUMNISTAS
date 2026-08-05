import { useState, type FormEvent } from 'react'
import { useApp } from '../state/AppContext'
import { Spinner } from '../components/ui'

export function Login() {
  const { login } = useApp()
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [intentos, setIntentos] = useState(0)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo entrar')
      setIntentos((n) => n + 1)
    } finally {
      setBusy(false)
    }
  }

  // Espacios al principio o al final: el teclado del teléfono los mete solo al
  // aceptar una sugerencia, y son imposibles de ver con el texto oculto.
  const conEspacios = password !== password.trim() && password.length > 0

  return (
    <div className="login">
      <form className="box" onSubmit={submit}>
        <h1>Columnistas</h1>
        <div className="sub">Tus columnas del día, para leer o escuchar.</div>

        <div className="field">
          <label htmlFor="pwd">Contraseña</label>
          <div style={{ position: 'relative' }}>
            <input
              id="pwd"
              type={visible ? 'text' : 'password'}
              autoFocus
              autoComplete="current-password"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              style={{ paddingRight: '3.2rem' }}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button
              type="button"
              className="btn ghost small"
              style={{ position: 'absolute', right: '.3rem', top: '50%', transform: 'translateY(-50%)' }}
              onClick={() => setVisible((v) => !v)}
              title={visible ? 'Ocultar' : 'Ver lo que escribo'}
            >
              {visible ? 'ocultar' : 'ver'}
            </button>
          </div>
          <span className="hint">Es la que pusiste en APP_PASSWORD dentro del archivo .env</span>
          {conEspacios && (
            <span className="hint" style={{ color: 'var(--warn)' }}>
              Cuidado: hay un espacio al principio o al final. Pulsa «ver» para
              comprobarlo.
            </span>
          )}
        </div>

        {error && (
          <div className="faint" style={{ color: 'var(--danger)', marginBottom: '.8rem' }}>
            {error}
          </div>
        )}

        {intentos >= 2 && (
          <div
            className="faint"
            style={{
              marginBottom: '.8rem',
              paddingLeft: '.6rem',
              borderLeft: '2px solid var(--line)',
            }}
          >
            Si estás seguro de la contraseña, puede que el contenedor conserve
            la anterior. En la computadora donde corre la app:
            <div style={{ marginTop: '.4rem', fontFamily: 'ui-monospace, monospace', fontSize: '.75rem' }}>
              docker compose up -d
            </div>
            <div style={{ marginTop: '.4rem', fontFamily: 'ui-monospace, monospace', fontSize: '.75rem' }}>
              docker compose exec api python -m app.cli check-password
            </div>
            <div style={{ marginTop: '.4rem' }}>
              «restart» no basta: no vuelve a leer el archivo .env.
            </div>
          </div>
        )}

        <button className="btn primary" style={{ width: '100%' }} disabled={busy || !password}>
          {busy ? <Spinner /> : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
