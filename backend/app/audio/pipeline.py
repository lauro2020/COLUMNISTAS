"""El generador de audio.

Toma un artículo ya normalizado y produce un MP3 con:
  * una introducción hablada (título, autor, medio y fecha),
  * el cuerpo completo con pausas entre párrafos,
  * marcas de sincronía párrafo ↔ segundo, para poder alternar entre leer y
    escuchar sin perder el punto.

Los fragmentos se sintetizan EN PARALELO y luego se unen con ffmpeg, así
un artículo largo tarda lo mismo que uno corto.

Se puede ejecutar de forma independiente:
    python -m app.cli audio --article 12
"""

from __future__ import annotations

import datetime as dt
import logging
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio import ffmpeg, textprep
from app.audio.tts.base import TTSProviderError
from app.audio.tts.registry import get_provider
from app.config import settings
from app.models import Article, Audio, AudioStatus, UserPreference

log = logging.getLogger(__name__)

#: pausa que se intercala entre fragmentos, en segundos
PAUSE_SECONDS = 0.45
#: peticiones simultáneas al proveedor de voz
PARALLEL_REQUESTS = 4


def audio_root() -> Path:
    root = Path(settings.audio_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def absolute_path(relative: str | None) -> Path | None:
    if not relative:
        return None
    return audio_root() / relative


# ---------------------------------------------------------------------------
def generate_for_article(
    db: Session,
    article_id: int,
    *,
    force: bool = False,
    provider_key: str | None = None,
    voice: str | None = None,
) -> Audio:
    article = db.get(Article, article_id)
    if article is None:
        raise ValueError(f"No existe el artículo {article_id}")

    prefs = db.get(UserPreference, 1)
    provider_key = provider_key or (prefs.tts_provider if prefs else settings.tts_provider)
    voice = voice or (prefs.tts_voice if prefs else settings.openai_tts_voice)
    provider = get_provider(provider_key)

    audio = db.scalar(select(Audio).where(Audio.article_id == article_id))
    if audio is None:
        audio = Audio(article_id=article_id)
        db.add(audio)
        db.flush()

    if audio.status == AudioStatus.ready and not force:
        return audio

    # Se borra el archivo anterior al regenerar
    if force and audio.file_path:
        old = absolute_path(audio.file_path)
        if old and old.exists():
            old.unlink(missing_ok=True)

    audio.status = AudioStatus.processing
    audio.error_message = None
    audio.provider = provider.key
    audio.voice = voice
    db.flush()
    db.commit()

    try:
        rel_path, duration, marks, size = _synthesize(article, provider, voice)
    except Exception as exc:  # noqa: BLE001 - un fallo de audio no rompe nada más
        log.exception("Fallo generando audio del artículo %s", article_id)
        audio.status = AudioStatus.error
        audio.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        db.flush()
        db.commit()
        return audio

    audio.file_path = rel_path
    audio.duration_seconds = duration
    audio.marks = marks
    audio.file_size = size
    audio.format = "mp3"
    audio.status = AudioStatus.ready
    audio.generated_at = dt.datetime.now(dt.timezone.utc)
    audio.error_message = None
    db.flush()
    db.commit()
    log.info("Audio listo: artículo %s (%.1f s)", article_id, duration)
    return audio


# ---------------------------------------------------------------------------
def _synthesize(article: Article, provider, voice: str) -> tuple[str, float, list[dict], int]:
    paragraphs = [
        block.get("text", "")
        for block in (article.body or [])
        if block.get("text") and block.get("type") in ("p", "h2", "h3", "quote", "li")
    ]
    if not paragraphs:
        raise TTSProviderError("El artículo no tiene texto que leer")

    intro = textprep.build_intro(
        article.title, article.author, article.outlet, article.published_at
    )
    chunks = textprep.build_chunks(paragraphs, intro=intro, max_chars=provider.max_chars)

    workdir = Path(tempfile.mkdtemp(prefix=f"tts-{article.id}-"))
    try:
        parts = _synthesize_chunks(chunks, provider, voice, workdir)
        pause = ffmpeg.silence(PAUSE_SECONDS, workdir / "pause.mp3")

        # Duraciones y marcas de sincronía
        marks: list[dict] = []
        sequence: list[Path] = []
        cursor = 0.0
        for index, (chunk, part) in enumerate(zip(chunks, parts, strict=True)):
            duration = ffmpeg.probe_duration(part)
            marks.extend(_chunk_marks(chunk, cursor, duration))
            sequence.append(part)
            cursor += duration
            if index < len(parts) - 1:
                sequence.append(pause)
                cursor += PAUSE_SECONDS

        published = article.published_at or dt.datetime.now(dt.timezone.utc)
        rel_dir = f"{published.year:04d}/{published.month:02d}"
        filename = f"{article.id}-{voice or 'default'}.mp3"
        target = audio_root() / rel_dir / filename

        ffmpeg.concat(sequence, target)
        total = ffmpeg.probe_duration(target)
        return f"{rel_dir}/{filename}", total, marks, target.stat().st_size
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _synthesize_chunks(chunks, provider, voice: str, workdir: Path) -> list[Path]:
    """Sintetiza todos los fragmentos (en paralelo si el proveedor lo permite)."""

    def one(item: tuple[int, textprep.Chunk]) -> Path:
        index, chunk = item
        raw = workdir / f"{index:04d}.{provider.output_format}"
        provider.synthesize(chunk.text, voice, raw)
        if provider.output_format != "mp3":
            return ffmpeg.to_mp3(raw, workdir / f"{index:04d}.mp3")
        return raw

    items = list(enumerate(chunks))
    if provider.supports_parallel and len(items) > 1:
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            return list(pool.map(one, items))
    return [one(item) for item in items]


def _chunk_marks(chunk: textprep.Chunk, start: float, duration: float) -> list[dict]:
    """Reparte la duración del fragmento entre sus párrafos, por longitud."""
    indices = [i for i in chunk.paragraph_indices if i >= 0]
    if not indices:
        return [{"paragraph_index": -1, "start": round(start, 2),
                 "end": round(start + duration, 2)}]

    weights = [max(len(chunk.text) // len(indices), 1) for _ in indices]
    total_weight = sum(weights)
    marks, cursor = [], start
    for index, weight in zip(indices, weights, strict=True):
        span = duration * (weight / total_weight)
        marks.append({
            "paragraph_index": index,
            "start": round(cursor, 2),
            "end": round(cursor + span, 2),
        })
        cursor += span
    return marks


# ---------------------------------------------------------------------------
def delete_audio_files(audios: list[Audio]) -> int:
    """Borra del disco los archivos de los audios indicados."""
    removed = 0
    for audio in audios:
        path = absolute_path(audio.file_path)
        if path and path.exists():
            path.unlink(missing_ok=True)
            removed += 1
    return removed
