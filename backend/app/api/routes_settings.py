"""Preferencias y credenciales por medio."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.audio.tts.registry import describe_providers
from app.config import settings
from app.models import MediaCredential, UserPreference
from app.schemas import CredentialIn, CredentialOut, PreferencesOut, PreferencesUpdate
from app.security import decrypt_payload, encrypt_payload

router = APIRouter(prefix="/api/settings", tags=["configuración"])


def _prefs(db: Session) -> UserPreference:
    prefs = db.get(UserPreference, 1)
    if prefs is None:
        prefs = UserPreference(
            id=1,
            collect_hour=settings.collect_hour,
            collect_minute=settings.collect_minute,
            timezone=settings.timezone,
            tts_provider=settings.tts_provider,
            tts_voice=settings.openai_tts_voice,
            retention_months=settings.retention_months,
        )
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


# ---------------------------------------------------------------------------
@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(
    db: Session = Depends(get_db), _: str = Depends(current_user)
) -> PreferencesOut:
    return PreferencesOut.model_validate(_prefs(db))


@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> PreferencesOut:
    prefs = _prefs(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    db.commit()
    db.refresh(prefs)
    return PreferencesOut.model_validate(prefs)


@router.get("/tts-providers")
def tts_providers(_: str = Depends(current_user)) -> list[dict]:
    return describe_providers()


# ---------------------------------------------------------------------------
# Credenciales de medios (cifradas)
# ---------------------------------------------------------------------------
def _to_out(cred: MediaCredential) -> CredentialOut:
    payload = decrypt_payload(cred.encrypted_payload)
    cookies = payload.get("cookies") or {}
    return CredentialOut(
        id=cred.id,
        outlet=cred.outlet,
        kind=cred.kind,
        label=cred.label,
        has_secret=bool(payload),
        cookie_names=sorted(cookies.keys()) if isinstance(cookies, dict) else [],
        updated_at=cred.updated_at,
        last_used_at=cred.last_used_at,
    )


@router.get("/credentials", response_model=list[CredentialOut])
def list_credentials(
    db: Session = Depends(get_db), _: str = Depends(current_user)
) -> list[CredentialOut]:
    creds = db.scalars(select(MediaCredential).order_by(MediaCredential.outlet)).all()
    return [_to_out(c) for c in creds]


@router.put("/credentials", response_model=CredentialOut)
def upsert_credential(
    payload: CredentialIn,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> CredentialOut:
    """Guarda (cifradas) las cookies o el usuario/contraseña de un medio.

    Las cookies se pegan tal cual las copias del navegador:
        `sessionid=abc123; otra=valor`
    """
    data: dict = {}
    if payload.kind == "cookies":
        if not payload.cookies_raw:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faltan las cookies")
        cookies = {}
        for part in payload.cookies_raw.split(";"):
            if "=" not in part:
                continue
            name, _, value = part.partition("=")
            name, value = name.strip(), value.strip()
            if name:
                cookies[name] = value
        if not cookies:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "No se reconoció ninguna cookie. El formato es «nombre=valor; otra=valor»",
            )
        data = {"cookies": cookies}
    else:
        if not (payload.username and payload.password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faltan usuario o contraseña")
        data = {"username": payload.username, "password": payload.password}

    cred = db.scalar(select(MediaCredential).where(MediaCredential.outlet == payload.outlet))
    if cred is None:
        cred = MediaCredential(outlet=payload.outlet)
        db.add(cred)
    cred.kind = payload.kind
    cred.label = payload.label
    cred.encrypted_payload = encrypt_payload(data)
    cred.updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(cred)
    return _to_out(cred)


@router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> None:
    cred = db.get(MediaCredential, credential_id)
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa credencial")
    db.delete(cred)
    db.commit()
