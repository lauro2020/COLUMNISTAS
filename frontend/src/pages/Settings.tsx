/** Configuración: columnistas, hora, voz, velocidad, retención y credenciales. */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Columnist, Credential, TtsProvider } from '../api/types'
import { Layout } from '../components/Layout'
import { Loading, formatDateTime } from '../components/ui'
import { clearOffline } from '../offline'
import { useApp } from '../state/AppContext'

const EMPTY_COLUMNIST = {
  name: '', outlet: '', source_url: '', feed_url: '',
  source_type: 'auto' as const, expected_frequency: 'diaria',
  extractor_key: '', active: true, notes: '',
}

export function Settings() {
  const { prefs, savePrefs, notify, logout } = useApp()

  const [columnists, setColumnists] = useState<Columnist[]>([])
  const [providers, setProviders] = useState<TtsProvider[]>([])
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [extractors, setExtractors] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const [draft, setDraft] = useState<typeof EMPTY_COLUMNIST | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [testing, setTesting] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null)

  const [credOutlet, setCredOutlet] = useState('Reforma')
  const [credCookies, setCredCookies] = useState('')

  const load = useCallback(async () => {
    try {
      const [c, p, cr, ex] = await Promise.all([
        api.columnists(), api.ttsProviders(), api.credentials(), api.extractors(),
      ])
      setColumnists(c); setProviders(p); setCredentials(cr); setExtractors(ex)
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo cargar la configuración')
    } finally {
      setLoading(false)
    }
  }, [notify])

  useEffect(() => { load() }, [load])

  const activeProvider = providers.find((p) => p.key === prefs.tts_provider)

  // -- columnistas -----------------------------------------------------------
  const saveColumnist = async () => {
    if (!draft) return
    const body = {
      ...draft,
      feed_url: draft.feed_url || null,
      extractor_key: draft.extractor_key || null,
    }
    try {
      if (editing) await api.updateColumnist(editing, body)
      else await api.createColumnist(body)
      setDraft(null); setEditing(null)
      notify('Guardado')
      load()
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudo guardar')
    }
  }

  const removeColumnist = async (columnist: Columnist) => {
    if (!window.confirm(
      `¿Eliminar a ${columnist.name}? Se borrarán también sus ${columnist.article_count} artículos guardados.`
    )) return
    await api.deleteColumnist(columnist.id)
    notify('Columnista eliminado')
    load()
  }

  const testColumnist = async (id: number) => {
    setTesting(id); setTestResult(null)
    try {
      setTestResult(await api.testColumnist(id))
    } catch (error) {
      setTestResult({ ok: false, error: String(error) })
    } finally {
      setTesting(null)
    }
  }

  // -- credenciales ----------------------------------------------------------
  const saveCredential = async () => {
    if (!credOutlet || !credCookies) return
    try {
      await api.saveCredential({
        outlet: credOutlet, kind: 'cookies', cookies_raw: credCookies,
      })
      setCredCookies('')
      notify('Credenciales guardadas y cifradas')
      load()
    } catch (error) {
      notify(error instanceof Error ? error.message : 'No se pudieron guardar')
    }
  }

  if (loading) return <Layout title="Ajustes"><Loading /></Layout>

  return (
    <Layout title="Ajustes">
      {/* ---------------------------------------------------------------- */}
      <div className="section-title">Recolección diaria</div>
      <div className="card">
        <div className="row">
          <div className="field" style={{ flex: 1, minWidth: '6rem' }}>
            <label htmlFor="hour">Hora</label>
            <input
              id="hour" type="number" min={0} max={23} value={prefs.collect_hour}
              onChange={(e) => savePrefs({ collect_hour: Number(e.target.value) })}
            />
          </div>
          <div className="field" style={{ flex: 1, minWidth: '6rem' }}>
            <label htmlFor="minute">Minuto</label>
            <input
              id="minute" type="number" min={0} max={59} step={5} value={prefs.collect_minute}
              onChange={(e) => savePrefs({ collect_minute: Number(e.target.value) })}
            />
          </div>
          <div className="field" style={{ flex: 2, minWidth: '11rem' }}>
            <label htmlFor="tz">Zona horaria</label>
            <input
              id="tz" value={prefs.timezone}
              onChange={(e) => savePrefs({ timezone: e.target.value })}
            />
          </div>
        </div>

        <label className="row" style={{ cursor: 'pointer' }}>
          <input
            type="checkbox" checked={prefs.auto_generate_audio}
            onChange={(e) => savePrefs({ auto_generate_audio: e.target.checked })}
          />
          <span>Generar el audio automáticamente al recolectar</span>
        </label>

        <div className="field" style={{ marginTop: '.8rem' }}>
          <label htmlFor="ret">Conservar el histórico (meses)</label>
          <input
            id="ret" type="number" min={0} max={120} value={prefs.retention_months}
            onChange={(e) => savePrefs({ retention_months: Number(e.target.value) })}
          />
          <span className="hint">0 = para siempre. Los favoritos nunca se borran.</span>
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      <div className="section-title">Voz y reproducción</div>
      <div className="card">
        <div className="field">
          <label htmlFor="prov">Proveedor de voz</label>
          <select
            id="prov" value={prefs.tts_provider}
            onChange={(e) => {
              const provider = providers.find((p) => p.key === e.target.value)
              savePrefs({
                tts_provider: e.target.value,
                tts_voice: provider?.voices[0]?.id ?? prefs.tts_voice,
              })
            }}
          >
            {providers.map((provider) => (
              <option key={provider.key} value={provider.key}>
                {provider.label}{provider.configured ? '' : ' — sin configurar'}
              </option>
            ))}
          </select>
          {activeProvider && !activeProvider.configured && (
            <span className="hint" style={{ color: 'var(--warn)' }}>
              Este proveedor no está listo. Revisa la clave en el archivo .env
              (OPENAI_API_KEY) o instala la voz de Piper.
            </span>
          )}
        </div>

        <div className="field">
          <label htmlFor="voice">Voz</label>
          <select
            id="voice" value={prefs.tts_voice}
            onChange={(e) => savePrefs({ tts_voice: e.target.value })}
          >
            {(activeProvider?.voices ?? []).map((voice) => (
              <option key={voice.id} value={voice.id}>{voice.label}</option>
            ))}
          </select>
          <span className="hint">
            El cambio se aplica a los audios nuevos. Para oírla en uno ya generado,
            abre el artículo y pulsa «↻ Audio».
          </span>
        </div>

        <div className="field">
          <label htmlFor="rate">Velocidad por defecto: {prefs.playback_rate}×</label>
          <input
            id="rate" type="range" min={0.75} max={2} step={0.25}
            value={prefs.playback_rate}
            onChange={(e) => savePrefs({ playback_rate: Number(e.target.value) })}
          />
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      <div className="section-title">Lectura</div>
      <div className="card">
        <div className="field">
          <label htmlFor="theme">Tema</label>
          <select
            id="theme" value={prefs.theme}
            onChange={(e) => savePrefs({ theme: e.target.value as 'light' | 'dark' | 'system' })}
          >
            <option value="system">Según el sistema</option>
            <option value="light">Claro</option>
            <option value="dark">Oscuro</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="fs">Tamaño de letra: {prefs.font_size} px</label>
          <input
            id="fs" type="range" min={14} max={28} step={1} value={prefs.font_size}
            onChange={(e) => savePrefs({ font_size: Number(e.target.value) })}
          />
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      <div className="section-title">Columnistas</div>

      {columnists.map((columnist) => (
        <div className="card" key={columnist.id}>
          <div className="spread">
            <div>
              <strong>{columnist.name}</strong>
              <div className="faint">
                {columnist.outlet} · {columnist.expected_frequency} · {columnist.article_count} artículos
              </div>
            </div>
            <label className="row" style={{ cursor: 'pointer' }} title="Activa o desactiva esta fuente">
              <input
                type="checkbox" checked={columnist.active}
                onChange={async (e) => {
                  await api.updateColumnist(columnist.id, { active: e.target.checked })
                  load()
                }}
              />
              <span className="faint">activa</span>
            </label>
          </div>

          <div className="faint" style={{ wordBreak: 'break-all', marginTop: '.4rem' }}>
            {columnist.source_url}
          </div>
          {columnist.feed_url && (
            <div className="faint" style={{ wordBreak: 'break-all' }}>RSS: {columnist.feed_url}</div>
          )}

          <div className="row" style={{ marginTop: '.7rem' }}>
            <button
              className="btn small"
              onClick={() => {
                setEditing(columnist.id)
                setDraft({
                  name: columnist.name,
                  outlet: columnist.outlet,
                  source_url: columnist.source_url,
                  feed_url: columnist.feed_url ?? '',
                  source_type: columnist.source_type as 'auto',
                  expected_frequency: columnist.expected_frequency,
                  extractor_key: columnist.extractor_key ?? '',
                  active: columnist.active,
                  notes: columnist.notes ?? '',
                })
              }}
            >Editar</button>

            <button
              className="btn small"
              onClick={() => testColumnist(columnist.id)}
              disabled={testing === columnist.id}
            >
              {testing === columnist.id ? 'Probando…' : 'Probar fuente'}
            </button>

            <button className="btn small danger" onClick={() => removeColumnist(columnist)}>
              Eliminar
            </button>
          </div>

          {testResult && testing === null && editing !== columnist.id && (
            <TestOutput result={testResult} onClose={() => setTestResult(null)} />
          )}
        </div>
      ))}

      {draft ? (
        <div className="card">
          <strong>{editing ? 'Editar columnista' : 'Nuevo columnista'}</strong>
          <div className="field" style={{ marginTop: '.7rem' }}>
            <label>Nombre</label>
            <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </div>
          <div className="field">
            <label>Medio</label>
            <input value={draft.outlet} onChange={(e) => setDraft({ ...draft, outlet: e.target.value })} />
          </div>
          <div className="field">
            <label>URL de su página de autor</label>
            <input
              value={draft.source_url}
              placeholder="https://…"
              onChange={(e) => setDraft({ ...draft, source_url: e.target.value })}
            />
          </div>
          <div className="field">
            <label>URL del RSS (opcional)</label>
            <input
              value={draft.feed_url}
              placeholder="Se descubre solo si el medio lo publica"
              onChange={(e) => setDraft({ ...draft, feed_url: e.target.value })}
            />
          </div>
          <div className="row">
            <div className="field" style={{ flex: 1, minWidth: '9rem' }}>
              <label>Tipo de fuente</label>
              <select
                value={draft.source_type}
                onChange={(e) => setDraft({ ...draft, source_type: e.target.value as 'auto' })}
              >
                <option value="auto">Automático (RSS y si no, HTML)</option>
                <option value="rss">Solo RSS</option>
                <option value="html">Solo HTML</option>
              </select>
            </div>
            <div className="field" style={{ flex: 1, minWidth: '9rem' }}>
              <label>Extractor</label>
              <select
                value={draft.extractor_key}
                onChange={(e) => setDraft({ ...draft, extractor_key: e.target.value })}
              >
                <option value="">Elegir según el dominio</option>
                {extractors.map((key) => <option key={key} value={key}>{key}</option>)}
              </select>
            </div>
          </div>
          <div className="field">
            <label>Frecuencia esperada</label>
            <input
              value={draft.expected_frequency}
              placeholder="diaria, lunes a viernes, semanal…"
              onChange={(e) => setDraft({ ...draft, expected_frequency: e.target.value })}
            />
          </div>

          <div className="row">
            <button className="btn primary" onClick={saveColumnist}>Guardar</button>
            <button className="btn ghost" onClick={() => { setDraft(null); setEditing(null) }}>
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button className="btn" onClick={() => { setDraft({ ...EMPTY_COLUMNIST }); setEditing(null) }}>
          + Añadir columnista
        </button>
      )}

      {/* ---------------------------------------------------------------- */}
      <div className="section-title">Credenciales por medio</div>
      <div className="card">
        <p className="faint" style={{ marginTop: 0 }}>
          Para los medios de pago a los que estás suscrito. Se guardan cifradas y
          solo se usan para leer contenido al que ya tienes derecho.
        </p>

        {credentials.map((cred) => (
          <div className="spread" key={cred.id} style={{ marginBottom: '.5rem' }}>
            <div>
              <strong>{cred.outlet}</strong>
              <div className="faint">
                {cred.cookie_names.length} cookies · actualizado {formatDateTime(cred.updated_at)}
              </div>
            </div>
            <button
              className="btn small danger"
              onClick={async () => { await api.deleteCredential(cred.id); load() }}
            >Borrar</button>
          </div>
        ))}

        <div className="field" style={{ marginTop: '.8rem' }}>
          <label>Medio</label>
          <input
            value={credOutlet}
            onChange={(e) => setCredOutlet(e.target.value)}
            placeholder="Debe coincidir exactamente con el medio del columnista"
          />
        </div>
        <div className="field">
          <label>Cookies de tu sesión</label>
          <textarea
            rows={3}
            value={credCookies}
            onChange={(e) => setCredCookies(e.target.value)}
            placeholder="nombre=valor; otra=valor"
          />
          <span className="hint">
            Cómo obtenerlas: entra al medio con tu cuenta en el navegador de tu
            computadora, abre las herramientas de desarrollo (F12), ve a
            Application → Cookies (o Almacenamiento → Cookies), y copia los pares
            nombre=valor separados por punto y coma.
          </span>
        </div>
        <button className="btn" onClick={saveCredential} disabled={!credCookies}>
          Guardar cifrado
        </button>
      </div>

      {/* ---------------------------------------------------------------- */}
      <div className="section-title">Sin conexión</div>
      <div className="card">
        <p className="faint" style={{ marginTop: 0 }}>
          Los artículos y audios que descargues se guardan en el teléfono.
        </p>
        <button
          className="btn small"
          onClick={async () => { await clearOffline(); notify('Descargas borradas') }}
        >
          Borrar lo descargado
        </button>
      </div>

      <div style={{ marginTop: '2rem' }}>
        <button className="btn ghost" onClick={logout}>Cerrar sesión</button>
      </div>
    </Layout>
  )
}

function TestOutput({ result, onClose }: {
  result: Record<string, unknown>
  onClose: () => void
}) {
  const ok = Boolean(result.ok)
  const sample = result.muestra_extraccion as Record<string, unknown> | null
  return (
    <div className="card" style={{ marginTop: '.7rem', background: 'var(--bg-sunken)' }}>
      <div className="spread">
        <span className={`pill ${ok ? 'ok' : 'bad'}`}>
          {ok ? 'La fuente responde' : 'La fuente falló'}
        </span>
        <button className="btn ghost small" onClick={onClose}>✕</button>
      </div>
      <div className="faint" style={{ marginTop: '.5rem' }}>
        Origen: {String(result.origen ?? '—')} · encontrados: {String(result.encontrados ?? 0)}
      </div>
      {result.error != null && <div className="error-text">{String(result.error)}</div>}
      {sample && (
        <div className="faint" style={{ marginTop: '.5rem' }}>
          Muestra: «{String(sample.titulo ?? '—')}» — {String(sample.parrafos ?? 0)} párrafos,{' '}
          {String(sample.palabras ?? 0)} palabras
          {sample.muro_de_pago ? ' (con muro de pago)' : ''}
        </div>
      )}
    </div>
  )
}
