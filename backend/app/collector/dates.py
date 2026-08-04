"""Detección de la fecha de publicación.

Se intenta, en este orden:
  1. JSON-LD (`datePublished`)
  2. Etiquetas <meta> habituales
  3. <time datetime="...">
  4. Texto en español dentro de la página ("12 de marzo de 2025")
"""

from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.config import settings

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

SPANISH_DATE = re.compile(
    r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+|del\s+)?(\d{4})", re.IGNORECASE
)

META_KEYS = [
    ('meta[property="article:published_time"]', "content"),
    ('meta[name="article:published_time"]', "content"),
    ('meta[property="og:article:published_time"]', "content"),
    ('meta[name="date"]', "content"),
    ('meta[name="pubdate"]', "content"),
    ('meta[itemprop="datePublished"]', "content"),
    ('meta[name="DC.date.issued"]', "content"),
    ("time[datetime]", "datetime"),
]


def local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def ensure_aware(value: dt.datetime | None) -> dt.datetime | None:
    """Si la fecha viene sin zona horaria se asume la del medio (México)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=local_tz())
    return value


def parse_any(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        return ensure_aware(dateparser.parse(value))
    except (ValueError, OverflowError, TypeError):
        pass
    match = SPANISH_DATE.search(value)
    if match:
        day, month_name, year = match.groups()
        month = MESES.get(month_name.lower())
        if month:
            try:
                return dt.datetime(int(year), month, int(day), tzinfo=local_tz())
            except ValueError:
                return None
    return None


def _from_jsonld(soup: BeautifulSoup) -> dt.datetime | None:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                candidates.extend(g for g in graph if isinstance(g, dict))
            for key in ("datePublished", "dateCreated", "uploadDate", "dateModified"):
                found = parse_any(item.get(key))
                if found:
                    return found
    return None


def extract_published_at(soup: BeautifulSoup, html: str = "") -> dt.datetime | None:
    found = _from_jsonld(soup)
    if found:
        return found

    for selector, attr in META_KEYS:
        node = soup.select_one(selector)
        if node:
            found = parse_any(node.get(attr) or node.get_text())
            if found:
                return found

    text = soup.get_text(" ", strip=True)[:4000]
    match = SPANISH_DATE.search(text)
    if match:
        return parse_any(match.group(0))
    return None


def today_local() -> dt.date:
    return dt.datetime.now(local_tz()).date()


def to_local(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return ensure_aware(value).astimezone(local_tz())
