"""Extractor genérico de respaldo.

Funciona razonablemente bien en casi cualquier medio sin escribir nada
específico. Se usa cuando (a) no hay extractor propio para ese dominio o
(b) el extractor propio falló.

Estrategia:
  discover -> busca en la página del autor los enlaces que parecen artículos
  extract  -> usa trafilatura (detección del bloque principal por densidad de
              texto) y, si falla, una heurística propia de "contenedor con más
              párrafos".
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import trafilatura
from bs4 import BeautifulSoup

from app.collector import dates, normalize
from app.collector.extractors.base import ArticleRef, BaseExtractor, ExtractedArticle
from app.collector.http_client import Fetcher

log = logging.getLogger(__name__)

# Rutas que claramente no son artículos
SKIP_PATH = re.compile(
    r"/(tag|tags|autor|autores|author|seccion|secciones|category|categoria|"
    r"buscar|search|suscri|subscri|login|registro|newsletter|video|videos|"
    r"galeria|podcast|cartones|contacto|aviso|privacidad|terminos)(/|$)",
    re.IGNORECASE,
)

# Rutas que sí parecen un artículo: /2025/03/12/algo o /algo-con-guiones-largo
ARTICLE_PATH = re.compile(r"/\d{4}/\d{2}/|/[a-z0-9]+(?:-[a-z0-9]+){2,}", re.IGNORECASE)


def redirected_away(requested: str, final: str) -> bool:
    """¿El medio nos llevó a una página distinta de la que pedimos?

    Pasa cuando una página de autor deja de existir: el medio responde 301 a la
    sección general o a la portada. Recolectar de ahí llenaría la bandeja con
    columnas de otras personas, así que hay que detectarlo y avisar.

    Cambiar de dominio (www ↔ sin www) o bajar a una subruta no cuenta.
    """
    pedida = urlparse(requested).path.rstrip("/").lower()
    llegada = urlparse(final or "").path.rstrip("/").lower()
    if not pedida or pedida == llegada:
        return False
    if llegada.startswith(pedida):
        return False
    # El medio puede reorganizar la ruta sin dejar de ser la página del autor
    # (p. ej. /opinion/fulano -> /autores/fulano). Mientras el identificador
    # del autor siga ahí, no es una redirección a otra cosa.
    slug = pedida.rsplit("/", 1)[-1]
    if len(slug) >= 6 and slug in llegada:
        return False
    return True


class GenericExtractor(BaseExtractor):
    key = "generic"
    domains = ()

    @classmethod
    def matches(cls, url: str) -> bool:
        # El genérico acepta cualquier URL. Las subclases (un medio concreto)
        # declaran sus dominios y solo aceptan los suyos.
        if cls.domains:
            return super().matches(url)
        return True

    # ------------------------------------------------------------------
    def discover(self, source_url: str, fetcher: Fetcher) -> list[ArticleRef]:
        result = fetcher.get(source_url, use_browser=self.needs_browser)
        if not result.ok:
            if not self.needs_browser:
                # Segundo intento con navegador por si el listado se pinta con JS
                result = fetcher.get(source_url, use_browser=True)
            if not result.ok:
                raise RuntimeError(result.error or "no se pudo abrir la página del autor")

        # Si el medio nos mandó a otra parte, lo que hay ahí NO es de este autor.
        if redirected_away(source_url, result.url):
            raise RuntimeError(
                f"La página de este autor redirige a «{result.url}», que ya no es "
                f"suya (suele ser la sección de opinión o la portada). Si "
                f"recolectáramos de ahí, guardaríamos columnas de otras personas. "
                f"Ábrela en el navegador, copia la dirección correcta y corrígela "
                f"en Ajustes › Columnistas › Editar."
            )

        return self.discover_from_html(result.text, result.url)

    def discover_from_html(self, html: str, base_url: str) -> list[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        host = urlparse(base_url).netloc.lower().removeprefix("www.")

        # Se ignoran menús y pies de página al buscar enlaces
        for tag in soup.find_all(["nav", "footer", "header", "aside"]):
            tag.decompose()

        refs: dict[str, ArticleRef] = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if href.startswith(("#", "mailto:", "javascript:", "tel:")):
                continue
            absolute = normalize.canonicalize_url(href, base_url)
            parsed = urlparse(absolute)
            link_host = parsed.netloc.lower().removeprefix("www.")
            if link_host != host:
                continue
            if SKIP_PATH.search(parsed.path):
                continue
            if not ARTICLE_PATH.search(parsed.path):
                continue
            if absolute.rstrip("/") == normalize.canonicalize_url(base_url).rstrip("/"):
                continue

            title = anchor.get_text(" ", strip=True)
            if absolute in refs and not title:
                continue
            refs[absolute] = ArticleRef(
                url=absolute, title=title if len(title) > 12 else None
            )

        return self._prefer_author_paths(list(refs.values()), base_url)[:25]

    @staticmethod
    def _prefer_author_paths(refs: list[ArticleRef], base_url: str) -> list[ArticleRef]:
        """Si el medio cuelga los artículos bajo la ruta del autor, quedarse con esos.

        Muchos periódicos usan `/opinion/<autor>/<titular>`. En esas páginas los
        enlaces a columnas de OTRAS personas (los del sidebar, «lo más leído»…)
        no cuelgan de esa ruta, así que filtrarlos evita atribuirle a alguien lo
        que no escribió. Si el medio no sigue ese esquema, no se filtra nada.
        """
        prefijo = urlparse(base_url).path.rstrip("/").lower()
        if not prefijo or prefijo == "/":
            return refs
        propios = [
            r for r in refs
            if urlparse(r.url).path.lower().startswith(f"{prefijo}/")
        ]
        return propios or refs

    # ------------------------------------------------------------------
    def extract(self, url: str, fetcher: Fetcher) -> ExtractedArticle | None:
        result = fetcher.get(url, use_browser=self.needs_browser)
        if not result.ok and not self.needs_browser:
            result = fetcher.get(url, use_browser=True)
        if not result.ok:
            raise RuntimeError(result.error or "no se pudo abrir el artículo")
        return self.extract_from_html(result.text, result.url)

    def extract_from_html(self, html: str, url: str) -> ExtractedArticle | None:
        soup = BeautifulSoup(html, "lxml")

        blocks = self._trafilatura_blocks(html, url)
        if len(blocks) < 2:
            blocks = self._densest_container_blocks(soup, url)
        if not blocks:
            return None

        title = normalize.extract_title(soup) or (blocks[0]["text"][:120] if blocks else "Sin título")
        # Si el primer bloque repite el titular, se elimina para no leerlo dos veces
        if blocks and normalize.normalize_for_hash(blocks[0]["text"]) == normalize.normalize_for_hash(title):
            blocks = blocks[1:]

        text = normalize.blocks_to_text(blocks)
        words = normalize.count_words(text)

        return ExtractedArticle(
            title=title.strip(),
            canonical_url=normalize.extract_canonical(soup, url),
            original_url=url,
            blocks=blocks,
            author=self._author(soup),
            published_at=dates.extract_published_at(soup, html),
            summary=normalize.extract_description(soup) or normalize.make_summary(text),
            is_paywalled=normalize.looks_paywalled(text, words),
            extractor=self.key,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _trafilatura_blocks(html: str, url: str) -> list[dict]:
        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                output_format="html",
                include_links=True,
                include_formatting=True,
                include_comments=False,
                include_tables=False,
                include_images=False,
                favor_precision=True,
                deduplicate=True,
            )
        except Exception as exc:  # noqa: BLE001 - trafilatura puede fallar con HTML raro
            log.debug("trafilatura falló en %s: %s", url, exc)
            return []
        if not extracted:
            return []
        return normalize.html_to_blocks(extracted, url)

    @staticmethod
    def _densest_container_blocks(soup: BeautifulSoup, url: str) -> list[dict]:
        """Elige el contenedor con más texto en párrafos."""
        best, best_score = None, 0
        candidates = soup.select(
            "article, main, [itemprop='articleBody'], [class*='cuerpo'], "
            "[class*='content'], [class*='article'], [class*='nota'], div"
        )
        for node in candidates:
            paragraphs = node.find_all("p", recursive=True)
            if len(paragraphs) < 3:
                continue
            score = sum(len(p.get_text(strip=True)) for p in paragraphs)
            # Penaliza contenedores gigantes que envuelven toda la página
            if node.name == "div" and len(node.find_all("a")) > len(paragraphs) * 3:
                score *= 0.3
            if score > best_score:
                best, best_score = node, score
        if best is None:
            return []
        return normalize.html_to_blocks(str(best), url)

    @staticmethod
    def _author(soup: BeautifulSoup) -> str | None:
        for selector, attr in [
            ('meta[name="author"]', "content"),
            ('meta[property="article:author"]', "content"),
            ('[itemprop="author"]', None),
            ('[rel="author"]', None),
            ('[class*="autor"]', None),
            ('[class*="author"]', None),
        ]:
            node = soup.select_one(selector)
            if not node:
                continue
            value = node.get(attr) if attr else node.get_text(" ", strip=True)
            if value and 3 < len(value.strip()) < 80:
                return value.strip()
        return None
