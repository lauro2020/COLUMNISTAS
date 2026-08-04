"""Servir y regenerar los archivos de audio.

El endpoint del archivo implementa peticiones parciales (HTTP Range). Es lo
que permite al reproductor saltar hacia adelante o hacia atrás sin volver a
descargar todo el MP3, y lo que hace que el service worker pueda guardarlo
para escuchar sin conexión.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.audio.pipeline import absolute_path
from app.models import Article, Audio, AudioStatus
from app.schemas import AudioOut

router = APIRouter(prefix="/api/audio", tags=["audio"])

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 256 * 1024


@router.get("/{audio_id}", response_model=AudioOut)
def get_audio(
    audio_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> AudioOut:
    audio = db.get(Audio, audio_id)
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese audio")
    out = AudioOut.model_validate(audio)
    if audio.status == AudioStatus.ready:
        out.url = f"/api/audio/{audio.id}/file"
    return out


@router.get("/article/{article_id}", response_model=AudioOut)
def get_audio_by_article(
    article_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> AudioOut:
    audio = db.scalar(select(Audio).where(Audio.article_id == article_id))
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este artículo todavía no tiene audio")
    out = AudioOut.model_validate(audio)
    if audio.status == AudioStatus.ready:
        out.url = f"/api/audio/{audio.id}/file"
    return out


@router.get("/{audio_id}/file")
def stream_audio(
    audio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> Response:
    audio = db.get(Audio, audio_id)
    if audio is None or audio.status != AudioStatus.ready:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El audio no está listo")

    path = absolute_path(audio.file_path)
    if path is None or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El archivo de audio no está en el disco")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "audio/mpeg",
        "Cache-Control": "private, max-age=31536000",
    }

    if not range_header:
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(_iter_file(path, 0, file_size - 1), headers=headers)

    match = RANGE_RE.match(range_header)
    if not match:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Rango no válido"
        )

    raw_start, raw_end = match.groups()
    start = int(raw_start) if raw_start else 0
    end = int(raw_end) if raw_end else file_size - 1
    end = min(end, file_size - 1)
    if start > end:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "Rango fuera del archivo"
        )

    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        _iter_file(path, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        headers=headers,
    )


def _iter_file(path: Path, start: int, end: int):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = handle.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


@router.post("/article/{article_id}/regenerate", response_model=dict)
def regenerate(
    article_id: int,
    voice: str | None = None,
    provider: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> dict:
    """Vuelve a generar el audio (por ejemplo, para probar otra voz)."""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese artículo")

    from app.tasks import generate_audio

    generate_audio.delay(article_id, force=True, provider=provider, voice=voice)
    return {"queued": True, "article_id": article_id}


@router.post("/generate-missing", response_model=dict)
def generate_missing(_: str = Depends(current_user)) -> dict:
    from app.tasks import generate_missing_audio

    generate_missing_audio.delay()
    return {"queued": True}
