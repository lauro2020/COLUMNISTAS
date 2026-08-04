"""Cliente HTTP educado.

Reglas que aplica automáticamente a todas las peticiones:
  * User-Agent propio e identificable.
  * Respeta robots.txt (se puede desactivar por configuración).
  * Un mínimo de segundos entre peticiones al MISMO dominio.
  * Reintentos con espera exponencial ante errores de red, 429 y 5xx.
  * Cookies de suscriptor por medio, si las hay guardadas.
  * Navegador headless (Playwright) solo cuando el contenido lo exige.
"""

from __future__ import annotations

import logging
import random
import threading
import time
import socket
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.config import settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    ok: bool
    from_browser: bool = False
    elapsed_ms: int = 0
    error: str | None = None


@dataclass
class RobotsCache:
    _parsers: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allowed(self, url: str, user_agent: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            parser = self._parsers.get(origin)
            if parser is None:
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(urljoin(origin, "/robots.txt"))
                try:
                    resp = httpx.get(
                        urljoin(origin, "/robots.txt"),
                        headers={"User-Agent": user_agent},
                        timeout=10,
                        follow_redirects=True,
                    )
                    if resp.status_code == 200:
                        parser.parse(resp.text.splitlines())
                    else:
                        # Sin robots.txt legible -> se asume permitido.
                        parser.allow_all = True
                except Exception:  # noqa: BLE001 - la red puede fallar
                    parser.allow_all = True
                self._parsers[origin] = parser
        try:
            return parser.can_fetch(user_agent, url)
        except Exception:  # noqa: BLE001
            return True


_robots = RobotsCache()
_last_request: dict[str, float] = {}
_rate_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Errores de resolución de nombres (DNS)
# ---------------------------------------------------------------------------
#: Mensajes con los que el sistema operativo avisa de que un dominio no resuelve
DNS_ERROR_HINTS = (
    "no address associated with hostname",   # EAI_NODATA
    "name or service not known",             # EAI_NONAME
    "nodename nor servname provided",        # macOS
    "temporary failure in name resolution",
    "getaddrinfo failed",
)


def is_dns_error(exc: BaseException) -> bool:
    """¿El fallo es «no pude resolver el nombre», y no «no pude conectar»?"""
    if isinstance(exc, socket.gaierror):
        return True
    text = str(exc).lower()
    return any(hint in text for hint in DNS_ERROR_HINTS)


def alternate_host_url(url: str) -> str | None:
    """Devuelve la misma URL con «www.» añadido o quitado del dominio.

    Varios medios publican solo una de las dos variantes; si la que tenemos
    guardada no resuelve, merece la pena probar la otra antes de rendirse.
    """
    parsed = urlparse(url)
    host = parsed.netloc
    if not host:
        return None
    swapped = host[4:] if host.startswith("www.") else f"www.{host}"
    return urlunparse(parsed._replace(netloc=swapped))


def _respect_rate_limit(host: str) -> None:
    """Espera lo necesario para no golpear el mismo dominio muy seguido."""
    delay = settings.request_delay_seconds
    if delay <= 0:
        return
    with _rate_lock:
        last = _last_request.get(host, 0.0)
        wait = delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.4))
        _last_request[host] = time.monotonic()


class Fetcher:
    """Se crea uno por ejecución de recolección; reutiliza la conexión."""

    def __init__(self, cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None):
        base_headers = {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
        }
        if headers:
            base_headers.update(headers)
        self._client = httpx.Client(
            headers=base_headers,
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            cookies=cookies or {},
        )
        self.cookies = cookies or {}
        #: dominios que hubo que corregir (p. ej. www.medio.com -> medio.com)
        self.host_swaps: dict[str, str] = {}

    # -- ciclo de vida -----------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- peticiones --------------------------------------------------------
    def get(
        self, url: str, *, use_browser: bool = False, allow_host_swap: bool = True
    ) -> FetchResult:
        if settings.respect_robots and not _robots.allowed(url, settings.user_agent):
            log.warning("robots.txt no permite %s", url)
            return FetchResult(
                url=url, status_code=0, text="", ok=False,
                error="Bloqueado por robots.txt",
            )

        if use_browser and settings.enable_headless_browser:
            return self._get_with_browser(url)

        host = urlparse(url).netloc
        last_error: str | None = None
        started = time.monotonic()

        for attempt in range(settings.max_retries):
            _respect_rate_limit(host)
            try:
                resp = self._client.get(url)
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = f"HTTP {resp.status_code}"
                    self._backoff(attempt)
                    continue
                elapsed = int((time.monotonic() - started) * 1000)
                return FetchResult(
                    url=str(resp.url),
                    status_code=resp.status_code,
                    text=resp.text,
                    ok=resp.status_code < 400,
                    elapsed_ms=elapsed,
                    error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                )
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"

                # Un fallo de DNS no mejora reintentando: el nombre no resuelve.
                # Se prueba una sola vez la variante del dominio con o sin "www."
                # (muchos medios solo publican una de las dos).
                if is_dns_error(exc):
                    if allow_host_swap:
                        alternate = alternate_host_url(url)
                        if alternate:
                            log.info("DNS falló en %s; probando %s", host, alternate)
                            result = self.get(
                                alternate, use_browser=use_browser, allow_host_swap=False
                            )
                            if result.ok:
                                self.host_swaps[host] = urlparse(alternate).netloc
                                return result
                    return FetchResult(
                        url=url, status_code=0, text="", ok=False,
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        error=(
                            f"No se pudo resolver el dominio «{host}» desde el "
                            f"contenedor (DNS). Ejecuta «python -m app.cli doctor» "
                            f"para ver el diagnóstico completo."
                        ),
                    )

                self._backoff(attempt)

        elapsed = int((time.monotonic() - started) * 1000)
        return FetchResult(
            url=url, status_code=0, text="", ok=False,
            elapsed_ms=elapsed, error=last_error or "fallo desconocido",
        )

    @staticmethod
    def _backoff(attempt: int) -> None:
        # 2s, 4s, 8s... con un poco de aleatoriedad para no sincronizar reintentos
        time.sleep(min(2 ** (attempt + 1), 30) + random.uniform(0, 1))

    def _get_with_browser(self, url: str) -> FetchResult:
        """Renderiza con Chromium. Solo si el sitio necesita JavaScript."""
        started = time.monotonic()
        try:
            from playwright.sync_api import sync_playwright  # import perezoso
        except ImportError:
            return FetchResult(
                url=url, status_code=0, text="", ok=False,
                error="Playwright no está instalado (construye con INSTALL_PLAYWRIGHT=true)",
            )

        host = urlparse(url).netloc
        _respect_rate_limit(host)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(args=["--no-sandbox"])
                context = browser.new_context(
                    user_agent=settings.user_agent, locale="es-MX"
                )
                if self.cookies:
                    context.add_cookies([
                        {"name": k, "value": v, "domain": f".{host}", "path": "/"}
                        for k, v in self.cookies.items()
                    ])
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded",
                          timeout=settings.request_timeout_seconds * 1000)
                page.wait_for_timeout(1500)
                html = page.content()
                final_url = page.url
                browser.close()
            return FetchResult(
                url=final_url, status_code=200, text=html, ok=True,
                from_browser=True, elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(
                url=url, status_code=0, text="", ok=False, from_browser=True,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=f"navegador: {exc}",
            )
