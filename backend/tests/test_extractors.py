"""Pruebas de los extractores (sin tocar la red)."""

from __future__ import annotations

import pytest

from app.collector.extractors.elfinanciero import ElFinancieroExtractor
from app.collector.extractors.eluniversal import ElUniversalExtractor
from app.collector.extractors.generic import GenericExtractor
from app.collector.extractors.reforma import ReformaExtractor
from app.collector.extractors.registry import extractor_keys, get_extractor
from tests import fixtures


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
