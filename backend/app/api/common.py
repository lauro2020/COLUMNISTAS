"""Piezas que comparten varias rutas de la API."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, UserPreference
from app.schemas import ArticleListItem


def local_tz(db: Session) -> ZoneInfo:
    """La zona horaria elegida en Ajustes; si falla, UTC."""
    prefs = db.get(UserPreference, 1)
    try:
        return ZoneInfo((prefs.timezone if prefs else None) or settings.timezone)
    except Exception:  # noqa: BLE001 - un nombre de zona inválido no debe tumbar nada
        return ZoneInfo("UTC")


def article_item(article: Article) -> ArticleListItem:
    """Convierte un artículo a la forma que consume la interfaz."""
    item = ArticleListItem.model_validate(article)
    audio = article.audios[0] if article.audios else None
    if audio:
        item.audio_id = audio.id
        item.audio_status = audio.status
        item.audio_duration = audio.duration_seconds
    return item


def day_bounds(day: dt.date, tz: ZoneInfo) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, dt.time.min, tzinfo=tz)
    return start, start + dt.timedelta(days=1)


def recent_cutoff(today: dt.date, recent_days: int, tz: ZoneInfo) -> dt.datetime:
    """Desde qué instante se considera «reciente» un artículo.

    Días naturales: se cuenta desde las 00:00 del día que queda `recent_days`
    atrás, así que una columna de hace exactamente esos días entra, y la del
    día siguiente hacia atrás ya no.
    """
    return dt.datetime.combine(
        today - dt.timedelta(days=recent_days), dt.time.min, tzinfo=tz
    )


def overview_sort_key(
    published_today: bool, days_since_last: int | None, name: str
) -> tuple:
    """Orden de la pantalla de inicio.

    Primero quien publicó hoy, después por cercanía de su última columna, y al
    final quien lleva más tiempo callado o nunca ha aparecido.
    """
    return (
        not published_today,
        days_since_last if days_since_last is not None else 10**6,
        name,
    )
