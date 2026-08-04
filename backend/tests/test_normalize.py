"""Pruebas de la normalización de HTML a texto limpio."""

from __future__ import annotations

from app.collector import normalize
from tests.fixtures import GENERIC_ARTICLE


def test_canonicalize_quita_rastreo_y_www():
    url = "https://www.diariox.test/opinion/nota/?utm_source=twitter&id=7#seccion"
    assert normalize.canonicalize_url(url) == "https://diariox.test/opinion/nota?id=7"


def test_canonicalize_resuelve_relativas():
    assert (
        normalize.canonicalize_url("/opinion/nota/", "https://diariox.test/autores/x/")
        == "https://diariox.test/opinion/nota"
    )


def test_html_to_blocks_conserva_estructura_y_enlaces():
    blocks = normalize.html_to_blocks(GENERIC_ARTICLE, "https://diariox.test/")
    tipos = [b["type"] for b in blocks]

    assert "p" in tipos
    assert "h2" in tipos, "los subtítulos deben conservarse"
    assert "quote" in tipos, "las citas deben conservarse"

    todos = " ".join(b["html"] for b in blocks)
    assert "<a href=" in todos, "los enlaces del cuerpo se conservan"


def test_html_to_blocks_elimina_ruido():
    blocks = normalize.html_to_blocks(GENERIC_ARTICLE, "https://diariox.test/")
    texto = normalize.blocks_to_text(blocks).lower()

    assert "anuncio molesto" not in texto
    assert "suscríbete" not in texto and "suscribete" not in texto
    assert "te puede interesar" not in texto
    assert "aviso de privacidad" not in texto
    assert "inicio" not in texto.split()


def test_hash_ignora_cambios_cosmeticos():
    a = normalize.content_hash("Título", "El texto  del   artículo.")
    b = normalize.content_hash("TÍTULO", "El texto del artículo!")
    assert a == b, "acentos, mayúsculas y espacios no deben cambiar el hash"

    c = normalize.content_hash("Título", "Un texto completamente distinto")
    assert a != c


def test_tiempo_de_lectura():
    assert normalize.reading_minutes(0) == 1
    assert normalize.reading_minutes(200) == 1
    assert normalize.reading_minutes(1000) == 5


def test_deteccion_de_muro_de_pago():
    assert normalize.looks_paywalled("Suscríbete para continuar leyendo", 20) is True
    assert normalize.looks_paywalled("Un texto normal y suficientemente largo", 800) is False


def test_resumen_corta_en_frase():
    texto = "Primera frase corta. Segunda frase que continúa el razonamiento del autor."
    resumen = normalize.make_summary(texto, max_chars=30)
    assert resumen.endswith(".") or resumen.endswith("…")
    assert len(resumen) <= 32
