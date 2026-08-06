"""Alta, baja y edición de columnistas (todo desde la interfaz)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.common import article_item as _article_item
from app.api.common import local_tz as _tz
from app.api.common import overview_sort_key, recent_cutoff
from app.api.deps import current_user, get_db
from app.collector import normalize, rss
from app.collector.extractors.registry import extractor_keys, get_extractor
from app.collector.http_client import Fetcher
from app.models import Article, CollectionRun, Columnist
from app.schemas import (
    ColumnistCreate,
    ColumnistOut,
    ColumnistOverview,
    ColumnistUpdate,
    OverviewResponse,
)

router = APIRouter(prefix="/api/columnists", tags=["columnistas"])


def _to_out(db: Session, columnist: Columnist) -> ColumnistOut:
    total = db.scalar(
        select(func.count(Article.id)).where(Article.columnist_id == columnist.id)
    ) or 0
    unread = db.scalar(
        select(func.count(Article.id))
        .where(Article.columnist_id == columnist.id)
        .where(Article.is_read.is_(False))
        .where(Article.is_archived.is_(False))
    ) or 0
    data = ColumnistOut.model_validate(columnist)
    data.article_count = total
    data.unread_count = unread
    return data


@router.get("", response_model=list[ColumnistOut])
def list_columnists(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> list[ColumnistOut]:
    query = select(Columnist).order_by(Columnist.name)
    if not include_inactive:
        query = query.where(Columnist.active.is_(True))
    return [_to_out(db, c) for c in db.scalars(query).all()]


@router.post("", response_model=ColumnistOut, status_code=status.HTTP_201_CREATED)
def create_columnist(
    payload: ColumnistCreate,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> ColumnistOut:
    exists = db.scalar(
        select(Columnist)
        .where(Columnist.name == payload.name)
        .where(Columnist.outlet == payload.outlet)
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese columnista ya está dado de alta")

    columnist = Columnist(**payload.model_dump())
    columnist.source_url = normalize.canonicalize_url(columnist.source_url)
    db.add(columnist)
    db.commit()
    db.refresh(columnist)
    return _to_out(db, columnist)


@router.patch("/{columnist_id}", response_model=ColumnistOut)
def update_columnist(
    columnist_id: int,
    payload: ColumnistUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> ColumnistOut:
    columnist = db.get(Columnist, columnist_id)
    if columnist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese columnista")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(columnist, field, value)
    if payload.source_url:
        columnist.source_url = normalize.canonicalize_url(payload.source_url)
    db.commit()
    db.refresh(columnist)
    return _to_out(db, columnist)


@router.delete(
    "/{columnist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
)
def delete_columnist(
    columnist_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> None:
    columnist = db.get(Columnist, columnist_id)
    if columnist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese columnista")
    db.delete(columnist)
    db.commit()


@router.get("/extractors", response_model=list[str])
def list_extractors(_: str = Depends(current_user)) -> list[str]:
    return extractor_keys()


@router.get("/overview", response_model=OverviewResponse)
def overview(
    recent_days: int = Query(default=15, ge=1, le=365),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> OverviewResponse:
    """Todos los columnistas de un vistazo, con su último artículo.

    Es la pantalla de inicio: una fila por columnista, para ver en un golpe de
    vista quién publicó hoy, quién publicó hace poco y quién lleva tiempo sin
    aparecer. El último artículo solo se devuelve si entra en la ventana
    reciente; si es más viejo, se manda la fecha para poder decir cuánto hace.
    """
    tz = _tz(db)
    hoy = dt.datetime.now(tz).date()
    corte = recent_cutoff(hoy, recent_days, tz)

    query = select(Columnist).order_by(Columnist.name)
    if not include_inactive:
        query = query.where(Columnist.active.is_(True))
    columnists = list(db.scalars(query).all())

    # Un solo viaje a la base de datos para el último artículo de cada uno
    ultimos = {
        article.columnist_id: article
        for article in db.scalars(
            select(Article)
            .options(selectinload(Article.audios))
            .where(Article.is_archived.is_(False))
            .order_by(Article.columnist_id, Article.published_at.desc().nullslast())
            .distinct(Article.columnist_id)
        ).all()
    }
    totales = dict(
        db.execute(
            select(Article.columnist_id, func.count(Article.id))
            .where(Article.is_archived.is_(False))
            .group_by(Article.columnist_id)
        ).all()
    )

    filas: list[ColumnistOverview] = []
    for columnist in columnists:
        ultimo = ultimos.get(columnist.id)
        fila = ColumnistOverview(
            columnist_id=columnist.id,
            name=columnist.name,
            outlet=columnist.outlet,
            active=columnist.active,
            total_articles=totales.get(columnist.id, 0),
            consecutive_failures=columnist.consecutive_failures,
            last_error=columnist.last_error,
        )

        if ultimo is not None and ultimo.published_at is not None:
            publicado = ultimo.published_at.astimezone(tz)
            fila.last_published_at = ultimo.published_at
            fila.days_since_last = (hoy - publicado.date()).days
            fila.published_today = publicado.date() == hoy
            if ultimo.published_at >= corte:
                fila.latest = _article_item(ultimo)

        filas.append(fila)

    filas.sort(key=lambda f: overview_sort_key(
        f.published_today, f.days_since_last, f.name))

    return OverviewResponse(
        date=hoy,
        recent_days=recent_days,
        total_columnists=len(filas),
        with_recent=sum(1 for f in filas if f.latest is not None),
        published_today=sum(1 for f in filas if f.published_today),
        last_run_at=db.scalar(select(func.max(CollectionRun.finished_at))),
        columnists=filas,
    )


@router.post("/{columnist_id}/test")
def test_columnist(
    columnist_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(current_user),
) -> dict:
    """Prueba la fuente EN VIVO sin guardar nada.

    Sirve para comprobar, al dar de alta un columnista, que la URL es
    correcta y que el extractor encuentra artículos.
    """
    columnist = db.get(Columnist, columnist_id)
    if columnist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese columnista")

    from app.collector.runner import cookies_for_outlet

    cookies = cookies_for_outlet(db, columnist.outlet)
    extractor = get_extractor(columnist.source_url, columnist.extractor_key)

    with Fetcher(
        cookies=cookies, browser_identity=columnist.browser_identity
    ) as fetcher:
        try:
            if columnist.feed_url:
                refs = rss.parse_feed(columnist.feed_url, fetcher)
                origen = f"RSS ({columnist.feed_url})"
            else:
                page = fetcher.get(columnist.source_url)
                usó_navegador = False
                if not page.ok:
                    # Segundo intento con el navegador headless, igual que hace
                    # la recolección real (solo si está habilitado en el .env).
                    retry = fetcher.get(columnist.source_url, use_browser=True)
                    if retry.ok:
                        page, usó_navegador = retry, True
                if not page.ok:
                    return {
                        "ok": False,
                        "origen": "página del autor",
                        "error": page.error,
                        "articulos": [],
                    }
                feed_url = rss.discover_feed_url(page.text, page.url)
                if feed_url:
                    columnist.feed_url = feed_url
                    db.commit()
                    refs = rss.parse_feed(feed_url, fetcher)
                    origen = f"RSS descubierto ({feed_url})"
                else:
                    refs = extractor.discover_from_html(page.text, page.url)
                    origen = f"HTML con extractor «{extractor.key}»"
                    if usó_navegador:
                        origen += " (a través del navegador headless)"
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "origen": "desconocido", "error": str(exc), "articulos": []}

        muestra = []
        for ref in refs[:5]:
            muestra.append({
                "url": ref.url,
                "titulo": ref.title,
                "fecha": ref.published_at.isoformat() if ref.published_at else None,
            })

        preview = None
        if refs:
            try:
                article = extractor.extract(refs[0].url, fetcher)
                if article:
                    preview = {
                        "titulo": article.title,
                        "parrafos": len(article.blocks),
                        "palabras": normalize.count_words(
                            normalize.blocks_to_text(article.blocks)
                        ),
                        "muro_de_pago": article.is_paywalled,
                        "extractor": article.extractor,
                        "primer_parrafo": article.blocks[0]["text"][:400] if article.blocks else None,
                    }
            except Exception as exc:  # noqa: BLE001
                preview = {"error": str(exc)}

    return {
        "ok": bool(refs),
        "origen": origen,
        "encontrados": len(refs),
        "articulos": muestra,
        "muestra_extraccion": preview,
    }
