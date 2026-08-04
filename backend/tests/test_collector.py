"""Pruebas del cliente HTTP, el RSS y la seguridad."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.collector import rss
from app.collector.http_client import Fetcher
from app.config import settings
from app.security import create_token, decode_token, decrypt_payload, encrypt_payload
from tests import fixtures


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Quita los retardos de cortesía para que las pruebas vuelen."""
    monkeypatch.setattr(settings, "request_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "respect_robots", False)
    monkeypatch.setattr(settings, "max_retries", 2)
    monkeypatch.setattr(Fetcher, "_backoff", staticmethod(lambda attempt: None))


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------
@respx.mock
def test_fetcher_envia_user_agent_propio():
    ruta = respx.get("https://diariox.test/a").mock(
        return_value=httpx.Response(200, text="hola")
    )
    with Fetcher() as fetcher:
        resultado = fetcher.get("https://diariox.test/a")

    assert resultado.ok
    assert "ColumnistasBot" in ruta.calls[0].request.headers["user-agent"]


@respx.mock
def test_fetcher_reintenta_ante_error_temporal():
    respx.get("https://diariox.test/b").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text="ya está")]
    )
    with Fetcher() as fetcher:
        resultado = fetcher.get("https://diariox.test/b")

    assert resultado.ok
    assert resultado.text == "ya está"


@respx.mock
def test_fetcher_devuelve_error_sin_lanzar_excepcion():
    respx.get("https://diariox.test/c").mock(side_effect=httpx.ConnectError("sin red"))
    with Fetcher() as fetcher:
        resultado = fetcher.get("https://diariox.test/c")

    assert resultado.ok is False
    assert "ConnectError" in resultado.error


@respx.mock
def test_fetcher_manda_las_cookies_de_suscriptor():
    ruta = respx.get("https://reforma.com/x").mock(return_value=httpx.Response(200, text="ok"))
    with Fetcher(cookies={"sesion": "abc123"}) as fetcher:
        fetcher.get("https://reforma.com/x")

    assert "sesion=abc123" in ruta.calls[0].request.headers["cookie"]


def test_robots_bloqueado_no_descarga(monkeypatch):
    monkeypatch.setattr(settings, "respect_robots", True)
    from app.collector import http_client

    monkeypatch.setattr(http_client._robots, "allowed", lambda url, ua: False)
    with Fetcher() as fetcher:
        resultado = fetcher.get("https://diariox.test/prohibido")

    assert resultado.ok is False
    assert "robots" in resultado.error.lower()


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------
@respx.mock
def test_parse_feed():
    respx.get("https://diariox.test/feed").mock(
        return_value=httpx.Response(200, text=fixtures.RSS_FEED)
    )
    with Fetcher() as fetcher:
        refs = rss.parse_feed("https://diariox.test/feed", fetcher)

    assert len(refs) == 2
    assert refs[0].title == "Columna del lunes"
    assert refs[0].published_at is not None
    assert refs[0].url == "https://diariox.test/opinion/2025/03/10/columna-del-lunes"


def test_descubrir_feed_en_el_head():
    encontrado = rss.discover_feed_url(
        fixtures.PAGE_WITH_FEED_LINK, "https://diariox.test/autores/x/"
    )
    assert encontrado == "https://diariox.test/opinion/feed"


@respx.mock
def test_feed_invalido_da_error_claro():
    respx.get("https://diariox.test/malo").mock(
        return_value=httpx.Response(200, text="esto no es un feed")
    )
    with Fetcher() as fetcher, pytest.raises(RuntimeError):
        rss.parse_feed("https://diariox.test/malo", fetcher)


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------
def test_cifrado_de_credenciales_ida_y_vuelta():
    original = {"cookies": {"sesion": "valor-secreto"}}
    blob = encrypt_payload(original)

    assert "valor-secreto" not in blob, "el secreto no puede quedar legible"
    assert decrypt_payload(blob) == original


def test_credencial_corrupta_no_revienta():
    assert decrypt_payload("esto-no-es-un-token-valido") == {}


def test_token_de_sesion():
    token = create_token()
    assert decode_token(token)["sub"] == "owner"
    assert decode_token("token.falso.xxx") is None


# ---------------------------------------------------------------------------
# Fallos de resolución de nombres (DNS)
# ---------------------------------------------------------------------------
import socket  # noqa: E402

from app.collector.http_client import alternate_host_url, is_dns_error  # noqa: E402


@pytest.mark.parametrize("mensaje", [
    "[Errno -5] No address associated with hostname",
    "[Errno -2] Name or service not known",
    "nodename nor servname provided, or not known",
    "Temporary failure in name resolution",
])
def test_se_reconocen_los_fallos_de_dns(mensaje):
    assert is_dns_error(httpx.ConnectError(mensaje)) is True


def test_no_confunde_otros_fallos_con_dns():
    assert is_dns_error(httpx.ConnectError("[Errno 111] Connection refused")) is False
    assert is_dns_error(httpx.ReadTimeout("se acabó el tiempo")) is False
    assert is_dns_error(socket.gaierror(-5, "lo que sea")) is True


def test_alternar_el_dominio_con_y_sin_www():
    assert alternate_host_url("https://www.reforma.com/autor/") == "https://reforma.com/autor/"
    assert alternate_host_url("https://reforma.com/autor/") == "https://www.reforma.com/autor/"
    assert alternate_host_url("no-es-una-url") is None


@respx.mock
def test_si_el_dominio_no_resuelve_se_prueba_la_otra_variante():
    respx.get("https://www.medio.test/autor/").mock(
        side_effect=httpx.ConnectError("[Errno -5] No address associated with hostname")
    )
    respx.get("https://medio.test/autor/").mock(
        return_value=httpx.Response(200, text="la columna")
    )

    with Fetcher() as fetcher:
        resultado = fetcher.get("https://www.medio.test/autor/")

    assert resultado.ok
    assert resultado.text == "la columna"
    assert fetcher.host_swaps == {"www.medio.test": "medio.test"}


@respx.mock
def test_si_ninguna_variante_resuelve_el_error_es_claro():
    respx.get("https://www.medio.test/autor/").mock(
        side_effect=httpx.ConnectError("[Errno -5] No address associated with hostname")
    )
    respx.get("https://medio.test/autor/").mock(
        side_effect=httpx.ConnectError("[Errno -5] No address associated with hostname")
    )

    with Fetcher() as fetcher:
        resultado = fetcher.get("https://www.medio.test/autor/")

    assert resultado.ok is False
    assert "no se pudo resolver el dominio" in resultado.error.lower()
    assert "doctor" in resultado.error, "el mensaje debe decir cómo diagnosticarlo"
    assert fetcher.host_swaps == {}


@respx.mock
def test_un_fallo_de_dns_no_gasta_los_reintentos():
    """Reintentar no arregla un DNS roto: debe fallar rápido, no en 14 segundos."""
    ruta = respx.get("https://www.medio.test/autor/").mock(
        side_effect=httpx.ConnectError("[Errno -5] No address associated with hostname")
    )
    respx.get("https://medio.test/autor/").mock(
        side_effect=httpx.ConnectError("[Errno -5] No address associated with hostname")
    )

    with Fetcher() as fetcher:
        fetcher.get("https://www.medio.test/autor/")

    assert ruta.call_count == 1, "una sola petición al dominio original"
