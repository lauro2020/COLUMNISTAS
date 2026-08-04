"""Soporte de RSS/Atom.

Siempre se prefiere el RSS cuando existe: es más rápido, más estable y
mucho más respetuoso con el medio que descargar la página del autor.
"""

from __future__ import annotations

import logging

import feedparser
from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef
from app.collector.http_client import Fetcher

log = logging.getLogger(__name__)

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json")


def discover_feed_url(html: str, base_url: str) -> str | None:
    """Busca <link rel="alternate" type="application/rss+xml"> en el <head>."""
    soup = BeautifulSoup(html, "lxml")
    for link in soup.select('link[rel="alternate"][href]'):
        if (link.get("type") or "").lower() in FEED_TYPES:
            return normalize.canonicalize_url(link["href"], base_url)
    # Rutas habituales cuando el medio no lo anuncia
    for guess in ("/feed", "/rss", "/feed/", "/rss.xml", "/index.xml"):
        candidate = normalize.canonicalize_url(guess, base_url)
        if candidate != normalize.canonicalize_url(base_url):
            return None  # se prueba explícitamente en `try_common_feeds`
    return None


def try_common_feeds(source_url: str, fetcher: Fetcher) -> str | None:
    """Prueba rutas típicas de feed sobre la URL del autor."""
    for suffix in ("feed", "rss", "feed.xml", "rss.xml"):
        candidate = source_url.rstrip("/") + "/" + suffix
        result = fetcher.get(candidate)
        if result.ok and _looks_like_feed(result.text):
            return candidate
    return None


def _looks_like_feed(text: str) -> bool:
    head = (text or "")[:600].lower()
    return "<rss" in head or "<feed" in head or "application/rss" in head


def parse_feed(feed_url: str, fetcher: Fetcher) -> list[ArticleRef]:
    result = fetcher.get(feed_url)
    if not result.ok:
        raise RuntimeError(result.error or f"no se pudo leer el feed {feed_url}")

    parsed = feedparser.parse(result.text)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"feed inválido: {getattr(parsed, 'bozo_exception', 'desconocido')}")

    refs: list[ArticleRef] = []
    for entry in parsed.entries:
        link = entry.get("link") or entry.get("id")
        if not link:
            continue
        published = (
            dates.parse_any(entry.get("published"))
            or dates.parse_any(entry.get("updated"))
            or dates.parse_any(entry.get("created"))
        )
        summary = entry.get("summary")
        if summary:
            summary = BeautifulSoup(summary, "lxml").get_text(" ", strip=True)
        refs.append(
            ArticleRef(
                url=normalize.canonicalize_url(link, feed_url),
                title=entry.get("title"),
                published_at=published,
                summary=summary,
            )
        )
    return refs
