"""Diagnóstico: salud de cada fuente y ejecuciones de recolección."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user, get_db
from app.models import (
    Article,
    Audio,
    AudioStatus,
    CollectionRun,
    Columnist,
    RunStatus,
    SourceRun,
)
from app.schemas import RunOut, SourceHealth

router = APIRouter(prefix="/api/health", tags=["diagnóstico"])


@router.get("/live")
def live() -> dict:
    """Comprobación simple de que el servicio responde (usada por Docker)."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok", "database": "ok"}


# ---------------------------------------------------------------------------
@router.get("/sources", response_model=list[SourceHealth])
def sources_health(
    days: int = Query(default=7, ge=1, le=60),
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> list[SourceHealth]:
    """Estado de salud de cada fuente en los últimos días."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    columnists = db.scalars(select(Columnist).order_by(Columnist.name)).all()

    runs = db.scalars(
        select(SourceRun).where(SourceRun.created_at >= since).order_by(SourceRun.created_at)
    ).all()

    by_columnist: dict[int, list[SourceRun]] = {}
    for run in runs:
        if run.columnist_id:
            by_columnist.setdefault(run.columnist_id, []).append(run)

    result: list[SourceHealth] = []
    for columnist in columnists:
        history = by_columnist.get(columnist.id, [])
        if columnist.consecutive_failures == 0 and columnist.last_success_at:
            estado = "sana"
        elif columnist.consecutive_failures >= 3:
            estado = "caida"
        elif columnist.consecutive_failures > 0:
            estado = "degradada"
        else:
            estado = "sin-datos"

        result.append(
            SourceHealth(
                columnist_id=columnist.id,
                name=columnist.name,
                outlet=columnist.outlet,
                active=columnist.active,
                status=estado,
                consecutive_failures=columnist.consecutive_failures,
                last_success_at=columnist.last_success_at,
                last_error=columnist.last_error,
                last_days=[
                    {
                        "date": r.created_at.date().isoformat(),
                        "status": r.status.value,
                        "found": r.articles_found,
                        "new": r.articles_new,
                        "ms": r.duration_ms,
                        "error": r.error_message,
                    }
                    for r in history[-days * 2:]
                ],
            )
        )
    return result


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    limit: int = Query(default=15, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> list[RunOut]:
    runs = db.scalars(
        select(CollectionRun)
        .options(selectinload(CollectionRun.source_runs))
        .order_by(CollectionRun.started_at.desc())
        .limit(limit)
    ).all()
    return [RunOut.model_validate(r) for r in runs]


@router.post("/runs")
def trigger_run(
    columnist_id: int | None = None,
    _: str = Depends(current_user),
) -> dict:
    """Lanza una recolección manual desde la app."""
    from app.tasks import collect

    collect.delay(
        trigger="manual",
        columnist_ids=[columnist_id] if columnist_id else None,
    )
    return {"queued": True}


@router.get("/stats")
def stats(db: Session = Depends(get_db), _: str = Depends(current_user)) -> dict:
    total = db.scalar(select(func.count(Article.id))) or 0
    unread = db.scalar(
        select(func.count(Article.id))
        .where(Article.is_read.is_(False))
        .where(Article.is_archived.is_(False))
    ) or 0
    audios_ready = db.scalar(
        select(func.count(Audio.id)).where(Audio.status == AudioStatus.ready)
    ) or 0
    audios_error = db.scalar(
        select(func.count(Audio.id)).where(Audio.status == AudioStatus.error)
    ) or 0
    active_sources = db.scalar(
        select(func.count(Columnist.id)).where(Columnist.active.is_(True))
    ) or 0
    last_run = db.scalar(
        select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(1)
    )

    return {
        "articles_total": total,
        "articles_unread": unread,
        "audios_ready": audios_ready,
        "audios_error": audios_error,
        "sources_active": active_sources,
        "last_run": {
            "at": last_run.started_at.isoformat() if last_run else None,
            "status": last_run.status.value if last_run else None,
            "new_articles": last_run.articles_new if last_run else 0,
            "sources_failed": last_run.sources_failed if last_run else 0,
        } if last_run else None,
    }
