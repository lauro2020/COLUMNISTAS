"""El recolector.

Recorre todas las fuentes activas, detecta artículos nuevos, los normaliza
y los guarda. Puede ejecutarse solo, sin la app web:

    python -m app.cli collect
    python -m app.cli collect --columnist 2

Principio de diseño: **una fuente que falla nunca detiene a las demás**.
Cada fuente se procesa dentro de su propio try/except, se registra el
resultado en `source_runs` y se sigue con la siguiente.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from urllib.parse import urlparse, urlunparse

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collector import dates, normalize, rss
from app.collector.extractors.base import ArticleRef, ExtractedArticle
from app.collector.extractors.registry import get_extractor
from app.collector.http_client import Fetcher
from app.models import (
    Article,
    Columnist,
    CollectionRun,
    MediaCredential,
    RunStatus,
    SourceRun,
    SourceType,
)
from app.security import decrypt_payload

log = logging.getLogger(__name__)

#: cuántos artículos candidatos se procesan como máximo por fuente y ejecución
MAX_ARTICLES_PER_SOURCE = 6
#: la PRIMERA vez que se recolecta una fuente se traen solo los más recientes,
#: para no volcar el archivo histórico del medio en la bandeja de hoy (ni pagar
#: la síntesis de voz de veinte columnas viejas por columnista)
MAX_ARTICLES_FIRST_RUN = 2
#: no se traen columnas más viejas que esto (evita reprocesar el archivo del medio)
MAX_AGE_DAYS = 10


class CollectionResult:
    def __init__(self) -> None:
        self.run_id: int | None = None
        self.new_article_ids: list[int] = []
        self.sources_total = 0
        self.sources_failed = 0


# ---------------------------------------------------------------------------
# Credenciales por medio
# ---------------------------------------------------------------------------
def cookies_for_outlet(db: Session, outlet: str) -> dict[str, str]:
    """Devuelve las cookies descifradas del medio, o {} si no hay."""
    cred = db.scalar(select(MediaCredential).where(MediaCredential.outlet == outlet))
    if not cred:
        return {}
    payload = decrypt_payload(cred.encrypted_payload)
    cookies = payload.get("cookies")
    if isinstance(cookies, dict):
        cred.last_used_at = dt.datetime.now(dt.timezone.utc)
        return {str(k): str(v) for k, v in cookies.items()}
    return {}


# ---------------------------------------------------------------------------
# Recolección
# ---------------------------------------------------------------------------
def collect_all(
    db: Session, *, trigger: str = "scheduled", columnist_ids: list[int] | None = None
) -> CollectionResult:
    query = select(Columnist).where(Columnist.active.is_(True))
    if columnist_ids:
        query = select(Columnist).where(Columnist.id.in_(columnist_ids))
    columnists = list(db.scalars(query).all())

    run = CollectionRun(trigger=trigger, sources_total=len(columnists))
    db.add(run)
    db.flush()

    result = CollectionResult()
    result.run_id = run.id
    result.sources_total = len(columnists)

    for columnist in columnists:
        started = time.monotonic()
        source_run = SourceRun(
            run_id=run.id,
            columnist_id=columnist.id,
            columnist_name=f"{columnist.name} ({columnist.outlet})",
        )
        notas: list[str] = []
        try:
            new_ids, found = collect_one(db, columnist, notas)
            source_run.status = RunStatus.ok if found else RunStatus.degraded
            source_run.articles_found = found
            source_run.articles_new = len(new_ids)
            source_run.extractor_used = columnist.extractor_key or "auto"
            # Cuando no entra nada nuevo hay que decir por qué. Antes la
            # pantalla de Fuentes se limitaba a «puede ser normal si no
            # publicó hoy», que tapaba por igual el día tranquilo y el
            # extractor roto.
            if not new_ids:
                if not notas:
                    source_run.error_message = (
                        "La fuente respondió pero no se encontró ningún "
                        "artículo. Puede ser normal si el columnista no "
                        "publicó hoy."
                    )
                else:
                    source_run.error_message = (
                        "No entró nada nuevo: " + resumen_notas(notas)
                    )
            columnist.consecutive_failures = 0
            columnist.last_success_at = dt.datetime.now(dt.timezone.utc)
            columnist.last_error = None
            result.new_article_ids.extend(new_ids)
        except Exception as exc:  # noqa: BLE001 - aislamos el fallo de esta fuente
            log.exception("Fallo al recolectar %s", columnist.name)
            source_run.status = RunStatus.error
            source_run.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            columnist.consecutive_failures += 1
            columnist.last_error = source_run.error_message
            result.sources_failed += 1
        finally:
            source_run.duration_ms = int((time.monotonic() - started) * 1000)
            db.add(source_run)
            db.flush()

    run.finished_at = dt.datetime.now(dt.timezone.utc)
    run.sources_failed = result.sources_failed
    run.articles_new = len(result.new_article_ids)
    if result.sources_failed == 0:
        run.status = RunStatus.ok
    elif result.sources_failed < len(columnists):
        run.status = RunStatus.degraded
    else:
        run.status = RunStatus.error
    db.flush()
    return result


def resumen_notas(notas: list[str]) -> str:
    """Agrupa los motivos de descarte en una frase corta y legible."""
    if not notas:
        return "sin detalle"
    cuenta: dict[str, int] = {}
    for nota in notas:
        cuenta[nota] = cuenta.get(nota, 0) + 1
    partes = [f"{n} {motivo}" if n > 1 else motivo for motivo, n in cuenta.items()]
    return "; ".join(partes)


def collect_one(
    db: Session, columnist: Columnist, notas: list[str] | None = None
) -> tuple[list[int], int]:
    """Recolecta una sola fuente. Devuelve (ids nuevos, artículos encontrados).

    En `notas`, si se pasa, se deja el motivo por el que cada candidato no
    acabó guardado. Es lo que permite responder «¿por qué no me llega nada
    de este columnista?» sin tener que leer los registros del contenedor.
    """
    apuntes = notas if notas is not None else []
    cookies = cookies_for_outlet(db, columnist.outlet)
    extractor = get_extractor(columnist.source_url, columnist.extractor_key)

    with Fetcher(
        cookies=cookies, browser_identity=columnist.browser_identity
    ) as fetcher:
        try:
            refs = _discover(columnist, extractor, fetcher, db)
            refs, descartes = _filter_candidates(db, columnist, refs)
            apuntes.extend(descartes)

            es_primera_vez = not db.scalar(
                select(func.count(Article.id)).where(
                    Article.columnist_id == columnist.id
                )
            )
            tope = MAX_ARTICLES_FIRST_RUN if es_primera_vez else MAX_ARTICLES_PER_SOURCE
            if len(refs) > tope:
                apuntes.append(
                    f"{len(refs) - tope} quedaron fuera del tope de {tope} por vuelta"
                )

            new_ids: list[int] = []
            for ref in refs[:tope]:
                try:
                    article = _extract_article(extractor, ref, fetcher)
                except Exception as exc:  # noqa: BLE001
                    log.warning("No se pudo extraer %s: %s", ref.url, exc)
                    apuntes.append(f"error al extraer ({type(exc).__name__})")
                    continue
                if article is None:
                    apuntes.append(
                        "la página no dejó extraer el texto "
                        "(¿muro de pago, o carga con JavaScript?)"
                    )
                    continue
                saved, motivo = _persist(db, columnist, article, ref)
                if saved is not None:
                    new_ids.append(saved)
                else:
                    apuntes.append(motivo)
        finally:
            # Si hubo que corregir el dominio (con o sin "www.") se guarda,
            # para no repetir la consulta fallida cada mañana. Si esto fallara,
            # no debe tapar el error real que trajo hasta aquí.
            try:
                _apply_host_swaps(db, columnist, fetcher.host_swaps)
            except Exception:  # noqa: BLE001
                log.warning("No se pudo guardar el dominio corregido de %s",
                            columnist.name, exc_info=True)

    return new_ids, len(refs)


def _apply_host_swaps(db: Session, columnist: Columnist, swaps: dict[str, str]) -> None:
    if not swaps:
        return
    for field in ("source_url", "feed_url"):
        value = getattr(columnist, field)
        if not value:
            continue
        parsed = urlparse(value)
        replacement = swaps.get(parsed.netloc)
        if replacement:
            fixed = urlunparse(parsed._replace(netloc=replacement))
            log.info("Corregido el dominio de %s: %s -> %s", columnist.name, value, fixed)
            setattr(columnist, field, fixed)
    db.flush()


def _discover(
    columnist: Columnist, extractor, fetcher: Fetcher, db: Session
) -> list[ArticleRef]:
    """Obtiene la lista de artículos candidatos, priorizando RSS."""
    wants_rss = columnist.source_type in (SourceType.rss, SourceType.auto)

    if wants_rss and columnist.feed_url:
        return rss.parse_feed(columnist.feed_url, fetcher)

    if wants_rss:
        # Intenta descubrir un feed una sola vez y lo guarda para el futuro
        page = fetcher.get(columnist.source_url)
        if page.ok:
            feed_url = rss.discover_feed_url(page.text, page.url)
            if feed_url:
                columnist.feed_url = feed_url
                db.flush()
                try:
                    return rss.parse_feed(feed_url, fetcher)
                except Exception as exc:  # noqa: BLE001
                    log.info("Feed descubierto pero ilegible (%s): %s", feed_url, exc)
            refs = extractor.discover_from_html(page.text, page.url)
            if refs:
                return refs
        if columnist.source_type == SourceType.rss:
            raise RuntimeError("No se encontró un feed RSS para esta fuente")

    return extractor.discover(columnist.source_url, fetcher)


def _filter_candidates(
    db: Session, columnist: Columnist, refs: list[ArticleRef]
) -> tuple[list[ArticleRef], list[str]]:
    """Descarta lo ya guardado y lo demasiado antiguo.

    Devuelve los candidatos que siguen vivos y, aparte, el motivo por el que
    se cayó cada uno de los demás.
    """
    if not refs:
        return [], []

    urls = [normalize.canonicalize_url(r.url) for r in refs]
    existing = set(
        db.scalars(select(Article.canonical_url).where(Article.canonical_url.in_(urls))).all()
    )

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_AGE_DAYS)
    fresh: list[ArticleRef] = []
    descartes: list[str] = []
    for ref in refs:
        ref.url = normalize.canonicalize_url(ref.url)
        # Muchas páginas de autor listan los enlaces sin fecha. Si la dirección
        # la lleva dentro, se aprovecha: así el filtro de antigüedad y el orden
        # "lo más nuevo primero" funcionan también en esas fuentes.
        if ref.published_at is None:
            ref.published_at = dates.from_url(ref.url)
        if ref.url in existing:
            descartes.append("ya estaban guardados")
            continue
        if ref.published_at and dates.ensure_aware(ref.published_at) < cutoff:
            descartes.append(f"más viejos de {MAX_AGE_DAYS} días")
            continue
        fresh.append(ref)

    # Los más recientes primero; los que no traen fecha van después
    fresh.sort(key=lambda r: (r.published_at is None, -(r.published_at or cutoff).timestamp()))
    return fresh, descartes


def _extract_article(extractor, ref: ArticleRef, fetcher: Fetcher) -> ExtractedArticle | None:
    """Extrae con el extractor del medio; si falla, con el genérico."""
    try:
        article = extractor.extract(ref.url, fetcher)
    except Exception as exc:  # noqa: BLE001
        log.info("Extractor %s falló en %s (%s); usando genérico", extractor.key, ref.url, exc)
        article = None

    if article is None:
        from app.collector.extractors.generic import GenericExtractor

        article = GenericExtractor().extract(ref.url, fetcher)

    if article and ref.published_at and not article.published_at:
        article.published_at = ref.published_at
    if article and ref.title and (not article.title or article.title == "Sin título"):
        article.title = ref.title
    if article:
        article.published_at = _mejor_fecha(article.published_at, ref.url)
    return article


#: cuánto puede discrepar la fecha de la página de la que trae la dirección
#: antes de considerar que la de la página es de otra nota (zona horaria y
#: "actualizado el…" caben de sobra en dos días)
TOLERANCIA_DE_FECHA = dt.timedelta(days=2)


def _mejor_fecha(leida: dt.datetime | None, url: str) -> dt.datetime | None:
    """Si la dirección trae fecha, casi siempre gana.

    Rascar la fecha del HTML es frágil: basta con que en la barra lateral
    asome una nota vieja para acabar fechando la columna de hoy hace un mes,
    y entonces desaparece del principio de la lista sin que nada dé error.
    La fecha que va dentro de la dirección (/2026/08/06/) no tiene ese
    problema, así que se usa cuando no hay otra o cuando la otra se aleja
    demasiado como para ser la misma columna.
    """
    de_url = dates.from_url(url)
    if de_url is None:
        return leida
    if leida is None:
        return de_url
    if abs(dates.ensure_aware(leida) - de_url) > TOLERANCIA_DE_FECHA:
        log.info(
            "Fecha corregida por la dirección: %s decía %s, la dirección dice %s",
            url, leida.date(), de_url.date(),
        )
        return de_url
    return leida


def _persist(
    db: Session, columnist: Columnist, extracted: ExtractedArticle, ref: ArticleRef
) -> tuple[int | None, str]:
    """Guarda el artículo. Devuelve (id, motivo); el id es None si no se guardó."""
    text = normalize.blocks_to_text(extracted.blocks)
    words = normalize.count_words(text)
    if words < 30 and not extracted.is_paywalled:
        log.info("Descartado por vacío: %s", extracted.canonical_url)
        return None, f"llegaron casi vacíos ({words} palabras)"

    digest = normalize.content_hash(extracted.title, text)
    canonical = normalize.canonicalize_url(extracted.canonical_url or ref.url)

    # Duplicado por URL canónica (republicación) o por contenido (edición menor)
    duplicate = db.scalar(
        select(Article).where(
            (Article.canonical_url == canonical)
            | ((Article.columnist_id == columnist.id) & (Article.content_hash == digest))
        )
    )
    if duplicate is not None:
        return None, "ya estaban guardados (mismo texto u otra dirección)"

    article = Article(
        columnist_id=columnist.id,
        title=extracted.title[:500],
        author=(extracted.author or columnist.name)[:200],
        outlet=(extracted.outlet or columnist.outlet)[:200],
        canonical_url=canonical,
        original_url=extracted.original_url or ref.url,
        published_at=dates.ensure_aware(extracted.published_at)
        or dt.datetime.now(dt.timezone.utc),
        body=extracted.blocks,
        plain_text=text,
        summary=extracted.summary or normalize.make_summary(text),
        content_hash=digest,
        word_count=words,
        reading_minutes=normalize.reading_minutes(words),
        is_paywalled=extracted.is_paywalled,
        extractor_used=extracted.extractor,
    )
    # Un choque de clave única (dos columnistas que comparten una columna
    # sindicada, por ejemplo) no puede tumbar el resto de la ejecución: se
    # deshace solo esta inserción y la transacción sigue viva.
    savepoint = db.begin_nested()
    try:
        db.add(article)
        db.flush()
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        log.info("La base de datos ya tenía este artículo: %s", canonical)
        return None, "ya estaban guardados"

    log.info("Nuevo artículo: %s — %s", columnist.name, article.title)
    return article.id, "guardado"
