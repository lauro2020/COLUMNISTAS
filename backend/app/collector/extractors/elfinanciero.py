"""Extractor de El Financiero (elfinanciero.com.mx).

Columnista semilla: Raymundo Riva Palacio.
Página de autor: https://www.elfinanciero.com.mx/opinion/raymundo-riva-palacio/

El Financiero usa Arc Publishing (la plataforma del Washington Post). Eso
tiene una ventaja enorme: la página trae el artículo COMPLETO en un JSON
incrustado (`Fusion.globalContent`), mucho más estable que cualquier
selector CSS. Se intenta primero ese JSON y, si no está, se usan selectores
y por último el extractor genérico.
"""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef, ExtractedArticle
from app.collector.extractors.generic import GenericExtractor

log = logging.getLogger(__name__)

FUSION_RE = re.compile(
    r"Fusion\.globalContent\s*=\s*(\{.*?\});\s*Fusion\.", re.DOTALL
)
FUSION_ANY_RE = re.compile(r"Fusion\.globalContent\s*=\s*(\{.*?\});", re.DOTALL)


class ElFinancieroExtractor(GenericExtractor):
    key = "elfinanciero"
    domains = ("elfinanciero.com.mx",)
    outlet = "El Financiero"
    needs_browser = False

    BODY_SELECTORS = [
        "div.article-body",
        "[class*='article-body']",
        "[itemprop='articleBody']",
        "div.content-body",
    ]

    # ------------------------------------------------------------------
    # Descubrimiento
    # ------------------------------------------------------------------
    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        refs: dict[str, ArticleRef] = {}

        payload = self._fusion_payload(html)
        if payload:
            for item in self._iter_content_items(payload):
                url = item.get("canonical_url") or item.get("websites", {}).get(
                    "elfinanciero", {}
                ).get("website_url")
                if not url:
                    continue
                absolute = normalize.canonicalize_url(url, base_url)
                headline = (item.get("headlines") or {}).get("basic")
                published = dates.parse_any(
                    item.get("publish_date") or item.get("display_date")
                )
                refs[absolute] = ArticleRef(
                    url=absolute, title=headline, published_at=published
                )

        if refs:
            return list(refs.values())[:25]
        return super().discover_from_html(html, base_url)

    # ------------------------------------------------------------------
    # Extracción
    # ------------------------------------------------------------------
    def extract_from_html(self, html: str, url: str) -> ExtractedArticle | None:
        payload = self._fusion_payload(html)
        if payload and payload.get("content_elements"):
            article = self._from_fusion(payload, url, html)
            if article and len(article.blocks) >= 2:
                return article

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
                    is_paywalled=normalize.looks_paywalled(text, normalize.count_words(text)),
                    extractor=self.key,
                )

        article = super().extract_from_html(html, url)
        if article:
            article.outlet = self.outlet
            article.extractor = self.key
        return article

    # ------------------------------------------------------------------
    # Utilidades de Arc / Fusion
    # ------------------------------------------------------------------
    @staticmethod
    def _fusion_payload(html: str) -> dict | None:
        for pattern in (FUSION_RE, FUSION_ANY_RE):
            match = pattern.search(html or "")
            if not match:
                continue
            try:
                return json.loads(match.group(1))
            except ValueError:
                # El JSON puede venir escapado dentro de una cadena
                try:
                    return json.loads(match.group(1).encode().decode("unicode_escape"))
                except (ValueError, UnicodeDecodeError):
                    continue
        return None

    @staticmethod
    def _iter_content_items(payload: dict):
        if isinstance(payload.get("content_elements"), list):
            for item in payload["content_elements"]:
                if isinstance(item, dict) and item.get("type") in (None, "story"):
                    yield item

    def _from_fusion(self, payload: dict, url: str, html: str) -> ExtractedArticle | None:
        blocks: list[dict] = []
        for element in payload.get("content_elements", []):
            if not isinstance(element, dict):
                continue
            kind = element.get("type")
            raw = element.get("content") or ""
            if kind == "text" and raw:
                cleaned = normalize.html_to_blocks(f"<p>{raw}</p>", url)
                blocks.extend(cleaned)
            elif kind == "header" and raw:
                blocks.append({"type": "h2", "html": raw, "text": BeautifulSoup(raw, "lxml").get_text(" ", strip=True)})
            elif kind in ("quote", "blockquote") and raw:
                blocks.append({"type": "quote", "html": raw, "text": BeautifulSoup(raw, "lxml").get_text(" ", strip=True)})

        if not blocks:
            return None

        text = normalize.blocks_to_text(blocks)
        headline = (payload.get("headlines") or {}).get("basic") or "Sin título"
        author = None
        credits = (payload.get("credits") or {}).get("by") or []
        if credits and isinstance(credits[0], dict):
            author = credits[0].get("name")

        canonical = payload.get("canonical_url") or url
        return ExtractedArticle(
            title=headline.strip(),
            canonical_url=normalize.canonicalize_url(canonical, url),
            original_url=url,
            blocks=blocks,
            author=author,
            outlet=self.outlet,
            published_at=dates.parse_any(payload.get("publish_date"))
            or dates.extract_published_at(BeautifulSoup(html, "lxml"), html),
            summary=(payload.get("description") or {}).get("basic")
            or normalize.make_summary(text),
            is_paywalled=normalize.looks_paywalled(text, normalize.count_words(text)),
            extractor=self.key,
        )
