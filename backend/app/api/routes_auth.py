"""Inicio de sesión (un solo usuario)."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.schemas import LoginRequest, TokenResponse
from app.security import create_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    # Retardo fijo: dificulta adivinar la contraseña por fuerza bruta
    time.sleep(0.4)
    if not verify_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña incorrecta"
        )
    return TokenResponse(token=create_token(), expires_days=settings.auth_token_days)
