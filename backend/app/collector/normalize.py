"""Normalización: de HTML sucio a un cuerpo limpio y estructurado.

El resultado es una lista de bloques:
    [{"type": "p", "html": "Texto con <a href=...>enlace</a>.", "text": "Texto con enlace."}]

`type` puede ser: p (párrafo), h2/h3 (subtítulo), quote (cita), li (lista).
Los enlaces, las citas y los subtítulos se conservan; los anuncios, banners
de suscripción, "contenido relacionado" y menús de navegación se eliminan.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, NavigableString, Tag

# Etiquetas que nunca forman parte de una columna
DROP_TAGS = {
    "script", "style", "noscript", "iframe", "svg", "form", "button",
    "nav", "aside", "footer", "header", "video", "audio", "picture",
    "figure", "figcaption", "table", "input", "select", "ins",
}

# Palabras que delatan bloques de ruido en class/id
NOISE_PATTERN = re.compile(
    r"(publicidad|advertis|ad-|-ad\b|adsense|banner|newsletter|suscri|subscri|"
    r"paywall|premium-?wall|relacionad|related|te-puede|lee-tambien|leer-mas|"
    r"mas-noticias|compartir|share|social|redes|comment|coment|disqus|tags?\b|"
    r"breadcrumb|menu|navbar|sidebar|widget|promo|cookie|modal|popup|"
    r"autor-?box|author-?bio|firma-?autor|siguenos|follow-us|toolbar|"
    r"galeria|slider|carousel|video-?player|más-?leídas|mas-?leidas)",
    re.IGNORECASE,
)

INLINE_ALLOWED = {"a", "em", "strong", "i", "b", "br", "u", "sup", "sub", "cite"}

BLOCK_MAP = {
    "p": "p",
    "h2": "h2",
    "h3": "h3",
    "h4": "h3",
    "blockquote": "quote",
    "li": "li",
}

WORDS_PER_MINUTE = 200

# Parámetros de rastreo que no cambian el contenido
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|igshid|mc_|ref|source|_ga|cmpid|ncid)", re.I)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
def canonicalize_url(url: str, base: str | None = None) -> str:
    """Quita fragmentos y parámetros de rastreo para poder comparar URLs."""
    if base:
        url = urljoin(base, url)
    parsed = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not TRACKING_PARAMS.match(k)]
    path = parsed.path.rstrip("/") or "/"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return urlunparse((
        parsed.scheme or "https", netloc, path, "", urlencode(query), "",
    ))


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------
def _is_noise(tag: Tag) -> bool:
    raw = getattr(tag, "attrs", None) or {}
    classes = raw.get("class") or []
    if isinstance(classes, str):
        classes = [classes]
    attrs = " ".join(
        filter(None, [
            " ".join(classes),
            raw.get("id") or "",
            raw.get("data-module") or "",
            raw.get("role") or "",
        ])
    )
    return bool(attrs and NOISE_PATTERN.search(attrs))


def strip_noise(root: Tag) -> Tag:
    for tag in root.find_all(list(DROP_TAGS)):
        tag.decompose()
    for tag in root.find_all(True):
        # Al descomponer un contenedor sus hijos quedan "muertos" pero siguen
        # en la lista que estamos recorriendo: hay que saltárselos.
        if not isinstance(tag, Tag) or getattr(tag, "decomposed", False):
            continue
        if _is_noise(tag):
            tag.decompose()
    return root


def _inline_html(tag: Tag, base_url: str | None) -> str:
    """Devuelve el HTML del bloque conservando solo etiquetas seguras."""
    clone = BeautifulSoup(str(tag), "lxml")
    inner = clone.find(tag.name) or clone
    for child in list(inner.find_all(True)):
        if child.name not in INLINE_ALLOWED:
            child.unwrap()
            continue
        if child.name == "a":
            href = child.get("href")
            child.attrs = {}
            if href:
                child["href"] = urljoin(base_url, href) if base_url else href
                child["target"] = "_blank"
                child["rel"] = "noopener noreferrer"
        else:
            child.attrs = {}
    html = inner.decode_contents() if hasattr(inner, "decode_contents") else str(inner)
    return re.sub(r"\s+", " ", html).strip()


def _visible_text(tag: Tag) -> str:
    text = tag.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def html_to_blocks(html: str, base_url: str | None = None) -> list[dict]:
    """Convierte un fragmento HTML (el cuerpo del artículo) en bloques."""
    soup = BeautifulSoup(html or "", "lxml")
    body = soup.body or soup
    strip_noise(body)

    blocks: list[dict] = []
    seen: set[str] = set()

    for element in body.find_all(list(BLOCK_MAP.keys())):
        if not isinstance(element, Tag):
            continue
        # Evita duplicar el texto de un <p> que vive dentro de un <blockquote>
        if element.name == "p" and element.find_parent(["blockquote", "li"]):
            continue
        text = _visible_text(element)
        if len(text) < 2:
            continue
        key = text[:120].lower()
        if key in seen:
            continue
        seen.add(key)
        blocks.append({
            "type": BLOCK_MAP[element.name],
            "html": _inline_html(element, base_url) or text,
            "text": text,
        })

    if not blocks:
        # Último recurso: partir el texto plano en párrafos por saltos de línea
        raw = body.get_text("\n", strip=True)
        for para in (p.strip() for p in raw.split("\n")):
            if len(para) > 40:
                blocks.append({"type": "p", "html": para, "text": para})

    return blocks


def blocks_from_plain_text(text: str) -> list[dict]:
    """Para extractores que devuelven texto plano (p. ej. trafilatura)."""
    blocks = []
    for para in re.split(r"\n{2,}|\n", text or ""):
        para = para.strip()
        if not para:
            continue
        kind = "h2" if len(para) < 90 and not para.endswith((".", "?", "!", "»", '"')) else "p"
        blocks.append({"type": kind, "html": para, "text": para})
    return blocks


# ---------------------------------------------------------------------------
# Métricas derivadas
# ---------------------------------------------------------------------------
def blocks_to_text(blocks: list[dict]) -> str:
    return "\n\n".join(b.get("text", "").strip() for b in blocks if b.get("text"))


def normalize_for_hash(text: str) -> str:
    """Texto canónico para detectar republicaciones y ediciones menores."""
    lowered = unicodedata.normalize("NFKD", (text or "").lower())
    lowered = "".join(c for c in lowered if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\s+", " ", lowered)).strip()


def content_hash(title: str, text: str) -> str:
    payload = normalize_for_hash(f"{title} {text}")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def reading_minutes(word_count: int) -> int:
    return max(1, round(word_count / WORDS_PER_MINUTE))


def make_summary(text: str, max_chars: int = 320) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_chars:
        return clean
    cut = clean[:max_chars]
    last_stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if last_stop > max_chars * 0.5:
        return cut[: last_stop + 1]
    return cut.rsplit(" ", 1)[0] + "…"


PAYWALL_HINTS = re.compile(
    r"(suscr[íi]bete|suscripci[óo]n|contenido exclusivo|art[íi]culo exclusivo|"
    r"para leer esta nota|reg[íi]strate para|inicia sesi[óo]n para continuar|"
    r"solo para suscriptores|hazte suscriptor)",
    re.IGNORECASE,
)


def looks_paywalled(text: str, word_count: int) -> bool:
    """Heurística: poco texto y frases de muro de pago."""
    if word_count < 150 and PAYWALL_HINTS.search(text or ""):
        return True
    return word_count < 60


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            if node.name == "meta":
                content = node.get("content")
                if content and content.strip():
                    return content.strip()
            else:
                text = _visible_text(node)
                if text:
                    return text
    return None


def extract_title(soup: BeautifulSoup) -> str | None:
    return _first_text(soup, [
        'meta[property="og:title"]',
        'meta[name="twitter:title"]',
        "h1",
        "title",
    ])


def extract_description(soup: BeautifulSoup) -> str | None:
    return _first_text(soup, [
        'meta[property="og:description"]',
        'meta[name="description"]',
    ])


def extract_canonical(soup: BeautifulSoup, fallback: str) -> str:
    link = soup.select_one('link[rel="canonical"]')
    if link and link.get("href"):
        return canonicalize_url(link["href"], fallback)
    og = soup.select_one('meta[property="og:url"]')
    if og and og.get("content"):
        return canonicalize_url(og["content"], fallback)
    return canonicalize_url(fallback)


def strings_of(node: Tag) -> list[str]:
    return [s.strip() for s in node.strings if isinstance(s, NavigableString) and s.strip()]
