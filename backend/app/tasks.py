"""Trabajos en segundo plano (Celery).

Piezas:
  tick               -> se ejecuta cada 5 minutos y decide si toca recolectar
  collect            -> la recolección diaria
  generate_audio     -> genera el MP3 de un artículo
  apply_retention    -> borra lo que supere la retención configurada

La hora de recolección NO está clavada en el calendario de Celery: `tick`
lee la preferencia guardada en la base de datos. Así puedes cambiar la hora
desde la app y surte efecto sin reiniciar nada.
"""

from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from app import notifications
from app.audio import pipeline
from app.collector.runner import collect_all
from app.config import settings
from app.db import session_scope
from app.models import Article, Audio, AudioStatus, CollectionRun, Columnist, UserPreference

log = logging.getLogger(__name__)

celery_app = Celery("columnistas", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_max_tasks_per_child=50,
    broker_connection_retry_on_startup=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    beat_schedule={
        "tick-cada-5-minutos": {
            "task": "app.tasks.tick",
            "schedule": crontab(minute="*/5"),
        },
    },
)

#: si una fuente falla estos días seguidos, se avisa por correo
FAILURE_ALERT_THRESHOLD = 3


def _prefs(db) -> UserPreference:
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
        db.flush()
    return prefs


# ---------------------------------------------------------------------------
@celery_app.task(name="app.tasks.tick")
def tick() -> str:
    """Decide si ya toca recolectar hoy. Se ejecuta cada 5 minutos."""
    with session_scope() as db:
        prefs = _prefs(db)
        try:
            tz = ZoneInfo(prefs.timezone or settings.timezone)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("UTC")

        now = dt.datetime.now(tz)
        target = now.replace(
            hour=prefs.collect_hour, minute=prefs.collect_minute, second=0, microsecond=0
        )
        if now < target:
            return "todavía no es la hora"

        # ¿Ya hubo una recolección programada hoy?
        start_of_day = target.astimezone(dt.timezone.utc)
        already = db.scalar(
            select(CollectionRun.id)
            .where(CollectionRun.trigger == "scheduled")
            .where(CollectionRun.started_at >= start_of_day)
            .limit(1)
        )
        if already:
            return "ya se recolectó hoy"

    collect.delay(trigger="scheduled")
    apply_retention.delay()
    return "recolección lanzada"


# ---------------------------------------------------------------------------
@celery_app.task(name="app.tasks.collect", bind=True, max_retries=1)
def collect(self, trigger: str = "manual", columnist_ids: list[int] | None = None) -> dict:
    """Recorre las fuentes y encola el audio de cada artículo nuevo."""
    with session_scope() as db:
        result = collect_all(db, trigger=trigger, columnist_ids=columnist_ids)
        prefs = _prefs(db)
        auto_audio = prefs.auto_generate_audio
        new_ids = list(result.new_article_ids)
        run_id = result.run_id
        failed = result.sources_failed
        total = result.sources_total

        degraded = list(
            db.scalars(
                select(Columnist).where(
                    Columnist.consecutive_failures >= FAILURE_ALERT_THRESHOLD
                )
            ).all()
        )
        degraded_info = [(c.name, c.outlet, c.consecutive_failures, c.last_error) for c in degraded]

    if auto_audio:
        for article_id in new_ids:
            generate_audio.delay(article_id)

    if degraded_info:
        cuerpo = "\n\n".join(
            f"• {name} ({outlet}) — {fails} días seguidos sin poder recolectar.\n  {error or ''}"
            for name, outlet, fails, error in degraded_info
        )
        notifications.send(
            "Fuentes con problemas",
            "Estas fuentes llevan varios días fallando:\n\n"
            + cuerpo
            + "\n\nRevisa la pantalla de Diagnóstico en la app.",
        )

    log.info("Recolección %s: %s artículos nuevos, %s/%s fuentes con error",
             run_id, len(new_ids), failed, total)
    return {
        "run_id": run_id,
        "new_articles": len(new_ids),
        "sources_failed": failed,
        "sources_total": total,
    }


# ---------------------------------------------------------------------------
@celery_app.task(name="app.tasks.generate_audio", bind=True, max_retries=2)
def generate_audio(self, article_id: int, force: bool = False,
                   provider: str | None = None, voice: str | None = None) -> dict:
    with session_scope() as db:
        audio = pipeline.generate_for_article(
            db, article_id, force=force, provider_key=provider, voice=voice
        )
        return {
            "article_id": article_id,
            "status": audio.status.value,
            "duration": audio.duration_seconds,
            "error": audio.error_message,
        }


@celery_app.task(name="app.tasks.generate_missing_audio")
def generate_missing_audio(limit: int = 50) -> int:
    """Reintenta los audios pendientes o fallidos."""
    with session_scope() as db:
        pending = db.scalars(
            select(Article.id)
            .outerjoin(Audio, Audio.article_id == Article.id)
            .where(
                (Audio.id.is_(None))
                | (Audio.status.in_([AudioStatus.pending, AudioStatus.error]))
            )
            .where(Article.is_archived.is_(False))
            .order_by(Article.published_at.desc())
            .limit(limit)
        ).all()
    for article_id in pending:
        generate_audio.delay(article_id)
    return len(pending)


# ---------------------------------------------------------------------------
@celery_app.task(name="app.tasks.apply_retention")
def apply_retention() -> dict:
    """Borra artículos y audios que superen la retención configurada.

    También barre los MP3 que ya no pertenecen a ningún artículo: si eliminas
    un columnista, sus artículos se van en cascada pero los archivos no.
    """
    with session_scope() as db:
        prefs = _prefs(db)
        months = prefs.retention_months
        borrados = removed_files = 0

        if months:
            cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=months * 30)
            old = list(
                db.scalars(
                    select(Article)
                    .where(Article.published_at < cutoff)
                    .where(Article.is_favorite.is_(False))
                ).all()
            )
            audios = [a for article in old for a in article.audios]
            removed_files = pipeline.delete_audio_files(audios)
            for article in old:
                db.delete(article)
            borrados = len(old)
            db.flush()

        conocidos = {
            path for path in db.scalars(
                select(Audio.file_path).where(Audio.file_path.is_not(None))
            ).all()
        }

    huerfanos = pipeline.delete_orphan_files(conocidos)
    return {
        "deleted": borrados,
        "files_removed": removed_files,
        "orphans_removed": huerfanos,
        "note": None if months else "retención desactivada",
    }
