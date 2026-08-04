"""Interfaz común de los extractores.

Añadir un medio nuevo = escribir UNA clase pequeña en este paquete.
No hay que tocar ninguna otra parte del sistema: el registro los descubre solo.

Cada extractor hace dos cosas:
  discover() -> ¿qué artículos hay publicados por este columnista?
  extract()  -> dada la URL de un artículo, devuelve su texto limpio.

Si un extractor devuelve None o lanza una excepción, el sistema cae
automáticamente al extractor genérico y, si tampoco funciona, marca esa
fuente como degradada y continúa con las demás.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.collector.http_client import Fetcher


@dataclass
class ArticleRef:
    """Un artículo detectado en la página del columnista o en su RSS."""

    url: str
    title: str | None = None
    published_at: dt.datetime | None = None
    summary: str | None = None


@dataclass
class ExtractedArticle:
    """Un artículo ya convertido a texto limpio."""

    title: str
    canonical_url: str
    blocks: list[dict] = field(default_factory=list)
    author: str | None = None
    outlet: str | None = None
    published_at: dt.datetime | None = None
    summary: str | None = None
    original_url: str | None = None
    is_paywalled: bool = False
    extractor: str = "generic"


class BaseExtractor:
    """Clase base. Hereda de aquí para añadir un medio."""

    key: str = "base"
    #: dominios que atiende, sin "www." (p. ej. ("eluniversal.com.mx",))
    domains: tuple[str, ...] = ()
    #: True si el sitio necesita JavaScript para mostrar el texto
    needs_browser: bool = False
    #: nombre legible del medio
    outlet: str | None = None

    @classmethod
    def matches(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        return any(host == d or host.endswith(f".{d}") for d in cls.domains)

    # -- a implementar por cada medio --------------------------------------
    def discover(self, source_url: str, fetcher: Fetcher) -> list[ArticleRef]:
        raise NotImplementedError

    def extract(self, url: str, fetcher: Fetcher) -> ExtractedArticle | None:
        raise NotImplementedError
