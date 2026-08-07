"""Pruebas de los extractores (sin tocar la red)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.collector.http_client import Fetcher
from app.config import settings

from app.collector.extractors.elfinanciero import ElFinancieroExtractor
from app.collector.extractors.eluniversal import ElUniversalExtractor
from app.collector.extractors.generic import GenericExtractor
from app.collector.extractors.reforma import ReformaExtractor
from app.collector.extractors.registry import extractor_keys, get_extractor
from tests import fixtures


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr(settings, "request_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "respect_robots", False)
    monkeypatch.setattr(settings, "max_retries", 1)
    monkeypatch.setattr(Fetcher, "_backoff", staticmethod(lambda attempt: None))


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
def test_el_registro_encuentra_los_extractores():
    keys = extractor_keys()
    assert {"generic", "eluniversal", "elfinanciero", "reforma"} <= set(keys)


@pytest.mark.parametrize(
    "url,esperado",
    [
        ("https://www.eluniversal.com.mx/autores/hector-de-mauleon/", "eluniversal"),
        ("https://www.elfinanciero.com.mx/opinion/raymundo-riva-palacio/", "elfinanciero"),
        ("https://www.reforma.com/jesus-silva-herzog-marquez/", "reforma"),
        ("https://un-medio-desconocido.test/autor/x/", "generic"),
    ],
)
def test_se_elige_el_extractor_por_dominio(url, esperado):
    assert get_extractor(url).key == esperado


def test_se_puede_forzar_un_extractor():
    assert get_extractor("https://loquesea.test/", "reforma").key == "reforma"


# ---------------------------------------------------------------------------
# Genérico
# ---------------------------------------------------------------------------
def test_generico_extrae_y_limpia():
    article = GenericExtractor().extract_from_html(
        fixtures.GENERIC_ARTICLE, "https://diariox.test/opinion/la-columna-de-prueba"
    )
    assert article is not None
    assert article.title == "La columna de prueba"
    assert article.canonical_url == "https://diariox.test/opinion/la-columna-de-prueba"
    assert article.published_at is not None
    assert article.published_at.year == 2025
    assert len(article.blocks) >= 3
    assert not article.is_paywalled

    texto = " ".join(b["text"] for b in article.blocks).lower()
    assert "anuncio molesto" not in texto


def test_generico_descubre_enlaces_de_articulos():
    refs = GenericExtractor().discover_from_html(
        fixtures.AUTHOR_PAGE, "https://diariox.test/autores/alguien/"
    )
    urls = {r.url for r in refs}
    assert "https://diariox.test/opinion/2025/03/12/la-primera-columna" in urls
    assert len(refs) == 3, "no debe colar la página de otro autor ni la de suscripciones"


# ---------------------------------------------------------------------------
# El Universal
# ---------------------------------------------------------------------------
def test_eluniversal_extrae_el_cuerpo():
    article = ElUniversalExtractor().extract_from_html(
        fixtures.ELUNIVERSAL_ARTICLE,
        "https://www.eluniversal.com.mx/opinion/hector-de-mauleon/la-ciudad-de-noche/",
    )
    assert article is not None
    assert article.outlet == "El Universal"
    assert article.extractor == "eluniversal"
    assert len(article.blocks) == 3
    assert "lee también" not in " ".join(b["text"] for b in article.blocks).lower()


def test_eluniversal_descubre_columnas():
    refs = ElUniversalExtractor().discover_from_html(
        fixtures.ELUNIVERSAL_AUTHOR_PAGE,
        "https://www.eluniversal.com.mx/autores/hector-de-mauleon/",
    )
    urls = {r.url for r in refs}
    assert "https://eluniversal.com.mx/opinion/hector-de-mauleon/la-ciudad-de-noche" in urls
    assert all("/autores/" not in u for u in urls)


# ---------------------------------------------------------------------------
# El Financiero (Arc / Fusion)
# ---------------------------------------------------------------------------
def test_elfinanciero_usa_el_json_incrustado():
    article = ElFinancieroExtractor().extract_from_html(
        fixtures.ELFINANCIERO_ARTICLE,
        "https://www.elfinanciero.com.mx/opinion/raymundo-riva-palacio/2025/03/12/el-reacomodo/",
    )
    assert article is not None
    assert article.title == "Estrictamente Personal: el reacomodo"
    assert article.author == "Raymundo Riva Palacio"
    assert article.outlet == "El Financiero"
    assert article.published_at.year == 2025

    tipos = [b["type"] for b in article.blocks]
    assert "h2" in tipos, "los encabezados de Arc se mapean a subtítulos"
    assert len(article.blocks) == 4


# ---------------------------------------------------------------------------
# Reforma
# ---------------------------------------------------------------------------
def test_reforma_detecta_el_muro_de_pago():
    article = ReformaExtractor().extract_from_html(
        fixtures.REFORMA_PAYWALLED, "https://www.reforma.com/la-ley-y-la-trampa/ar2987654"
    )
    assert article is not None
    assert article.is_paywalled is True


def test_reforma_con_sesion_extrae_todo():
    article = ReformaExtractor().extract_from_html(
        fixtures.REFORMA_FULL, "https://www.reforma.com/la-ley-y-la-trampa/ar2987654"
    )
    assert article is not None
    assert article.is_paywalled is False
    assert len(article.blocks) == 3
    assert article.outlet == "Reforma"


def test_reforma_descubre_por_patron_de_url():
    refs = ReformaExtractor().discover_from_html(
        fixtures.REFORMA_AUTHOR_PAGE, "https://www.reforma.com/jesus-silva-herzog-marquez/"
    )
    urls = {r.url for r in refs}
    assert len(refs) == 2, "solo las URLs con /arNNNNNNN son artículos"
    assert all("/ar" in u for u in urls)


# ---------------------------------------------------------------------------
# Robustez: un extractor roto no debe tumbar el sistema
# ---------------------------------------------------------------------------
def test_html_vacio_no_revienta():
    assert GenericExtractor().extract_from_html("", "https://x.test/a") is None
    assert GenericExtractor().discover_from_html("", "https://x.test/a") == []


def test_html_corrupto_no_revienta():
    roto = "<html><body><div><p>uno<p>dos</div"
    resultado = GenericExtractor().extract_from_html(roto, "https://x.test/a")
    assert resultado is None or resultado.blocks is not None


# ---------------------------------------------------------------------------
# Reforma: pantalla de acceso
# ---------------------------------------------------------------------------
from app.collector.extractors.reforma import is_login_gate  # noqa: E402


def test_se_detecta_la_pantalla_de_acceso_de_reforma():
    # Lo que devolvió de verdad: 302 a /libre/acceso/accesofb.htm
    assert is_login_gate(
        "https://www.reforma.com/libre/acceso/accesofb.htm?urlredirect=/autor/", ""
    ) is True
    assert is_login_gate(
        "https://www.reforma.com/autor/", "<html>Inicia sesión para continuar</html>"
    ) is True


def test_una_pagina_normal_no_se_confunde_con_la_de_acceso():
    assert is_login_gate(
        "https://www.reforma.com/la-ley-y-la-trampa/ar2987654", fixtures.REFORMA_FULL
    ) is False


# ---------------------------------------------------------------------------
# Semilla
# ---------------------------------------------------------------------------
from app.seed import SEED_COLUMNISTS  # noqa: E402


def test_la_semilla_no_tiene_columnistas_repetidos():
    claves = [(c["name"], c["outlet"]) for c in SEED_COLUMNISTS]
    assert len(claves) == len(set(claves)), "la clave única es (nombre, medio)"


def test_todas_las_urls_de_la_semilla_son_absolutas():
    for entrada in SEED_COLUMNISTS:
        assert entrada["source_url"].startswith("https://"), entrada["name"]


def test_los_extractores_indicados_en_la_semilla_existen():
    disponibles = set(extractor_keys())
    for entrada in SEED_COLUMNISTS:
        clave = entrada["extractor_key"]
        if clave:
            assert clave in disponibles, f"{entrada['name']} pide «{clave}»"


def test_el_extractor_indicado_coincide_con_el_dominio():
    for entrada in SEED_COLUMNISTS:
        clave = entrada["extractor_key"]
        if clave:
            elegido = get_extractor(entrada["source_url"]).key
            assert elegido == clave, f"{entrada['name']}: {elegido} != {clave}"


def test_milenio_llega_con_identidad_de_navegador():
    """Milenio devuelve 403 al robot; se comprobó en la práctica."""
    milenio = [c for c in SEED_COLUMNISTS if c["outlet"] == "Milenio"]
    assert milenio, "debe haber columnistas de Milenio"
    assert all(c["browser_identity"] for c in milenio)


def test_las_fuentes_sin_url_de_autor_llegan_desactivadas():
    """Sin página de autor no se puede recolectar: mejor inactiva y avisando."""
    for entrada in SEED_COLUMNISTS:
        if not entrada["active"]:
            assert "DESACTIVADO" in (entrada["notes"] or ""), entrada["name"]


# ---------------------------------------------------------------------------
# Redirecciones que cambian de página: no son del autor
# ---------------------------------------------------------------------------
from app.collector.extractors.generic import redirected_away  # noqa: E402


@pytest.mark.parametrize("pedida,final,esperado", [
    # Casos reales observados en producción
    ("https://www.elfinanciero.com.mx/opinion/jorge-castaneda/",
     "https://www.elfinanciero.com.mx/opinion/", True),
    ("https://www.razon.com.mx/autor/javier-solorzano-zinser/",
     "https://www.razon.com.mx", True),
    # Cambiar de dominio (www) o bajar a una subruta es legítimo
    ("https://www.codigomagenta.com.mx/seccion/que-alguien-me-explique/",
     "https://codigomagenta.com.mx/seccion/que-alguien-me-explique/", False),
    ("https://medio.test/autores/x/", "https://medio.test/autores/x/pagina/2", False),
    ("https://medio.test/autores/x/", "https://medio.test/autores/x/", False),
])
def test_se_detecta_cuando_el_medio_nos_manda_a_otra_pagina(pedida, final, esperado):
    assert redirected_away(pedida, final) is esperado


def test_discover_avisa_en_vez_de_recolectar_columnas_ajenas():
    """Si la página de autor redirige a la sección, hay que parar y avisar."""
    class FetcherFalso:
        def get(self, url, **kwargs):
            from app.collector.http_client import FetchResult
            return FetchResult(
                url="https://medio.test/opinion/",   # <- la sección, no el autor
                status_code=200, text=fixtures.AUTHOR_PAGE, ok=True,
            )

    with pytest.raises(RuntimeError, match="ya no es suya"):
        GenericExtractor().discover("https://medio.test/opinion/fulano/", FetcherFalso())


def test_se_prefieren_los_enlaces_que_cuelgan_de_la_ruta_del_autor():
    html = """
    <html><body><main>
      <a href="/opinion/fulano/2026/08/04/su-columna-de-hoy/">Su columna de hoy</a>
      <a href="/opinion/fulano/2026/08/01/otra-columna-suya/">Otra columna suya</a>
      <a href="/opinion/mengano/2026/08/04/columna-de-otro/">Columna de otro</a>
      <a href="/politica/2026/08/04/una-nota-cualquiera/">Una nota cualquiera</a>
    </main></body></html>
    """
    refs = GenericExtractor().discover_from_html(html, "https://medio.test/opinion/fulano/")
    urls = {r.url for r in refs}

    assert len(refs) == 2
    assert all("/opinion/fulano/" in u for u in urls)
    assert not any("mengano" in u for u in urls)


def test_si_nada_cuelga_de_la_ruta_del_autor_no_se_filtra_nada():
    """El Universal lista en /autores/x/ pero publica en /opinion/x/: no filtrar."""
    html = """
    <html><body><main>
      <a href="/opinion/fulano/una-columna-larga-de-verdad/">Una columna</a>
      <a href="/opinion/fulano/otra-columna-larga-de-verdad/">Otra columna</a>
    </main></body></html>
    """
    refs = GenericExtractor().discover_from_html(html, "https://medio.test/autores/fulano/")
    assert len(refs) == 2


# ---------------------------------------------------------------------------
# El Financiero: listados que no vienen en Fusion.globalContent
# ---------------------------------------------------------------------------
def test_elfinanciero_encuentra_columnas_por_ruta_canonica():
    """Riva Palacio y Schettino devolvían 0 con solo mirar Fusion.globalContent."""
    html = """
    <html><body><script>
      var a = {"canonical_url":"/opinion/raymundo-riva-palacio/2026/08/04/el-reacomodo/"};
      var b = {"canonical_url":"\\/opinion\\/raymundo-riva-palacio\\/2026\\/08\\/01\\/otra\\/"};
      var c = {"canonical_url":"/opinion/otro-autor/2026/08/03/no-es-suya/"};
      var d = {"canonical_url":"/opinion/"};
    </script></body></html>
    """
    refs = ElFinancieroExtractor().discover_from_html(
        html, "https://www.elfinanciero.com.mx/opinion/raymundo-riva-palacio/"
    )
    urls = {r.url for r in refs}

    assert len(refs) == 2, "solo sus dos columnas"
    assert all("raymundo-riva-palacio" in u for u in urls)
    assert not any("otro-autor" in u for u in urls)


# ---------------------------------------------------------------------------
# Una columna suelta no es la página del autor
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url,es_columna", [
    ("https://www.razon.com.mx/opinion/2026/08/06/michoacan/", True),
    ("https://www.elfinanciero.com.mx/opinion/quien/2026/08/06/titular/", True),
    ("https://www.razon.com.mx/autor/javier-solorzano-zinser/", False),
    ("https://www.eluniversal.com.mx/opinion/jorge-castaneda/", False),
    ("https://www.elfinanciero.com.mx/opinion/macario-schettino/", False),
])
def test_se_distingue_una_columna_de_la_pagina_del_autor(url, es_columna):
    from app.collector.extractors.generic import looks_like_single_article

    assert looks_like_single_article(url) is es_columna


def test_de_una_columna_se_saca_la_pagina_de_su_autor():
    """Al pegar la dirección de una columna, poder responder con la buena."""
    from app.collector.extractors.generic import author_pages_in

    html = """
    <html><body>
      <article>
        <span class="byline"><a href="/autor/javier-solorzano/">Javier Solórzano</a></span>
        <p>El cuerpo de la columna.</p>
        <a href="/opinion/2026/08/05/otra-columna/">Otra columna</a>
        <a href="https://twitter.com/alguien">Twitter</a>
      </article>
    </body></html>
    """
    encontradas = author_pages_in(html, "https://www.razon.com.mx/opinion/2026/08/06/michoacan/")

    # canonicalize_url quita el «www.»
    assert "https://razon.com.mx/autor/javier-solorzano" in encontradas
    assert not any("twitter" in u for u in encontradas)


@respx.mock
def test_pegar_una_columna_en_vez_de_la_pagina_del_autor_se_rechaza():
    """Aceptarla sería peor: colgarían de ahí notas de otras personas."""
    from app.collector.extractors.generic import GenericExtractor

    url = "https://www.razon.com.mx/opinion/2026/08/06/michoacan/"
    respx.get(url).mock(return_value=httpx.Response(200, text="""
        <html><body><article>
          <span class="byline"><a href="/autor/javier-solorzano/">Javier Solórzano</a></span>
          <a href="/opinion/2026/08/05/nota-de-otro-autor/">Nota de otro</a>
        </article></body></html>
    """))

    with Fetcher() as fetcher, pytest.raises(RuntimeError) as fallo:
        GenericExtractor().discover(url, fetcher)

    mensaje = str(fallo.value)
    assert "UNA columna concreta" in mensaje
    assert "/autor/javier-solorzano" in mensaje, "debe ofrecer la dirección buena"


def test_el_universal_no_mezcla_columnas_de_otros_autores():
    """En /opinion/<autor>/ las columnas cuelgan de esa misma ruta."""
    from app.collector.extractors.eluniversal import ElUniversalExtractor

    base = "https://www.eluniversal.com.mx/opinion/jorge-castaneda/"
    html = """
    <html><body>
      <article><h2><a href="/opinion/jorge-castaneda/la-columna-de-hoy/">La columna de hoy</a></h2></article>
      <article><h2><a href="/opinion/jorge-castaneda/la-columna-de-ayer/">La columna de ayer</a></h2></article>
      <aside><h3><a href="/opinion/otro-columnista/lo-que-escribio-otro/">Lo que escribió otro</a></h3></aside>
      <div class="card"><a href="/nacion/una-noticia-cualquiera/">Una noticia</a></div>
    </body></html>
    """

    refs = ElUniversalExtractor().discover_from_html(html, base)

    rutas = [r.url for r in refs]
    assert all("/opinion/jorge-castaneda/" in u for u in rutas), rutas
    assert len(rutas) == 2
