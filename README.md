# Columnistas

Aplicación web instalable (PWA) que cada mañana recopila las columnas de opinión
de los autores que tú definas, las convierte a un formato de lectura limpio y
genera una versión en audio de cada una, para que puedas **leer o escuchar**
según el momento.

> Uso personal. El contenido recopilado no se publica ni se redistribuye.

---

## Índice

1. [Qué hace](#qué-hace)
2. [Cómo está construido](#cómo-está-construido)
3. [Instalación paso a paso](#instalación-paso-a-paso)
4. [Primer uso](#primer-uso)
5. [Instalar en el teléfono](#instalar-en-el-teléfono)
6. [Medios de pago (Reforma, El Financiero…)](#medios-de-pago)
7. [Añadir un columnista o un medio nuevo](#añadir-un-columnista-o-un-medio-nuevo)
8. [Voz: OpenAI o Piper local](#voz-openai-o-piper-local)
9. [Ejecutar cada pieza por separado](#ejecutar-cada-pieza-por-separado)
10. [Pruebas](#pruebas)
11. [Desplegar en un servidor](#desplegar-en-un-servidor)
12. [Cuando algo falla](#cuando-algo-falla)
13. [Decisiones técnicas y supuestos](#decisiones-técnicas-y-supuestos)

---

## Qué hace

- **Recolección diaria automática** a la hora que configures (por defecto 06:00,
  hora de Ciudad de México). Prioriza el RSS y solo recurre al HTML cuando el
  medio no publica feed.
- **Detección de duplicados** por URL canónica y por hash del contenido, para
  que una republicación o una corrección menor no aparezca dos veces.
- **Texto limpio**: título, autor, medio, fecha, cuerpo en párrafos y tiempo
  estimado de lectura. Se conservan enlaces, citas y subtítulos; se eliminan
  anuncios, banners de suscripción, "contenido relacionado" y menús.
- **Audio automático** con voz natural en español, listo antes de que despiertes,
  con introducción hablada (título, autor, medio y fecha) y botón para
  regenerarlo cuando quieras.
- **Sincronía texto ↔ audio**: mientras escuchas, el párrafo correspondiente se
  resalta; si tocas un párrafo, el audio salta ahí.
- **Pantalla de inicio por columnista**: una fila por cada uno, con el título y
  la fecha de su última columna. Solo aparece si se publicó en los últimos 15
  días; si es más antigua, en su lugar va la leyenda «Sin artículos recientes»
  con cuánto hace del último. Quien publicó hoy va arriba y marcado, de modo
  que se ve de un vistazo quién tiene algo nuevo y quién no.
- **Históricos plegados**: cada fila lleva una pestaña que despliega todo lo
  recopilado de ese columnista, del más reciente al más antiguo.
- **Estados** por artículo (sin leer, leído, escuchado, archivado, favorito),
  búsqueda de texto completo en español y filtros por columnista, medio, fecha
  y estado.
- **Reproductor** con velocidad de 0.75× a 2×, saltos de ±15 s, cola continua y
  reanudación desde donde te quedaste, sincronizada entre dispositivos.
- **PWA instalable**: funciona sin conexión y reproduce en segundo plano con
  controles en la pantalla de bloqueo.
- **Diagnóstico de fuentes**: si un medio cambia su web y el extractor falla, el
  sistema lo registra, marca esa fuente como degradada, te avisa y **sigue con
  las demás**.

---

## Cómo está construido

Tres componentes independientes que pueden ejecutarse y probarse por separado:

| # | Componente | Dónde vive | Se prueba solo con |
|---|---|---|---|
| 1 | **Recolector** — obtiene y normaliza artículos | `backend/app/collector/` | `python -m app.cli collect` |
| 2 | **Generador de audio** — texto a voz | `backend/app/audio/` | `python -m app.cli audio --article 1` |
| 3 | **Aplicación web (PWA)** — lo que abres | `frontend/` | `npm run dev` |

Y las piezas de infraestructura:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  web (nginx) │──▶│  api         │──▶│  PostgreSQL  │
│  la PWA      │   │  FastAPI     │   │  artículos   │
└──────────────┘   └──────┬───────┘   └──────────────┘
                          │
                   ┌──────▼───────┐   ┌──────────────┐
                   │  Redis       │◀──│  beat        │
                   │  la cola     │   │  el reloj    │
                   └──────┬───────┘   └──────────────┘
                          │
                   ┌──────▼────────────────────────────┐
                   │  worker: recolecta y genera audio │
                   └───────────────────────────────────┘
```

### Por qué este stack

- **Python + FastAPI** para el backend. La parte difícil de este proyecto es
  extraer texto limpio de webs de periódicos, y ahí Python gana claramente:
  `trafilatura` (detección del bloque principal por densidad de texto),
  `feedparser` y `playwright` no tienen equivalente igual de maduro en Node.
- **React + TypeScript + Vite** para el frontend, como pedía el enunciado. Da
  una PWA rápida y el tipado evita errores tontos entre la API y la interfaz.
- **PostgreSQL** porque trae búsqueda de texto completo **con diccionario en
  español** integrada (`to_tsvector('spanish', …)`), sin añadir un buscador
  aparte, y `JSONB` para guardar el cuerpo estructurado del artículo.
- **Redis + Celery** para la cola. `beat` dispara un latido cada 5 minutos y la
  tarea decide si toca recolectar según la hora guardada en la base de datos:
  así puedes cambiar la hora desde la app sin reiniciar nada.
- **Disco local para los MP3** (un volumen de Docker), con un adaptador para
  almacenamiento de objetos ya previsto. Para uso personal, el disco es más
  simple y más barato que S3.
- **Docker Compose** para que todo se levante con un comando y no tengas que
  instalar Python, Postgres ni Redis a mano.

---

## Instalación paso a paso

### Lo que necesitas antes

1. **Docker Desktop** instalado y abierto ([descarga](https://www.docker.com/products/docker-desktop/)).
   Es lo único que hace falta: no tienes que instalar Python ni bases de datos.
2. Una **clave de API de OpenAI** si quieres la voz de pago
   ([platform.openai.com/api-keys](https://platform.openai.com/api-keys)).
   También puedes empezar con la voz local gratuita.

### 1. Descarga el proyecto

```bash
git clone https://github.com/lauro2020/columnistas.git
cd columnistas
```

### 2. Crea tu archivo de configuración

```bash
cp .env.example .env
```

Abre `.env` con cualquier editor de texto y cambia estas tres líneas:

```ini
APP_SECRET_KEY=   # pega aquí una cadena larga y aleatoria (ver abajo)
APP_PASSWORD=     # la contraseña con la que entrarás a la app
OPENAI_API_KEY=   # tu clave sk-... (déjala vacía si usarás Piper)
```

Para generar la clave secreta, en la terminal:

```bash
openssl rand -hex 32
```

Copia el resultado y pégalo en `APP_SECRET_KEY`.

> Para `APP_PASSWORD`, usa letras, números y guiones, **sin comillas y sin los
> símbolos `#` ni `$`**. En un archivo `.env`, todo lo que va después de `#` se
> descarta como comentario, y `$` lo interpreta Docker como el principio del
> nombre de una variable. Con cualquiera de los dos, la contraseña que llega al
> contenedor no es la que escribiste.

> ⚠️ Guarda esa clave. Si la cambias más adelante, las credenciales de los
> medios que hayas guardado dejarán de poder descifrarse y tendrás que
> volver a introducirlas.

### 3. Enciéndelo

```bash
docker compose up -d --build
```

La primera vez tarda unos minutos (descarga las imágenes y compila). Cuando
termine, abre en el navegador:

**http://localhost:8080**

Entra con la contraseña que pusiste en `APP_PASSWORD`.

### 4. Comprueba que todo arrancó

```bash
docker compose ps
```

Deberías ver seis servicios en estado `running`: `db`, `redis`, `api`,
`worker`, `beat` y `web`.

### Comandos que te van a hacer falta

```bash
docker compose logs -f api        # ver qué está haciendo la API
docker compose logs -f worker     # ver la recolección y el audio
docker compose restart            # reiniciar todo
docker compose down               # apagar (los datos se conservan)
docker compose down -v            # apagar Y BORRAR todos los datos
```

---

## Primer uso

Al arrancar, la app ya trae cargados **21 columnistas** de nueve medios
(El Financiero, El Universal, Reforma, Milenio, Excélsior, La Razón, UnoTV,
Código Magenta y Proceso). Dos llegan **desactivados** porque les falta la URL
de su página de autor; se ven en Ajustes con una nota explicando qué completar.

No esperes a mañana: en la pantalla **Columnistas** pulsa **↻ Buscar ahora**. Con
tantas fuentes la primera recolección tarda unos **10 minutos** (hay una espera
de cortesía entre peticiones al mismo medio) y los audios otro tanto.

Para ver de un vistazo cuáles funcionan, sin esperar a la recolección:

```bash
docker compose exec api python -m app.cli check-sources
```

Te imprime una tabla con las 21 fuentes, cuántos artículos encuentra cada una
y el error exacto de las que fallan. Después, la pestaña **Fuentes** de la app
muestra lo mismo con el histórico de los últimos días.

### Cuánto cuesta el audio con esta lista

Con unas 15 columnas nuevas al día y la voz de OpenAI, ronda los **0.20 USD
diarios**, unos 6 o 7 dólares al mes. Si prefieres que no cueste nada, cambia a
Piper en Ajustes, o desactiva **«Generar el audio automáticamente al
recolectar»** y genera solo el de las columnas que te interesen, desde el botón
«↻ Audio» de cada artículo.

---

## Instalar en el teléfono

### Primero: que el teléfono llegue a la app

`http://localhost:8080` **solo funciona en la computadora donde corre**. En el
teléfono, «localhost» es el propio teléfono, y ahí no hay nada. Hay tres
caminos, de menos a más completo:

#### A. Por la red de tu casa (2 minutos, funciona hoy)

Desde la carpeta del proyecto:

```bash
sh tools/direccion-en-red.sh
```

Ese comando revisa, una por una, las cinco cosas que tienen que estar bien, y
al final te da la dirección:

```
── 2. Contenedores ──────────────────────────────
  ✓ El contenedor «web» (la página) está corriendo.
  ✓ El contenedor «api» (los datos) está corriendo.
  ✓ El puerto está abierto a toda la red (0.0.0.0:8080).

── 3. Escucha en el puerto 8080 ──────────────────
  ✓ Sí, hay un programa escuchando en el 8080.

── 4. Cortafuegos de macOS ───────────────────────
  ✓ El cortafuegos está apagado: no está estorbando.

── 5. Dirección para el teléfono ─────────────────

      http://192.168.1.42:8080
  ✓ responde
```

Lo que salga con **✗** es lo que hay que arreglar, y el propio comando dice
cómo. En el teléfono, **conectado al mismo WiFi**, escribe la dirección
completa —con `http://` delante— y entra con tu contraseña.

> Escribir `http://` no es un capricho: sin eso, el navegador del teléfono
> toma la dirección como una búsqueda, o intenta `https://` y falla.

Si el comando sale todo en ✓ y aun así el teléfono no abre, el problema está
entre el router y el teléfono. Por orden: apaga los datos móviles, apaga
cualquier VPN del teléfono, y comprueba que sea el mismo WiFi (muchos routers
dan dos redes con nombres parecidos, una acabada en «5G», que a veces no se
ven entre ellas; y la red «de invitados» casi nunca deja ver a las demás).

Con esto puedes **leer y escuchar** con normalidad. Lo que NO vas a tener:

| | Por qué |
|---|---|
| Instalar en la pantalla de inicio | Los navegadores solo lo permiten por HTTPS |
| Descargar para uso sin conexión | El service worker necesita HTTPS |
| Controles en la pantalla de bloqueo | La Media Session API necesita HTTPS |
| Que funcione fuera de tu casa | Es una dirección de tu red local |

La app te lo dice: el botón de descarga aparece como «Sin conexión no
disponible» y explica el motivo al tocarlo.

> La dirección `192.168.x.x` puede cambiar al reiniciar el router. Si un día
> deja de abrir, vuelve a ejecutar `ipconfig getifaddr en0`.

#### B. Con Tailscale (unos 15 minutos, gratis, es lo que recomiendo)

Te da HTTPS de verdad y funciona **desde cualquier lugar**, sin abrir puertos
en el router ni comprar un dominio. Tu Mac sigue siendo el servidor.

1. Instala [Tailscale](https://tailscale.com/download) en la Mac y en el
   teléfono, e inicia sesión con la misma cuenta en ambos.
2. En la Mac:

   ```bash
   tailscale serve --bg 8080
   tailscale serve status
   ```

3. Te dará una dirección `https://tu-mac.algo.ts.net`. Ábrela en el teléfono:
   ya es HTTPS, así que se puede instalar, descargar para sin conexión y usar
   los controles de la pantalla de bloqueo.

Sigue con la limitación de que la Mac tiene que estar encendida a las 6 de la
mañana para que la recolección ocurra sola.

#### C. En un servidor (lo definitivo)

Ver [Desplegar en un servidor](#desplegar-en-un-servidor). Es lo único que hace
que la recolección de las 06:00 ocurra siempre, esté tu Mac encendida o no.

### Después: instalarla

**iPhone (Safari):** abre la dirección de la app → botón Compartir →
*Añadir a pantalla de inicio*.

**Android (Chrome):** abre la dirección → menú de tres puntos →
*Instalar aplicación*.

Una vez instalada:

- Pulsa **⤓ Descargar para sin conexión** en la pantalla de inicio. A partir de ahí
  puedes leer y escuchar sin datos.
- El audio sigue sonando con la pantalla apagada, y aparecen los controles en la
  pantalla de bloqueo.
- Lo que leas o escuches se sincroniza con el navegador de tu computadora.

> Para que funcione desde fuera de tu casa, la app tiene que estar en un
> servidor accesible desde internet (ver [Desplegar en un servidor](#desplegar-en-un-servidor)).
> Los navegadores exigen HTTPS para instalar una PWA, salvo en `localhost`.

---

## Medios de pago

Reforma y, en parte, El Financiero exigen suscripción. La app puede usar **tu**
sesión de suscriptor para leer el contenido al que ya tienes derecho.

### Cómo obtener las cookies

1. En tu computadora, abre el medio en el navegador **e inicia sesión**.
2. Pulsa `F12` (o clic derecho → *Inspeccionar*) para abrir las herramientas de
   desarrollo.
3. Ve a la pestaña **Application** (en Chrome) o **Almacenamiento** (en Firefox).
4. En el panel izquierdo abre **Cookies** y elige el dominio del medio.
5. Copia los pares `nombre=valor` que veas, separados por punto y coma:

   ```
   sessionid=a1b2c3...; usuario=demo; token=xyz...
   ```

6. En la app: **Ajustes → Credenciales por medio**. Escribe el nombre del medio
   **exactamente igual** que aparece en la ficha del columnista (por ejemplo
   `Reforma`), pega las cookies y guarda.

Se cifran con AES antes de guardarse; ni leyendo la base de datos se ven en
claro. Solo se envían al medio al que pertenecen.

> Las cookies caducan cada cierto tiempo. Si un medio vuelve a mostrar textos
> truncados, repite el proceso.

---

## Añadir un columnista o un medio nuevo

### Caso 1: el medio ya está soportado (o basta el extractor genérico)

No hay que tocar código. En la app: **Ajustes → Columnistas → + Añadir
columnista**. Rellena nombre, medio y la URL de su página de autor, guarda y
pulsa **Probar fuente**: te dirá si encontró artículos y te enseñará una muestra
del texto extraído.

El extractor genérico funciona razonablemente bien en casi cualquier periódico,
así que empieza siempre por aquí.

### Caso 2: el medio necesita un extractor propio

Solo si el genérico no da buenos resultados. Es **un único archivo pequeño** y no
hay que tocar nada más del sistema: el registro lo descubre solo.

Crea `backend/app/collector/extractors/mimedio.py`:

```python
from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef, ExtractedArticle
from app.collector.extractors.generic import GenericExtractor


class MiMedioExtractor(GenericExtractor):
    key = "mimedio"                       # identificador único
    domains = ("mimedio.com.mx",)         # dominios que atiende
    outlet = "Mi Medio"                   # nombre legible
    needs_browser = False                 # True si el sitio necesita JavaScript

    # Dónde vive el cuerpo del artículo, en orden de preferencia
    BODY_SELECTORS = ["div.cuerpo-nota", "[itemprop='articleBody']"]

    def extract_from_html(self, html: str, url: str) -> ExtractedArticle | None:
        soup = BeautifulSoup(html, "lxml")
        for selector in self.BODY_SELECTORS:
            node = soup.select_one(selector)
            if not node:
                continue
            blocks = normalize.html_to_blocks(str(node), url)
            if len(blocks) >= 2:
                text = normalize.blocks_to_text(blocks)
                return ExtractedArticle(
                    title=(normalize.extract_title(soup) or "Sin título").strip(),
                    canonical_url=normalize.extract_canonical(soup, url),
                    original_url=url,
                    blocks=blocks,
                    author=self._author(soup),
                    outlet=self.outlet,
                    published_at=dates.extract_published_at(soup, html),
                    summary=normalize.make_summary(text),
                    is_paywalled=normalize.looks_paywalled(
                        text, normalize.count_words(text)),
                    extractor=self.key,
                )
        # Si nada funciona, el genérico se encarga
        return super().extract_from_html(html, url)

    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        # Opcional: si no lo defines, se usa la heurística genérica de enlaces
        return super().discover_from_html(html, base_url)
```

Después:

```bash
docker compose restart api worker
```

Y en la ficha del columnista elige tu extractor en el campo **Extractor**.

Mira `eluniversal.py` (selectores CSS), `elfinanciero.py` (JSON incrustado de
Arc) y `reforma.py` (muro de pago + navegador headless) como ejemplos reales de
las tres situaciones típicas.

### Cuando un medio responde 403

Algunos periódicos rechazan cualquier petición que no venga de un navegador
—incluso la de su propio `robots.txt`—. Para esos casos, cada columnista tiene
la casilla **«Identificarse como navegador»** en su ficha:

- Está **desactivada por defecto**: la app se presenta con su propio
  User-Agent, que es lo correcto y lo que permite al medio saber quién le pide
  las páginas.
- Al activarla, las peticiones **a esa fuente** se hacen igual que las de tu
  navegador. Es la misma petición que haría tu Mac al abrir esa página: sirve
  para leer con comodidad lo que ya puedes leer, y sigue siendo para tu
  consumo personal.
- Si aun con la casilla activada el medio devuelve 403, es que filtra por algo
  más que el User-Agent y hace falta el navegador headless
  (`INSTALL_PLAYWRIGHT=true` al construir y `ENABLE_HEADLESS_BROWSER=true`).

### Activar el navegador headless

Hace falta en dos casos: sitios que pintan el texto con JavaScript y sitios
que devuelven 403 aun con la casilla de navegador activada.

En el archivo `.env`, pon las **dos** variables en `true`. Son dos cosas
distintas: la primera instala Chromium al construir la imagen, la segunda
permite usarlo.

```ini
INSTALL_PLAYWRIGHT=true
ENABLE_HEADLESS_BROWSER=true
```

> ⚠️ Cada una en **su propio renglón y sin `#` delante**. Si el nombre solo
> aparece dentro de un comentario (una línea que empieza por `#`), no cuenta:
> Docker ignora todo lo que va después de la almohadilla. Para salir de dudas,
> `python -m app.cli doctor` te dice en su punto 4 si Chromium está instalado
> de verdad.

Y reconstruye:

```bash
docker compose up -d --build
```

La imagen crece unos 500 MB y la primera construcción tarda bastante más. A
partir de ahí, cuando una petición normal falle, el sistema reintenta con un
Chromium de verdad. Es más lento, así que solo se usa como respaldo.

Si un medio devuelve 403 **también** desde el navegador headless, está
bloqueando activamente la lectura automatizada y no hay forma razonable de
recolectarlo: tendrás que abrirlo a mano.

### Reglas que aplica el sistema por ti

No tienes que preocuparte de esto al escribir un extractor, ya está resuelto:

- Se respeta `robots.txt` (desactivable con `RESPECT_ROBOTS=false`).
- Se envía un User-Agent propio e identificable (salvo en las fuentes donde
  actives «Identificarse como navegador»).
- Hay un mínimo de segundos entre peticiones al mismo dominio.
- Los fallos temporales se reintentan con espera exponencial (2 s, 4 s, 8 s…).
- El navegador headless solo se usa si el contenido lo requiere.
- Un extractor que falla **nunca** tumba al resto: se registra, se marca la
  fuente como degradada y la ejecución continúa.

---

## Voz: OpenAI o Piper local

Se cambia en **Ajustes → Voz y reproducción**, sin reiniciar nada.

### OpenAI (por defecto)

Voz muy natural en español. Cuesta alrededor de **0.01–0.02 USD por columna**
con `gpt-4o-mini-tts`; tres columnistas diarios salen por menos de 1 USD al mes.
Necesita `OPENAI_API_KEY` en el `.env`.

### Piper (local, gratis, sin internet)

Alternativa sin coste ni límites. Instala una voz una sola vez:

```bash
docker compose exec api python -m app.cli download-piper-voice es_MX-ald-medium
```

Y luego elige "Piper (local, gratis)" en Ajustes. Voces disponibles:
`es_MX-ald-medium`, `es_MX-claude-high`, `es_ES-davefx-medium`,
`es_ES-sharvard-medium`, `es_AR-daniela-high`.

> Nota: la imagen de Docker no trae el binario de Piper preinstalado para no
> engordarla. Si vas a usar Piper como opción principal, añade su instalación al
> `backend/Dockerfile`; el código ya lo detecta y te avisa con un mensaje claro
> si falta.

### Qué se le hace al texto antes de leerlo

`backend/app/audio/textprep.py` traduce a español hablado:

| Escrito | Leído |
|---|---|
| `el 35%` | el treinta y cinco por ciento |
| `1,200 mdp` | mil doscientos millones de pesos |
| `el 12/03/2025` | el doce de marzo de dos mil veinticinco |
| `el Dr. Pérez, art. 4o.` | el doctor Pérez, artículo cuarto |
| `la SHCP` | la Secretaría de Hacienda y Crédito Público |
| `el PJF` | el P-J-F (se deletrea) |

Además se añaden pausas entre párrafos y una introducción hablada al inicio.
Los artículos largos se trocean, se sintetizan **en paralelo** y se unen con
ffmpeg, de modo que una columna larga no tarda mucho más que una corta.

---

## Ejecutar cada pieza por separado

Los tres componentes son independientes. Con Docker corriendo:

```bash
# Recolectar ahora mismo (todas las fuentes)
docker compose exec api python -m app.cli collect

# Recolectar solo una fuente (el id sale de `status`)
docker compose exec api python -m app.cli collect --columnist 2

# Probar TODAS las fuentes de una vez y ver cuáles fallan
docker compose exec api python -m app.cli check-sources

# ¿Por qué no me llega nada de este columnista? Enseña el veredicto de cada
# enlace de su página: ya guardado, demasiado viejo, o por qué no se extrajo
docker compose exec api python -m app.cli why "riva palacio"

# Corregir fechas mal leídas de artículos ya guardados (primero enseña, y
# solo toca la base de datos si añades --apply)
docker compose exec api python -m app.cli fix-dates

# Probar una sola fuente SIN guardar nada: ¿responde? ¿qué extrae?
docker compose exec api python -m app.cli test-source 3

# Generar el audio de un artículo concreto
docker compose exec api python -m app.cli audio --article 12 --force

# Generar todos los audios que falten
docker compose exec api python -m app.cli audio --missing

# Ver el estado general
docker compose exec api python -m app.cli status

# Diagnosticar la red: ¿resuelven los dominios? ¿responden por HTTPS?
docker compose exec api python -m app.cli doctor
```

### Desarrollo sin Docker

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.cli migrate && python -m app.cli seed
uvicorn app.main:app --reload

# Worker y reloj (en otras dos terminales)
celery -A app.tasks.celery_app worker --loglevel=INFO
celery -A app.tasks.celery_app beat --loglevel=INFO

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Necesitas PostgreSQL y Redis corriendo, y un `backend/.env` apuntando a ellos.
También hace falta `ffmpeg` en el sistema (`brew install ffmpeg` o
`apt install ffmpeg`).

---

## Pruebas

```bash
cd backend
pytest                 # 55 pruebas, ninguna toca internet
pytest -v tests/test_extractors.py
```

Qué cubren:

- `test_extractors.py` — los cuatro extractores contra HTML de ejemplo: que
  encuentran los artículos, que limpian el ruido, que detectan el muro de pago
  de Reforma, que el registro elige el extractor correcto por dominio y que un
  HTML vacío o corrupto no revienta nada.
- `test_normalize.py` — canonicalización de URLs, conservación de enlaces y
  citas, eliminación de anuncios y banners, estabilidad del hash de contenido.
- `test_textprep.py` — cifras, porcentajes, fechas, abreviaturas y siglas;
  troceado sin perder ningún párrafo.
- `test_audio_pipeline.py` — la canalización completa con un proveedor de voz
  simulado: que se sintetiza todo el artículo, que las marcas de sincronía
  cubren todos los párrafos y van en orden, y que un fallo del proveedor da un
  error controlado.
- `test_collector.py` — User-Agent, reintentos, cookies de suscriptor, bloqueo
  por robots.txt, lectura de RSS, cifrado de credenciales y recuperación ante
  fallos de DNS (incluida la variante del dominio con o sin «www.»).

El frontend se comprueba con `cd frontend && npm run typecheck`.

---

## Desplegar en un servidor

Para que la recolección de las 06:00 ocurra de verdad sin que enciendas nada,
la app tiene que vivir en una máquina encendida 24/7. Un servidor de 5–10 USD
al mes sobra.

```bash
# En el servidor (Ubuntu):
curl -fsSL https://get.docker.com | sh
git clone https://github.com/lauro2020/columnistas.git
cd columnistas
cp .env.example .env && nano .env      # rellena las tres variables
docker compose up -d --build
```

Después pon un HTTPS delante (Caddy es lo más sencillo, obtiene el certificado
solo):

```caddyfile
columnistas.tudominio.com {
    reverse_proxy localhost:8080
}
```

HTTPS no es opcional: sin él el teléfono no deja instalar la PWA ni usar el
service worker.

### Copias de seguridad

```bash
# Guardar
docker compose exec -T db pg_dump -U columnistas columnistas > respaldo.sql

# Restaurar
docker compose exec -T db psql -U columnistas columnistas < respaldo.sql
```

Los MP3 viven en el volumen `audiodata` y siempre se pueden regenerar desde el
texto, así que lo importante es la base de datos.

---

## Cuando algo falla

**Empieza siempre por aquí.** Dos comandos: el primero distingue entre un
problema de red y un bloqueo del medio; el segundo prueba la extracción de
todas las fuentes a la vez.

```bash
docker compose exec api python -m app.cli doctor
docker compose exec api python -m app.cli check-sources
```

| Síntoma | Qué mirar |
|---|---|
| Cambiaste `APP_PASSWORD` y sigue sin dejarte entrar | `docker compose restart` **no** vuelve a leer el `.env`. Hace falta `docker compose up -d`, que recrea los contenedores con los valores nuevos. |
| No te deja entrar con tu contraseña | `docker compose exec api python -m app.cli check-password`: te dice si la que tecleas coincide con la que tiene el contenedor, sin mostrarla. Ojo con `#` y `$` en el `.env`: el primero convierte en comentario todo lo que le sigue, y el segundo lo interpreta Docker como una variable. |
| Al construir: `Package 'ttf-ubuntu-font-family' has no installation candidate` | Playwright intentaba instalar paquetes de Ubuntu sobre Debian. Ya está corregido: la imagen base está fijada a Debian 12 y las bibliotecas se instalan por nombre. Si lo ves, haz `git pull` y vuelve a construir. |
| `HTTP 403 — el medio rechaza a nuestro robot` | Ese sitio responde 403 a cualquier cliente que no sea un navegador, incluso para servir su `robots.txt`. En **Ajustes › Columnistas › Editar**, activa **«Identificarse como navegador»** para esa fuente. |
| `403 … aun identificándonos como navegador` | El sitio (Milenio, por ejemplo) filtra por algo más que el User-Agent. Activa el navegador headless: ver más abajo. |
| Reforma dice `redirigió a su pantalla de acceso` | No reconoció tu sesión. Guarda las cookies en **Ajustes › Credenciales** con el medio escrito exactamente `Reforma`. Si ya estaban, caducaron: vuelve a copiarlas. |
| `No address associated with hostname` | Es DNS, no scraping: el contenedor no logra traducir el dominio a una dirección. Corre `doctor`. La configuración ya fuerza DNS de Cloudflare y Google, porque el resolutor interno de Docker Desktop falla con algunos periódicos. Si sigue, prueba `docker compose restart` y reinicia Docker Desktop. |
| No aparece ninguna columna | Pestaña **Fuentes**: ahí se ve el error exacto de cada medio. |
| Un columnista dice «Sin artículos recientes» | Su última columna recopilada tiene más de 15 días. La leyenda dice cuánto hace; su histórico completo sigue disponible en la pestaña **históricos** de su fila. |
| Una fuente en rojo | El medio cambió su web. Prueba `test-source <id>`; si el genérico tampoco saca nada, hará falta ajustar el extractor. |
| Un columnista que sí bajaba y de pronto se quedó atrás | `python -m app.cli why "<parte del nombre>"`. Reproduce en vivo la recolección y da el veredicto de cada enlace de su página: ya guardado, demasiado viejo, o el motivo exacto por el que no se pudo extraer. |
| Una columna reciente aparece fechada meses atrás | La fecha se leyó de la barra lateral de la página, no del artículo. Ya no debería pasar (manda la fecha de la dirección), pero lo ya guardado se arregla con `python -m app.cli fix-dates --apply`. |
| Textos truncados o "de pago" | Faltan las cookies de tu suscripción, o caducaron. Ver [Medios de pago](#medios-de-pago). |
| El audio dice "falló" | Casi siempre es la clave de OpenAI (ausente, sin saldo o con el límite alcanzado). El error completo se ve al abrir el artículo. |
| El audio no suena en el teléfono | Descarga el día primero si estás sin conexión; y comprueba que la app va por HTTPS. |
| La app no se instala en el teléfono | Solo se puede instalar por HTTPS (o en `localhost`). Por IP de red local no. Ver [Instalar en el teléfono](#instalar-en-el-teléfono). |
| El teléfono no abre la app | `sh tools/direccion-en-red.sh`: revisa contenedores, puerto, cortafuegos y dirección, y dice qué falta. |
| Todo va lento al recolectar | Es a propósito: hay una espera mínima entre peticiones al mismo medio. Se ajusta con `REQUEST_DELAY_SECONDS`. |

Ver los registros:

```bash
docker compose logs -f worker    # recolección y audio
docker compose logs -f api       # peticiones de la app
docker compose logs -f beat      # el reloj de las 6 AM
```

---

## Decisiones técnicas y supuestos

### Decisiones

1. **RSS primero, HTML después.** Cuando el medio publica feed es más rápido,
   más estable y mucho más respetuoso con su servidor. El sistema incluso
   descubre el feed solo y lo guarda para la próxima vez.
2. **Extractores en cascada.** Extractor del medio → extractor genérico →
   fallo controlado. Un medio que rediseña su web degrada la calidad, no rompe
   la aplicación.
3. **El cuerpo se guarda como bloques con tipo** (`p`, `h2`, `quote`, `li`), no
   como HTML plano. Eso permite a la vez renderizar la lectura conservando
   enlaces y citas, y darle al motor de voz solo el texto, sin etiquetas.
4. **La hora de recolección no vive en el calendario de Celery**, sino en la
   base de datos: `beat` late cada 5 minutos y la tarea decide. Así la hora se
   cambia desde la app sin reiniciar servicios.
5. **Duplicados por dos vías**: URL canónica (con los parámetros de rastreo
   eliminados) y hash del contenido normalizado (sin acentos, mayúsculas ni
   espacios de más). Lo primero atrapa republicaciones; lo segundo, ediciones
   menores.
6. **Un fragmento de audio por grupo de párrafos**, con su duración medida por
   `ffprobe`. De ahí salen las marcas de sincronía párrafo ↔ segundo, sin
   depender de que el proveedor de voz ofrezca *timestamps* (la mayoría no lo
   hace).
7. **MP3 mono a 22 kHz y 64 kbps.** Para voz suena igual que un archivo mucho
   mayor y pesa cinco veces menos: importa al descargar el día en el teléfono.
8. **Peticiones parciales (HTTP Range) implementadas a mano** en el endpoint del
   audio, y replicadas dentro del service worker sobre la caché. Sin eso no
   podrías saltar dentro de un audio descargado.
9. **Un solo usuario con contraseña**, con bloqueo temporal tras varios
   intentos fallidos y sin documentación de la API publicada. No hay registro,
   roles ni recuperación de contraseña: es una app personal, y añadirlos sería
   complejidad sin beneficio.
10. **Credenciales cifradas con Fernet** (AES-128 + HMAC), con la llave derivada
    de `APP_SECRET_KEY`. Nunca se devuelven al navegador: la app solo muestra
    los *nombres* de las cookies guardadas.
11. **La primera recolección de cada fuente trae solo dos columnas.** Sin ese
    tope, estrenar veinte columnistas volcaría el archivo histórico de cada
    medio en la bandeja de hoy y pagarías la síntesis de voz de todo ello. A
    partir de la segunda ejecución rige el tope normal.
12. **Un choque de clave única no tumba la ejecución.** Cada artículo se
    inserta dentro de su propio punto de guardado: si dos columnistas
    comparten una columna sindicada, se descarta esa inserción y la
    recolección continúa.
13. **DNS explícito en los contenedores** (Cloudflare y Google, por TCP). El
    resolutor interno de Docker Desktop falla con algunos dominios de
    periódicos —los que van tras Akamai o CloudFront— y devuelve
    «No address associated with hostname». Además, un fallo de DNS no consume
    reintentos (no se arregla esperando) y se prueba una vez la variante del
    dominio con o sin «www.», corrigiendo la URL guardada si esa funciona.

### Supuestos

- **Es una app personal, de un solo usuario.** Todo lo recopilado es para tu
  consumo; nada se publica ni se comparte.
- **Los selectores CSS de los extractores específicos son los habituales de cada
  medio, pero no pude verificarlos contra las webs reales** (el entorno donde se
  construyó este proyecto tiene bloqueado el acceso a esos dominios). Si alguno
  ya no coincide, el extractor genérico entra automáticamente y el sistema sigue
  funcionando; la pantalla **Fuentes** te dirá exactamente qué está pasando, y
  ajustar un selector es cambiar una línea.
- **Reforma requiere suscripción para prácticamente todo**, y pinta el contenido
  con JavaScript. Por eso su extractor viene marcado con `needs_browser = True`.
  Para usarlo, construye la imagen con el navegador incluido:
  `INSTALL_PLAYWRIGHT=true docker compose build api worker` y pon
  `ENABLE_HEADLESS_BROWSER=true` en el `.env`.
- **La retención por defecto es de 12 meses**; los favoritos nunca se borran.
- **La zona horaria por defecto es `America/Mexico_City`.**
- **Solo se procesan como máximo 6 artículos nuevos por fuente y ejecución**, y
  se ignoran los de más de 10 días. Es una salvaguarda para que la primera
  ejecución no descargue el archivo histórico entero del medio.

---

## Licencia y uso responsable

Proyecto de uso personal. Respeta los términos de servicio de cada medio: la
herramienta está pensada para leer con comodidad contenido al que ya tienes
acceso legítimo, no para redistribuirlo.
