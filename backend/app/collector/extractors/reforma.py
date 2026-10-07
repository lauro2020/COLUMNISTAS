"""Extractor de Reforma (reforma.com).

Columnista semilla: Jesús Silva-Herzog Márquez.
Página de autor: https://www.reforma.com/jesus-silva-herzog-marquez/

Particularidades de Reforma:
  * Prácticamente todo su contenido es de pago. Sin una sesión de suscriptor
    solo se obtienen titular y primeras líneas.
  * El sitio pinta buena parte del contenido con JavaScript, por lo que se
    marca `needs_browser = True`.

Las cookies de tu suscripción se guardan CIFRADAS desde la pantalla de
Configuración y se inyectan aquí automáticamente (ver `Fetcher`).
Se usan únicamente para leer contenido al que ya tienes derecho.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef, ExtractedArticle
from app.collector.extractors.generic import GenericExtractor

# Reforma usa dos formas de dirección de artículo:
#   /titulo-de-la-nota/ar1234567                 (notas)
#   /titulo-de-la-columna-2026-10-06/op322086    (columnas de opinión)
ARTICLE_RE = re.compile(r"/(?:ar|op)\d{5,}", re.IGNORECASE)

# Cuando no reconoce una sesión de suscriptor, Reforma redirige a su pantalla
# de acceso. Detectarlo permite decir qué pasa en vez de "no encontré nada".
LOGIN_PATH_RE = re.compile(r"/libre/acceso/|/acceso/|accesofb", re.IGNORECASE)

#: Páginas de Reforma que reúnen columnas de MUCHOS autores («Hoy opinan»).
#: En ellas hay que quedarse solo con las del columnista que se recolecta: si
#: no, se guardarían las de todos con el nombre de uno.
SECTION_PATHS = {"/editoriales", "/opinion"}


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni signos: «Silva-Herzog» -> «silva herzog»."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_acentos.lower()).split())


def _clave_de_nombre(nombre: str) -> str:
    """Nombre y primer apellido: «Carlos Elizondo Mayer-Serra» -> «carlos elizondo».

    Reforma firma a veces con el apellido completo y a veces abreviado, así
    que se compara solo el comienzo.
    """
    return " ".join(_normalizar(nombre).split()[:2])


def es_pagina_de_seccion(url: str) -> bool:
    return urlparse(url or "").path.rstrip("/").lower() in SECTION_PATHS


LOGIN_MESSAGE = (
    "Reforma redirigió a su pantalla de acceso: no reconoció una sesión de "
    "suscriptor. Guarda las cookies de tu suscripción en "
    "Ajustes › Credenciales, con el medio escrito exactamente «Reforma». "
    "Si ya las guardaste, seguramente caducaron: vuelve a copiarlas."
)


def is_login_gate(final_url: str, html: str) -> bool:
    """¿Nos mandaron a la pantalla de acceso en vez de al contenido?"""
    if LOGIN_PATH_RE.search(final_url or ""):
        return True
    # Página de acceso servida sin redirección: es corta y pide iniciar sesión
    if len(html or "") < 20000 and re.search(
        r"(inicia sesi[óo]n|iniciar sesi[óo]n|accesofb)", html or "", re.IGNORECASE
    ):
        return True
    return False


class ReformaExtractor(GenericExtractor):
    key = "reforma"
    domains = ("reforma.com",)
    outlet = "Reforma"
    needs_browser = True

    BODY_SELECTORS = [
        "div.gs_texto",
        "#gs_texto",
        "div.cuerpo-nota",
        "[itemprop='articleBody']",
        "article .text-container",
        "div.text-container",
    ]

    def discover(self, source_url: str, fetcher) -> list[ArticleRef]:
        result = fetcher.get(source_url, use_browser=self.needs_browser)
        if not result.ok:
            raise RuntimeError(result.error or "no se pudo abrir la página del autor")
        if is_login_gate(result.url, result.text):
            raise RuntimeError(LOGIN_MESSAGE)
        return self.discover_from_html(result.text, result.url)

    def extract(self, url: str, fetcher):
        result = fetcher.get(url, use_browser=self.needs_browser)
        if not result.ok:
            raise RuntimeError(result.error or "no se pudo abrir el artículo")
        if is_login_gate(result.url, result.text):
            raise RuntimeError(LOGIN_MESSAGE)
        return self.extract_from_html(result.text, result.url)

    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        refs: dict[str, ArticleRef] = {}

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not ARTICLE_RE.search(href):
                continue
            url = normalize.canonicalize_url(href, base_url)
            if "reforma.com" not in url:
                continue
            title = anchor.get_text(" ", strip=True)
            if url not in refs or (title and not refs[url].title):
                refs[url] = ArticleRef(url=url, title=title or None)

        if refs and self.author_hint and es_pagina_de_seccion(base_url):
            refs = self._solo_del_autor(soup, refs, base_url)

        if refs:
            return list(refs.values())[:25]
        if self.author_hint and es_pagina_de_seccion(base_url):
            # Hoy no firma nada: no se recurre al genérico, que devolvería
            # enlaces de otros autores.
            return []
        return super().discover_from_html(html, base_url)

    def _solo_del_autor(self, soup, refs: dict, base_url: str) -> dict:
        """Deja los artículos cuya «tarjeta» nombra al columnista.

        En la página de sección cada columna es una tarjeta (foto, firma,
        título, extracto). La firma no es un enlace aparte: está en la misma
        tarjeta que el enlace al artículo. Para cada artículo se sube desde
        su enlace hasta el contenedor más grande que aún contenga UN solo
        artículo; ese es su texto, y ahí tiene que aparecer el columnista.
        """
        clave = _clave_de_nombre(self.author_hint or "")
        if not clave:
            return refs

        def ruta(href: str) -> str:
            return normalize.canonicalize_url(href, base_url)

        propios: dict = {}
        for anchor in soup.find_all("a", href=True):
            if not ARTICLE_RE.search(anchor["href"]):
                continue
            url = ruta(anchor["href"].strip())
            if url not in refs:
                continue
            tarjeta = anchor
            while tarjeta.parent is not None and tarjeta.parent.name not in ("body", "html", "[document]"):
                padre = tarjeta.parent
                distintos = {
                    ruta(a["href"].strip())
                    for a in padre.find_all("a", href=True)
                    if ARTICLE_RE.search(a["href"])
                }
                if len(distintos) > 1:
                    break
                tarjeta = padre
            if clave in _normalizar(tarjeta.get_text(" ", strip=True)):
                propios[url] = refs[url]
        return propios

    def extract_from_html(self, html: str, url: str) -> ExtractedArticle | None:
        soup = BeautifulSoup(html, "lxml")

        blocks: list[dict] = []
        for selector in self.BODY_SELECTORS:
            node = soup.select_one(selector)
            if not node:
                continue
            candidate = normalize.html_to_blocks(str(node), url)
            if candidate:
                blocks = candidate
                break

        if not blocks:
            article = super().extract_from_html(html, url)
            if article:
                article.outlet = self.outlet
                article.extractor = self.key
                if not article.blocks:
                    article.is_paywalled = True
            return article

        text = normalize.blocks_to_text(blocks)
        words = normalize.count_words(text)
        return ExtractedArticle(
            title=(normalize.extract_title(soup) or "Sin título").strip(),
            canonical_url=normalize.extract_canonical(soup, url),
            original_url=url,
            blocks=blocks,
            author=self._author(soup),
            outlet=self.outlet,
            published_at=dates.extract_published_at(soup, html),
            summary=normalize.extract_description(soup) or normalize.make_summary(text),
            # Reforma trunca a ~2 párrafos cuando no reconoce la sesión
            is_paywalled=normalize.looks_paywalled(text, words) or words < 200,
            extractor=self.key,
        )
