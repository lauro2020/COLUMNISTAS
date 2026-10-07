"""Bandeja del día, búsqueda, lectura y estado de los artículos."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.common import article_item as _to_item
from app.api.common import day_bounds as _day_bounds
from app.api.common import local_tz as _tz
from app.api.deps import current_user, get_db
from app.models import Article, AudioStatus, CollectionRun
from app.schemas import (
    ArticleDetail,
    ArticleListItem,
    ArticleStateUpdate,
    AudioOut,
    InboxGroup,
    InboxResponse,
    ProgressUpdate,
)

router = APIRouter(prefix="/api/articles", tags=["artículos"])


# ---------------------------------------------------------------------------
# Bandeja del día
# ---------------------------------------------------------------------------
@router.get("/inbox", response_model=InboxResponse)
def inbox(
    date: dt.date | None = None,
    include_read: bool = True,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> InboxResponse:
    tz = _tz(db)
    day = date or dt.datetime.now(tz).date()
    start, end = _day_bounds(day, tz)

    query = (
        select(Article)
        .options(selectinload(Article.audios), selectinload(Article.columnist))
        .where(Article.is_archived.is_(False))
        .where(
            or_(
                Article.published_at.between(start, end),
                Article.collected_at.between(start, end),
            )
        )
        .order_by(Article.published_at.desc())
    )
    if not include_read:
        query = query.where(Article.is_read.is_(False))

    articles = list(db.scalars(query).all())

    grouped: dict[int, InboxGroup] = {}
    for article in articles:
        group = grouped.get(article.columnist_id)
        if group is None:
            group = InboxGroup(
                columnist_id=article.columnist_id,
                columnist_name=article.columnist.name if article.columnist else (article.author or "—"),
                outlet=article.outlet or (article.columnist.outlet if article.columnist else "—"),
                articles=[],
            )
            grouped[article.columnist_id] = group
        group.articles.append(_to_item(article))

    last_run = db.scalar(select(func.max(CollectionRun.finished_at)))

    return InboxResponse(
        date=day,
        total=len(articles),
        unread=sum(1 for a in articles if not a.is_read),
        groups=sorted(grouped.values(), key=lambda g: g.columnist_name),
        last_run_at=last_run,
    )


# ---------------------------------------------------------------------------
# Búsqueda y filtros
# ---------------------------------------------------------------------------
@router.get("", response_model=dict)
def search_articles(
    q: str | None = None,
    columnist_id: int | None = None,
    outlet: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    state: str | None = Query(default=None, description="unread|read|listened|favorite|archived|paywalled"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> dict:
    tz = _tz(db)
    query: Select = select(Article).options(
        selectinload(Article.audios), selectinload(Article.columnist)
    )
    count_query: Select = select(func.count(Article.id))

    filters = []
    if columnist_id:
        filters.append(Article.columnist_id == columnist_id)
    if outlet:
        filters.append(Article.outlet == outlet)
    if date_from:
        filters.append(Article.published_at >= dt.datetime.combine(date_from, dt.time.min, tzinfo=tz))
    if date_to:
        filters.append(
            Article.published_at < dt.datetime.combine(date_to, dt.time.min, tzinfo=tz) + dt.timedelta(days=1)
        )

    state_map = {
        "unread": Article.is_read.is_(False),
        "read": Article.is_read.is_(True),
        "listened": Article.is_listened.is_(True),
        "favorite": Article.is_favorite.is_(True),
        "archived": Article.is_archived.is_(True),
        "paywalled": Article.is_paywalled.is_(True),
    }
    if state in state_map:
        filters.append(state_map[state])
    if state != "archived":
        filters.append(Article.is_archived.is_(False))

    if q:
        # Búsqueda de texto completo en español (índice GIN sobre search_vector)
        ts_query = func.plainto_tsquery("spanish", q)
        filters.append(Article.search_vector.op("@@")(ts_query))
        rank = func.ts_rank(Article.search_vector, ts_query)
        query = query.order_by(rank.desc(), Article.published_at.desc())
    else:
        query = query.order_by(Article.published_at.desc())

    for condition in filters:
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = db.scalar(count_query) or 0
    rows = list(db.scalars(query.offset((page - 1) * size).limit(size)).all())

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_to_item(a).model_dump() for a in rows],
    }


# ---------------------------------------------------------------------------
# Detalle
# ---------------------------------------------------------------------------
@router.get("/{article_id}", response_model=ArticleDetail)
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> ArticleDetail:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese artículo")

    detail = ArticleDetail.model_validate(article)
    audio = article.audios[0] if article.audios else None
    if audio:
        detail.audio_id = audio.id
        detail.audio_status = audio.status
        detail.audio_duration = audio.duration_seconds
        detail.audio = AudioOut.model_validate(audio)
        if audio.status == AudioStatus.ready:
            detail.audio.url = f"/api/audio/{audio.id}/file"
    return detail


@router.patch("/{article_id}/state", response_model=ArticleListItem)
def update_state(
    article_id: int,
    payload: ArticleStateUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> ArticleListItem:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese artículo")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(article, field, value)
    if data.get("is_read") and article.read_at is None:
        article.read_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(article)
    return _to_item(article)


@router.post("/{article_id}/progress", response_model=ArticleListItem)
def update_progress(
    article_id: int,
    payload: ProgressUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> ArticleListItem:
    """Guarda dónde me quedé (se sincroniza entre dispositivos)."""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese artículo")

    if payload.audio_position_seconds is not None:
        article.audio_position_seconds = max(0.0, payload.audio_position_seconds)
    if payload.reading_paragraph_index is not None:
        article.reading_paragraph_index = max(0, payload.reading_paragraph_index)
    if payload.mark_listened:
        article.is_listened = True
        article.is_read = True
        if article.read_at is None:
            article.read_at = dt.datetime.now(dt.timezone.utc)
    article.progress_updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(article)
    return _to_item(article)


@router.post("/mark-all-read")
def mark_all_read(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> dict:
    tz = _tz(db)
    day = date or dt.datetime.now(tz).date()
    start, end = _day_bounds(day, tz)

    articles = db.scalars(
        select(Article)
        .where(Article.is_read.is_(False))
        .where(Article.is_archived.is_(False))
        .where(or_(Article.published_at.between(start, end),
                   Article.collected_at.between(start, end)))
    ).all()
    now = dt.datetime.now(dt.timezone.utc)
    for article in articles:
        article.is_read = True
        article.read_at = article.read_at or now
    db.commit()
    return {"updated": len(articles)}


# ---------------------------------------------------------------------------
# Paquete para uso sin conexión
# ---------------------------------------------------------------------------
@router.get("/offline/bundle")
def offline_bundle(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> dict:
    """Lista de recursos que la PWA debe descargar para funcionar sin internet."""
    tz = _tz(db)
    day = date or dt.datetime.now(tz).date()
    start, end = _day_bounds(day, tz)

    articles = db.scalars(
        select(Article)
        .options(selectinload(Article.audios))
        .where(Article.is_archived.is_(False))
        .where(or_(Article.published_at.between(start, end),
                   Article.collected_at.between(start, end)))
    ).all()

    resources = []
    for article in articles:
        resources.append(f"/api/articles/{article.id}")
        audio = article.audios[0] if article.audios else None
        if audio and audio.status == AudioStatus.ready:
            resources.append(f"/api/audio/{audio.id}/file")

    return {"date": day.isoformat(), "count": len(articles), "resources": resources}
