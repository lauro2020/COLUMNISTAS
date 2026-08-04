"""Dependencias compartidas de la API."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import decode_token


def current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    """Comprueba el token de sesión.

    Se acepta en la cabecera `Authorization: Bearer <token>` o como
    parámetro `?token=` (lo necesita la etiqueta <audio> del navegador,
    que no puede enviar cabeceras).
    """
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:]
    elif token:
        raw = token

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la sesión",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(raw)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida o caducada",
        )
    return payload.get("sub", "owner")


DbSession = Depends(get_db)
AuthUser = Depends(current_user)

__all__ = ["current_user", "get_db", "Session", "DbSession", "AuthUser"]
