"""Alta, baja y edición de columnistas (todo desde la interfaz)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.collector import normalize, rss
from app.collector.extractors.registry import extractor_keys, get_extractor
from app.collector.http_client import Fetcher
from app.models import Article, Columnist
from app.schemas import ColumnistCreate, ColumnistOut, ColumnistUpdate

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

    with Fetcher(cookies=cookies) as fetcher:
        try:
            if columnist.feed_url:
                refs = rss.parse_feed(columnist.feed_url, fetcher)
                origen = f"RSS ({columnist.feed_url})"
            else:
                page = fetcher.get(columnist.source_url)
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
