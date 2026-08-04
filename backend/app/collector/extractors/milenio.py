"""Extractor de Milenio (milenio.com).

Columnistas semilla: Héctor Aguilar Camín, Joaquín López-Dóriga,
Francisco Abundis.

Particularidad comprobada en la práctica: Milenio responde **403 a cualquier
cliente que no sea un navegador**, incluso para servir su `robots.txt`. Por eso:

  * los columnistas de Milenio vienen con «Identificarse como navegador»
    activado en la semilla, y
  * este extractor declara `needs_browser = True`, de modo que si tienes el
    navegador headless habilitado se use directamente.

Si el sitio sigue rechazando la petición incluso desde Chromium, está
bloqueando de forma activa la lectura automatizada y no hay forma razonable de
recolectarlo: la pantalla de Fuentes lo dirá con esas palabras.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef, ExtractedArticle
from app.collector.extractors.generic import GenericExtractor

# Milenio usa /opinion/<autor>/<seccion>/<slug> y /politica/<slug>
ARTICLE_RE = re.compile(r"/(opinion|politica|negocios|estados|cultura|policia)/", re.I)


class MilenioExtractor(GenericExtractor):
    key = "milenio"
    domains = ("milenio.com",)
    outlet = "Milenio"
    needs_browser = True

    BODY_SELECTORS = [
        "div.content-body",
        "div.nota-cuerpo",
        "[itemprop='articleBody']",
        "div.article-body",
        "section.content",
    ]

    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        refs: dict[str, ArticleRef] = {}

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if href.startswith(("#", "mailto:", "javascript:")):
                continue
            url = normalize.canonicalize_url(href, base_url)
            if "milenio.com" not in url or not ARTICLE_RE.search(url):
                continue
            if url.rstrip("/") == normalize.canonicalize_url(base_url).rstrip("/"):
                continue
            # La página del autor enlaza a sí misma y a la sección de opinión
            if url.rstrip("/").endswith("/opinion"):
                continue
            title = anchor.get_text(" ", strip=True)
            if url not in refs or (title and not refs[url].title):
                refs[url] = ArticleRef(url=url, title=title or None)

        if refs:
            return list(refs.values())[:25]
        return super().discover_from_html(html, base_url)

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
                    summary=normalize.extract_description(soup) or normalize.make_summary(text),
                    is_paywalled=normalize.looks_paywalled(
                        text, normalize.count_words(text)
                    ),
                    extractor=self.key,
                )

        article = super().extract_from_html(html, url)
        if article:
            article.outlet = self.outlet
            article.extractor = self.key
        return article
