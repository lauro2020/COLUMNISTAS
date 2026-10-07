"""Seguridad: sesión del usuario y cifrado de credenciales de medios.

- La app es de UN solo usuario. Entras con la contraseña de `APP_PASSWORD`
  y recibes un token firmado (JWT) que el navegador guarda.
- Las cookies/credenciales de los medios se guardan CIFRADAS en la base de
  datos con Fernet (AES-128 en modo CBC + HMAC), derivando la llave de
  `APP_SECRET_KEY`. Ni siquiera leyendo la base de datos se ven en claro.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------
def verify_password(candidate: str) -> bool:
    """Comparación en tiempo constante para no filtrar información."""
    return hmac.compare_digest(candidate.encode(), settings.app_password.encode())


def create_token() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": "owner",
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(days=settings.auth_token_days)).timestamp()),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# Cifrado de credenciales
# ---------------------------------------------------------------------------
def _fernet() -> Fernet:
    """Deriva una llave Fernet válida (32 bytes, base64url) del secreto."""
    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_payload(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False).encode()
    return _fernet().encrypt(raw).decode()


def decrypt_payload(blob: str) -> dict[str, Any]:
    """Devuelve {} si la llave cambió o el dato está corrupto (nunca revienta)."""
    try:
        return json.loads(_fernet().decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError, TypeError):
        return {}
