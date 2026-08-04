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

from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef, ExtractedArticle
from app.collector.extractors.generic import GenericExtractor

# Reforma usa URLs tipo /titulo-de-la-columna/ar1234567
ARTICLE_RE = re.compile(r"/ar\d{5,}", re.IGNORECASE)


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

        if refs:
            return list(refs.values())[:25]
        return super().discover_from_html(html, base_url)

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
