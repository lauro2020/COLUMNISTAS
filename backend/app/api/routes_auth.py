"""Inicio de sesión (un solo usuario)."""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, HTTPException, Request, status

from app.config import settings
from app.schemas import LoginRequest, TokenResponse
from app.security import create_token, verify_password

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Freno a los intentos por fuerza bruta. En memoria: es una app de un solo
# usuario y reiniciar el contenedor para saltárselo requiere ya tener acceso
# a la máquina.
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _client_key(request: Request) -> str:
    # Detrás de nginx la IP real llega en X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def _seconds_locked(key: str) -> int:
    ventana = settings.login_lockout_minutes * 60
    ahora = time.monotonic()
    with _lock:
        intentos = [t for t in _failures.get(key, []) if ahora - t < ventana]
        _failures[key] = intentos
        if len(intentos) < settings.login_max_attempts:
            return 0
        return int(ventana - (ahora - intentos[0])) + 1


def _record_failure(key: str) -> None:
    with _lock:
        _failures.setdefault(key, []).append(time.monotonic())


def _clear(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request) -> TokenResponse:
    key = _client_key(request)

    bloqueado = _seconds_locked(key)
    if bloqueado:
        minutos = max(1, bloqueado // 60)
        log.warning("Login bloqueado temporalmente para %s", key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Demasiados intentos fallidos. Vuelve a probar en "
                f"{minutos} minuto{'s' if minutos > 1 else ''}."
            ),
            headers={"Retry-After": str(bloqueado)},
        )

    # Retardo fijo: dificulta adivinar la contraseña por fuerza bruta
    time.sleep(0.4)

    if not verify_password(payload.password):
        _record_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña incorrecta"
        )

    _clear(key)
    return TokenResponse(token=create_token(), expires_days=settings.auth_token_days)



