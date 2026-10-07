"""HTML de ejemplo para las pruebas (no se descarga nada de internet)."""

from __future__ import annotations

GENERIC_ARTICLE = """
<html><head>
  <title>La columna de prueba | Diario X</title>
  <meta property="og:title" content="La columna de prueba">
  <meta name="description" content="Un resumen breve de la columna.">
  <meta property="article:published_time" content="2025-03-12T08:00:00-06:00">
  <link rel="canonical" href="https://diariox.test/opinion/la-columna-de-prueba?utm_source=twitter">
</head><body>
  <nav class="navbar"><a href="/">Inicio</a><a href="/opinion">Opinión</a></nav>
  <div class="publicidad-top">Anuncio molesto</div>
  <article>
    <h1>La columna de prueba</h1>
    <div class="autor-box">Por Autor de Prueba</div>
    <div class="cuerpo-nota">
      <p>El primer p&aacute;rrafo habla del 35% de los votos y de la
         <a href="/nota-relacionada">reforma judicial</a> que discute el Congreso.</p>
      <h2>Un subt&iacute;tulo intermedio</h2>
      <p>El segundo p&aacute;rrafo insiste en que el 12 de marzo de 2025 cambi&oacute; todo,
         con 1,200 millones de pesos de por medio.</p>
      <blockquote>Una cita textual que debe conservarse.</blockquote>
      <p>Tercer p&aacute;rrafo de cierre, con una idea final suficientemente larga
         para no ser descartada por el limpiador de bloques.</p>
    </div>
    <div class="relacionadas"><h3>Te puede interesar</h3><p>Otra nota distinta</p></div>
  </article>
  <div class="newsletter-banner">Suscr&iacute;bete a nuestro bolet&iacute;n</div>
  <footer><p>Aviso de privacidad</p></footer>
</body></html>
"""

AUTHOR_PAGE = """
<html><body>
  <nav><a href="/seccion/opinion">Opini&oacute;n</a></nav>
  <main>
    <article><h2><a href="/opinion/2025/03/12/la-primera-columna/">La primera columna del autor</a></h2></article>
    <article><h2><a href="/opinion/2025/03/11/la-segunda-columna/">La segunda columna del autor</a></h2></article>
    <article><h2><a href="https://diariox.test/opinion/2025/03/10/la-tercera-columna/">La tercera columna del autor</a></h2></article>
    <a href="/autores/otro-autor/">Otro autor</a>
    <a href="/suscripciones/">Suscr&iacute;bete</a>
  </main>
</body></html>
"""

ELUNIVERSAL_ARTICLE = """
<html><head>
  <meta property="og:title" content="En Tercera Persona: la ciudad de noche">
  <meta property="article:published_time" content="2025-03-12T06:30:00-06:00">
  <link rel="canonical" href="https://www.eluniversal.com.mx/opinion/hector-de-mauleon/la-ciudad-de-noche/">
  <meta name="author" content="H&eacute;ctor de Maule&oacute;n">
</head><body>
  <div class="field--name-body">
    <p>La ciudad cambia cuando cae la noche y las calles se vuelven otra cosa distinta.</p>
    <p>En la esquina de Bol&iacute;var, el 40% de los locales cerr&oacute; durante el &uacute;ltimo a&ntilde;o.</p>
    <p>Queda, sin embargo, la memoria de lo que fue ese barrio hace apenas dos d&eacute;cadas.</p>
  </div>
  <div class="mas-noticias"><p>Lee tambi&eacute;n otra cosa</p></div>
</body></html>
"""

ELUNIVERSAL_AUTHOR_PAGE = """
<html><body>
  <div class="view-content">
    <article><a href="/opinion/hector-de-mauleon/la-ciudad-de-noche/">La ciudad de noche</a></article>
    <article><a href="/opinion/hector-de-mauleon/el-barrio-perdido/">El barrio perdido</a></article>
    <a href="/autores/hector-de-mauleon/">Todos sus art&iacute;culos</a>
  </div>
</body></html>
"""

ELFINANCIERO_ARTICLE = """
<html><head><title>Estrictamente Personal</title></head><body>
<script>
window.Fusion = {};
Fusion.globalContent = {"headlines":{"basic":"Estrictamente Personal: el reacomodo"},
"description":{"basic":"Un resumen del texto."},
"canonical_url":"/opinion/raymundo-riva-palacio/2025/03/12/el-reacomodo/",
"publish_date":"2025-03-12T06:00:00Z",
"credits":{"by":[{"name":"Raymundo Riva Palacio"}]},
"content_elements":[
 {"type":"text","content":"El reacomodo en Palacio Nacional comenz&oacute; hace tres semanas."},
 {"type":"header","content":"El fondo del asunto"},
 {"type":"text","content":"La cifra que importa es el 22% del presupuesto, seg&uacute;n la <a href=\\"https://shcp.test\\">SHCP</a>."},
 {"type":"text","content":"Nadie en el gabinete quiso confirmarlo por escrito."}
]};
Fusion.deployment = "1";
</script>
</body></html>
"""

REFORMA_PAYWALLED = """
<html><head>
  <meta property="og:title" content="La ley y la trampa">
  <link rel="canonical" href="https://www.reforma.com/la-ley-y-la-trampa/ar2987654">
</head><body>
  <div class="gs_texto">
    <p>El primer p&aacute;rrafo visible antes del muro de pago.</p>
  </div>
  <div class="paywall">Suscr&iacute;bete para continuar leyendo</div>
</body></html>
"""

REFORMA_FULL = """
<html><head>
  <meta property="og:title" content="La ley y la trampa">
  <meta property="article:published_time" content="2025-03-10T07:00:00-06:00">
  <link rel="canonical" href="https://www.reforma.com/la-ley-y-la-trampa/ar2987654">
</head><body>
  <div class="gs_texto">
    <p>%s</p>
    <p>%s</p>
    <p>%s</p>
  </div>
</body></html>
""" % (
    "La discusión sobre la reforma judicial ha ocupado los últimos meses del debate público mexicano y "
    "conviene detenerse en sus supuestos más elementales antes de continuar. " * 5,
    "El argumento central de quienes la defienden descansa en una premisa que rara vez se examina con calma "
    "y que merece una revisión detenida. " * 5,
    "Queda por ver si el Tribunal Electoral tendrá algo que decir sobre el asunto en las próximas semanas. " * 5,
)

REFORMA_AUTHOR_PAGE = """
<html><body>
  <a href="/la-ley-y-la-trampa/ar2987654">La ley y la trampa</a>
  <a href="/otra-columna/ar2987000">Otra columna</a>
  <a href="/suscripciones/">Suscr&iacute;bete</a>
</body></html>
"""

RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Opini&oacute;n</title>
  <item>
    <title>Columna del lunes</title>
    <link>https://diariox.test/opinion/2025/03/10/columna-del-lunes/</link>
    <pubDate>Mon, 10 Mar 2025 12:00:00 GMT</pubDate>
    <description>Resumen del lunes</description>
  </item>
  <item>
    <title>Columna del martes</title>
    <link>https://diariox.test/opinion/2025/03/11/columna-del-martes/</link>
    <pubDate>Tue, 11 Mar 2025 12:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""

PAGE_WITH_FEED_LINK = """
<html><head>
  <link rel="alternate" type="application/rss+xml" href="/opinion/feed/">
</head><body><p>Hola</p></body></html>
"""
