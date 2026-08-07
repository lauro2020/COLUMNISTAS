"""Extractor de El Universal (eluniversal.com.mx).

Columnista semilla: Héctor de Mauleón.
Página de autor: https://www.eluniversal.com.mx/autores/hector-de-mauleon/

El Universal corre sobre Drupal: el cuerpo suele vivir en
`div.field--name-body` o en `[itemprop="articleBody"]`.
Si esos selectores dejan de existir, la clase cae sola al extractor
genérico y el sistema sigue funcionando (solo baja un poco la precisión).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef
from app.collector.extractors.generic import GenericExtractor

ARTICLE_RE = re.compile(r"/(opinion|nacion|mundo|cartera|metropoli|estados)/", re.I)


class ElUniversalExtractor(GenericExtractor):
    key = "eluniversal"
    domains = ("eluniversal.com.mx",)
    outlet = "El Universal"
    needs_browser = False

    BODY_SELECTORS = [
        "div.field--name-body",
        "[itemprop='articleBody']",
        "div.entry-content",
        "article .content",
    ]

    LIST_SELECTORS = [
        "article a[href]",
        ".view-content a[href]",
        "[class*='card'] a[href]",
        "h2 a[href], h3 a[href]",
    ]

    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        refs: dict[str, ArticleRef] = {}

        for selector in self.LIST_SELECTORS:
            for anchor in soup.select(selector):
                href = anchor.get("href", "").strip()
                if not href or href.startswith(("#", "mailto:", "javascript:")):
                    continue
                url = normalize.canonicalize_url(href, base_url)
                if "eluniversal.com.mx" not in url or not ARTICLE_RE.search(url):
                    continue
                if url.rstrip("/") == normalize.canonicalize_url(base_url).rstrip("/"):
                    continue
                title = anchor.get_text(" ", strip=True)
                if url not in refs or (title and not refs[url].title):
                    refs[url] = ArticleRef(url=url, title=title or None)

        if refs:
            # El Universal tiene dos formas de página de autor:
            # `/autores/<slug>/`, donde las columnas cuelgan de otra ruta, y
            # `/opinion/<slug>/`, donde cuelgan de la propia. En la segunda hay
            # que filtrar, o se cuelan las notas de la barra lateral y se le
            # atribuyen al columnista columnas que no escribió.
            return self._prefer_author_paths(list(refs.values()), base_url)[:25]
        return super().discover_from_html(html, base_url)

    def extract_from_html(self, html: str, url: str):
        soup = BeautifulSoup(html, "lxml")
        blocks: list[dict] = []
        for selector in self.BODY_SELECTORS:
            node = soup.select_one(selector)
            if node:
                blocks = normalize.html_to_blocks(str(node), url)
                if len(blocks) >= 2:
                    break
                blocks = []

        if not blocks:
            article = super().extract_from_html(html, url)
            if article:
                article.outlet = self.outlet
                article.extractor = self.key
            return article

        text = normalize.blocks_to_text(blocks)
        words = normalize.count_words(text)
        title = normalize.extract_title(soup) or "Sin título"

        from app.collector.extractors.base import ExtractedArticle

        return ExtractedArticle(
            title=title.strip(),
            canonical_url=normalize.extract_canonical(soup, url),
            original_url=url,
            blocks=blocks,
            author=self._author(soup),
            outlet=self.outlet,
            published_at=dates.extract_published_at(soup, html),
            summary=normalize.extract_description(soup) or normalize.make_summary(text),
            is_paywalled=normalize.looks_paywalled(text, words),
            extractor=self.key,
        )
