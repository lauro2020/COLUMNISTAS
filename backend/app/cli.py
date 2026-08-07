"""Línea de comandos.

Cada componente se puede ejecutar y probar por separado:

    python -m app.cli migrate                 # crea/actualiza las tablas
    python -m app.cli seed                    # carga los columnistas iniciales
    python -m app.cli collect                 # recolecta ahora mismo
    python -m app.cli collect --columnist 2   # solo una fuente
    python -m app.cli audio --article 12      # genera el audio de un artículo
    python -m app.cli audio --missing         # genera todos los que falten
    python -m app.cli status                  # resumen del sistema
    python -m app.cli check-password          # ¿por qué no me deja entrar?
    python -m app.cli check-sources           # prueba TODAS las fuentes
    python -m app.cli why "riva palacio"      # ¿por qué no llega nada de éste?
    python -m app.cli test-source 3           # prueba una fuente sin guardar
    python -m app.cli download-piper-voice es_MX-ald-medium
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
from pathlib import Path

from sqlalchemy import func, select

from app import seed as seed_module
from app.config import settings
from app.db import session_scope

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("cli")

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_PATHS = {
    "es_MX-ald-medium": "es/es_MX/ald/medium/es_MX-ald-medium",
    "es_MX-claude-high": "es/es_MX/claude/high/es_MX-claude-high",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "es_ES-sharvard-medium": "es/es_ES/sharvard/medium/es_ES-sharvard-medium",
    "es_AR-daniela-high": "es/es_AR/daniela/high/es_AR-daniela-high",
}


# ---------------------------------------------------------------------------
def cmd_migrate(_: argparse.Namespace) -> int:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")
    print("✓ Base de datos actualizada")
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    with session_scope() as db:
        result = seed_module.run(db)
    print(f"✓ Semilla aplicada: {result}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from app.collector.runner import collect_all

    ids = [args.columnist] if args.columnist else None
    with session_scope() as db:
        result = collect_all(db, trigger="manual", columnist_ids=ids)
        new_ids = list(result.new_article_ids)
        failed = result.sources_failed
        total = result.sources_total

    print(f"✓ Recolección terminada: {len(new_ids)} artículos nuevos "
          f"({failed}/{total} fuentes con error)")

    if new_ids and not args.no_audio:
        from app.audio.pipeline import generate_for_article

        for article_id in new_ids:
            with session_scope() as db:
                audio = generate_for_article(db, article_id)
                print(f"  audio artículo {article_id}: {audio.status.value}"
                      f"{' — ' + audio.error_message if audio.error_message else ''}")
    return 0


def cmd_audio(args: argparse.Namespace) -> int:
    from app.audio.pipeline import generate_for_article
    from app.models import Article, Audio, AudioStatus

    if args.article:
        with session_scope() as db:
            audio = generate_for_article(db, args.article, force=args.force,
                                         voice=args.voice, provider_key=args.provider)
            print(f"{audio.status.value}: {audio.file_path} "
                  f"({audio.duration_seconds or 0:.0f} s)")
            if audio.error_message:
                print(f"  error: {audio.error_message}")
        return 0

    if args.missing:
        with session_scope() as db:
            pending = list(db.scalars(
                select(Article.id)
                .outerjoin(Audio, Audio.article_id == Article.id)
                .where((Audio.id.is_(None)) | (Audio.status.in_([AudioStatus.pending, AudioStatus.error])))
                .order_by(Article.published_at.desc())
                .limit(args.limit)
            ).all())
        print(f"Generando audio de {len(pending)} artículos…")
        for article_id in pending:
            with session_scope() as db:
                audio = generate_for_article(db, article_id, force=args.force)
                print(f"  {article_id}: {audio.status.value}")
        return 0

    print("Indica --article <id> o --missing", file=sys.stderr)
    return 1


def cmd_status(_: argparse.Namespace) -> int:
    from app.models import Article, Audio, AudioStatus, CollectionRun, Columnist

    with session_scope() as db:
        columnists = db.scalars(select(Columnist).order_by(Columnist.name)).all()
        total = db.scalar(select(func.count(Article.id))) or 0
        ready = db.scalar(select(func.count(Audio.id)).where(Audio.status == AudioStatus.ready)) or 0
        last = db.scalar(select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(1))

        print(f"\nArtículos: {total}   Audios listos: {ready}")
        if last:
            print(f"Última recolección: {last.started_at:%Y-%m-%d %H:%M} UTC "
                  f"— {last.status.value}, {last.articles_new} nuevos, "
                  f"{last.sources_failed}/{last.sources_total} con error")

        # El historial importa: un día sin línea aquí es un día en que la
        # recolección no llegó a ejecutarse (la computadora estuvo apagada, o
        # los contenedores parados), y eso explica de golpe a varios
        # columnistas que "se quedaron atrás".
        recientes = db.scalars(
            select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(10)
        ).all()
        if len(recientes) > 1:
            print("\nÚltimas recolecciones (si falta un día, ese día no se ejecutó):")
            for r in recientes:
                print(f"  {r.started_at:%d/%m %H:%M} UTC  {r.trigger:<9} "
                      f"{r.status.value:<8} {r.articles_new:>3} nuevos  "
                      f"{r.sources_failed}/{r.sources_total} con error")

        print("\nFuentes:")
        for c in columnists:
            estado = "✓" if c.consecutive_failures == 0 else f"✗ x{c.consecutive_failures}"
            activo = "" if c.active else "  (inactivo)"
            print(f"  [{c.id:>3}] {estado}  {c.name} — {c.outlet}{activo}")
            if c.last_error:
                print(f"        último error: {c.last_error[:120]}")
    print()
    return 0


def cmd_test_source(args: argparse.Namespace) -> int:
    from app.collector.extractors.registry import get_extractor
    from app.collector.http_client import Fetcher
    from app.collector.runner import cookies_for_outlet
    from app.models import Columnist

    with session_scope() as db:
        columnist = db.get(Columnist, args.columnist_id)
        if columnist is None:
            print("No existe ese columnista", file=sys.stderr)
            return 1
        cookies = cookies_for_outlet(db, columnist.outlet)
        extractor = get_extractor(columnist.source_url, columnist.extractor_key)
        print(f"Fuente: {columnist.name} ({columnist.outlet})")
        print(f"Extractor: {extractor.key}")
        if columnist.browser_identity:
            print("Identificación: navegador")
        with Fetcher(
            cookies=cookies, browser_identity=columnist.browser_identity
        ) as fetcher:
            refs = extractor.discover(columnist.source_url, fetcher)
            print(f"Artículos detectados: {len(refs)}")
            for ref in refs[:5]:
                print(f"  · {ref.title or '(sin título)'}\n    {ref.url}")
            if refs:
                article = extractor.extract(refs[0].url, fetcher)
                if article:
                    print(f"\nExtracción de muestra: «{article.title}»")
                    print(f"  párrafos: {len(article.blocks)}  "
                          f"muro de pago: {article.is_paywalled}")
                    if article.blocks:
                        print(f"  inicio: {article.blocks[0]['text'][:200]}…")
    return 0


def _autopsia_de_la_pagina(columnist, fetcher) -> None:
    """Cuando no se reconoce ningún artículo, describir la página.

    Es lo que hace falta para escribir el extractor que le falta a ese medio,
    y no se puede adivinar desde fuera: hay que ver cómo agrupa sus enlaces,
    si trae un feed escondido, y si el listado lo pinta el servidor o el
    JavaScript del navegador.
    """
    from collections import Counter
    from urllib.parse import urljoin, urlparse

    from bs4 import BeautifulSoup

    from app.collector import rss

    print("\n  Radiografía de la página, para saber qué extractor le falta:\n")

    pagina = fetcher.get(columnist.source_url)
    if not pagina.ok:
        print(f"    No se pudo releer: {pagina.error}")
        return

    html = pagina.text or ""
    soup = BeautifulSoup(html, "lxml")
    print(f"    Dirección final   {pagina.url}")
    print(f"    Tamaño            {len(html):,} caracteres")

    # ¿La pinta el servidor o el navegador?
    pistas_js = [n for n in ("__NEXT_DATA__", "__NUXT__", "Fusion.globalContent",
                             "window.__INITIAL_STATE__", "application/ld+json")
                 if n in html]
    print(f"    Datos incrustados {', '.join(pistas_js) if pistas_js else 'ninguno reconocible'}")

    # ¿Hay un feed que nos ahorre el trabajo?
    feed = rss.discover_feed_url(html, pagina.url)
    if feed:
        print(f"    Feed anunciado    {feed}   ← con esto basta")
    else:
        print("    Feed anunciado    no")

    enlaces = [a.get("href") for a in soup.find_all("a", href=True)]
    absolutos = []
    for href in enlaces:
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        completo = urljoin(pagina.url, href)
        if urlparse(completo).netloc == urlparse(pagina.url).netloc:
            absolutos.append(urlparse(completo).path)

    print(f"    Enlaces al propio medio  {len(absolutos)}")
    if not absolutos:
        print("\n    Cero enlaces internos: la lista la pinta el JavaScript.")
        print("    Prueba a activar el navegador headless para este columnista")
        print("    (Ajustes › Columnistas › Editar › «Identificarse como")
        print("    navegador») y vuelve a ejecutar esto.")
        return

    # Agrupar por los dos primeros tramos de la ruta: ahí se ve enseguida
    # dónde vive el contenido y dónde el menú de navegación.
    def familia(path: str) -> str:
        tramos = [t for t in path.split("/") if t]
        return "/" + "/".join(tramos[:2]) if tramos else "/"

    grupos = Counter(familia(p) for p in absolutos)
    print("\n    Cómo se agrupan esos enlaces (los 12 grupos mayores):\n")
    for prefijo, cuantos in grupos.most_common(12):
        ejemplo = next(p for p in absolutos if familia(p) == prefijo)
        print(f"      {cuantos:>4}  {prefijo:<28}  p.ej. {ejemplo[:60]}")

    print("\n    Pega esta radiografía y se puede escribir el extractor que falta.")


def cmd_fix_dates(args: argparse.Namespace) -> int:
    """Corrige las fechas mal leídas de los artículos ya guardados.

    Cuando la fecha se sacaba del texto de la página se podía colar la de una
    nota vecina, y entonces una columna de ayer quedaba fechada hace meses y
    desaparecía del principio de la lista. La dirección del artículo suele
    llevar la fecha buena (/2026/08/06/): esto la recupera.
    """
    from app.collector import dates as fechas
    from app.collector.runner import TOLERANCIA_DE_FECHA
    from app.models import Article

    with session_scope() as db:
        articulos = db.scalars(select(Article).order_by(Article.id)).all()
        cambios = []
        for art in articulos:
            de_url = fechas.from_url(art.canonical_url) or fechas.from_url(art.original_url)
            if de_url is None or art.published_at is None:
                continue
            if abs(fechas.ensure_aware(art.published_at) - de_url) <= TOLERANCIA_DE_FECHA:
                continue
            cambios.append((art, fechas.ensure_aware(art.published_at), de_url))

        if not cambios:
            print("\n✓ Ninguna fecha que corregir: todas concuerdan con su dirección.\n")
            return 0

        print(f"\n{len(cambios)} artículo(s) con la fecha equivocada:\n")
        for art, antes, despues in cambios:
            print(f"  {antes:%d/%m/%Y} → {despues:%d/%m/%Y}   {art.title[:52]}")

        if not args.apply:
            print("\n  Esto ha sido solo una vista previa; no se ha tocado nada.")
            print("  Para aplicarlo:   python -m app.cli fix-dates --apply\n")
            return 0

        for art, _, despues in cambios:
            art.published_at = despues
        db.flush()
        print(f"\n✓ {len(cambios)} fecha(s) corregida(s).\n")

    return 0


def _buscar_columnista(db, aguja: str):
    """Encuentra un columnista por id o por un trozo de su nombre."""
    from app.models import Columnist

    if aguja.isdigit():
        return db.get(Columnist, int(aguja)), []

    patron = f"%{aguja.strip().lower()}%"
    encontrados = list(
        db.scalars(
            select(Columnist).where(func.lower(Columnist.name).like(patron))
            .order_by(Columnist.name)
        ).all()
    )
    if len(encontrados) == 1:
        return encontrados[0], []
    return None, encontrados


def cmd_why(args: argparse.Namespace) -> int:
    """Explica, artículo por artículo, por qué no llega nada de una fuente.

    `check-sources` dice si la fuente responde; esto va un paso más allá y
    reproduce en vivo lo que hace la recolección de cada mañana, enseñando
    el veredicto de cada candidato: si ya estaba guardado, si es demasiado
    viejo, si llegó vacío por un muro de pago, o si sí entraría.
    """
    import datetime as dt

    # Este comando se lee, no se depura: los apuntes de httpx sobre cada
    # petición estorban más de lo que ayudan.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from app.collector import dates as fechas
    from app.collector import normalize
    from app.collector.extractors.registry import get_extractor
    from app.collector.http_client import Fetcher
    from app.collector.runner import (
        MAX_AGE_DAYS,
        MAX_ARTICLES_FIRST_RUN,
        MAX_ARTICLES_PER_SOURCE,
        _discover,
        cookies_for_outlet,
    )
    from app.models import Article

    with session_scope() as db:
        columnist, parecidos = _buscar_columnista(db, args.columnista)
        if columnist is None:
            if parecidos:
                print("Hay varios que encajan. Repite con el número:\n", file=sys.stderr)
                for c in parecidos:
                    print(f"  {c.id:>4}  {c.name} ({c.outlet})", file=sys.stderr)
            else:
                print(f"No encontré ningún columnista con «{args.columnista}».",
                      file=sys.stderr)
                print("Lista completa:   python -m app.cli check-sources", file=sys.stderr)
            return 1

        print(f"\n{'=' * 74}")
        print(f"  {columnist.name} — {columnist.outlet}   (id {columnist.id})")
        print(f"{'=' * 74}")
        print(f"  Página        {columnist.source_url}")
        if columnist.feed_url:
            print(f"  Feed RSS      {columnist.feed_url}")
        print(f"  Extractor     {get_extractor(columnist.source_url, columnist.extractor_key).key}")
        print(f"  Activo        {'sí' if columnist.active else 'NO — no se recolecta'}")
        if columnist.browser_identity:
            print("  Identidad     se hace pasar por navegador")
        if columnist.consecutive_failures:
            print(f"  Fallos        {columnist.consecutive_failures} seguidos")
        if columnist.last_error:
            print(f"  Último error  {columnist.last_error[:200]}")

        # --- Lo que ya está guardado ---------------------------------------
        guardados = list(
            db.scalars(
                select(Article)
                .where(Article.columnist_id == columnist.id)
                .order_by(Article.published_at.desc())
                .limit(5)
            ).all()
        )
        total = db.scalar(
            select(func.count(Article.id)).where(Article.columnist_id == columnist.id)
        ) or 0
        print(f"\n  Ya guardados: {total}")
        for art in guardados:
            fecha = art.published_at.strftime("%d/%m/%Y") if art.published_at else "sin fecha"
            print(f"    {fecha}  {art.title[:56]}")
        if not guardados:
            print("    (ninguno todavía)")

        cookies = cookies_for_outlet(db, columnist.outlet)
        extractor = get_extractor(columnist.source_url, columnist.extractor_key)
        es_primera_vez = total == 0
        tope = MAX_ARTICLES_FIRST_RUN if es_primera_vez else MAX_ARTICLES_PER_SOURCE

        print(f"\n{'-' * 74}")
        print("  Lo que ve la recolección AHORA MISMO en la página del autor")
        print(f"{'-' * 74}")

        with Fetcher(
            cookies=cookies, browser_identity=columnist.browser_identity
        ) as fetcher:
            try:
                refs = _discover(columnist, extractor, fetcher, db)
            except Exception as exc:  # noqa: BLE001
                print(f"\n  ✗ Ni siquiera se pudo abrir la fuente:\n    {exc}\n")
                print("  Esto es un problema de acceso, no de extracción. Prueba:")
                print("    python -m app.cli doctor\n")
                return 1

            if not refs:
                print("\n  ✗ La página abre, pero no se reconoció ningún artículo en ella.")

                # Antes de dar el parte, probar con el navegador: si el medio
                # pinta la lista con JavaScript, esto la resuelve de una vez.
                con_navegador = fetcher.get(columnist.source_url, use_browser=True)
                if con_navegador.ok:
                    refs = extractor.discover_from_html(
                        con_navegador.text, con_navegador.url
                    )
                if refs:
                    print(f"\n  ✓ Pero con el navegador headless sí: {len(refs)} artículos.")
                    print("    Esta fuente pinta su lista con JavaScript. Actívaselo en")
                    print("    Ajustes › Columnistas › Editar › «Identificarse como")
                    print("    navegador», y comprueba que ENABLE_HEADLESS_BROWSER e")
                    print("    INSTALL_PLAYWRIGHT estén en «true» dentro del .env.\n")
                    return 0

                _autopsia_de_la_pagina(columnist, fetcher)
                return 1

            urls = [normalize.canonicalize_url(r.url) for r in refs]
            existentes = set(
                db.scalars(
                    select(Article.canonical_url).where(Article.canonical_url.in_(urls))
                ).all()
            )
            corte = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_AGE_DAYS)

            print(f"\n  Encontró {len(refs)} enlaces. Veredicto de cada uno:\n")

            candidatos = []
            for ref in refs[: args.limit]:
                ref.url = normalize.canonicalize_url(ref.url)
                fecha = fechas.ensure_aware(ref.published_at) if ref.published_at else None
                etiqueta = fecha.strftime("%d/%m/%Y") if fecha else "sin fecha"
                # Muchas páginas de autor no traen el titular en el enlace; en
                # ese caso el final de la dirección se lee lo bastante bien.
                titulo = ref.title or ref.url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")

                if ref.url in existentes:
                    veredicto = "· ya guardado"
                elif fecha and fecha < corte:
                    veredicto = f"· descartado por viejo (más de {MAX_AGE_DAYS} días)"
                else:
                    veredicto = "→ CANDIDATO"
                    candidatos.append(ref)
                print(f"    {etiqueta:>10}  {str(titulo)[:44]:<46} {veredicto}")

            if len(refs) > args.limit:
                print(f"    … y {len(refs) - args.limit} más (usa --limit para verlos)")

            if not candidatos:
                print("\n  → Todo lo que publica esta página ya está en tu base de datos,")
                print("    o es más viejo que el límite. Si esperabas una columna de hoy")
                print("    y no aparece arriba, es que el medio todavía no la ha puesto")
                print("    en la página del autor.\n")
                return 0

            print(f"\n  {len(candidatos)} candidato(s) nuevo(s). "
                  f"La recolección procesa {tope} por vuelta.")
            print(f"\n{'-' * 74}")
            print("  Extrayendo el texto de los candidatos (esto es lo que suele fallar)")
            print(f"{'-' * 74}\n")

            problemas = []
            for ref in candidatos[: args.limit]:
                try:
                    article = extractor.extract(ref.url, fetcher)
                except Exception as exc:  # noqa: BLE001
                    print(f"    ✗ {ref.url}")
                    print(f"      Error al extraer: {type(exc).__name__}: {exc}")
                    problemas.append("error")
                    continue
                if article is None:
                    print(f"    ✗ {ref.url}")
                    print("      No se pudo sacar el texto de la página.")
                    problemas.append("sin texto")
                    continue

                texto = normalize.blocks_to_text(article.blocks)
                palabras = normalize.count_words(texto)
                if palabras < 30 and not article.is_paywalled:
                    marca, nota = "✗", f"solo {palabras} palabras: SE DESCARTA por vacío"
                    problemas.append("vacío")
                elif article.is_paywalled:
                    marca, nota = "~", f"{palabras} palabras, detectado MURO DE PAGO"
                    problemas.append("muro de pago")
                else:
                    marca, nota = "✓", f"{palabras} palabras: se guardaría"
                print(f"    {marca} «{article.title[:56]}»")
                print(f"      {nota}")
                if article.blocks:
                    print(f"      empieza: {article.blocks[0]['text'][:110]}…")
                print()

        # --- Qué hacer -----------------------------------------------------
        print(f"\n{'-' * 74}")
        print("  Qué hacer")
        print(f"{'-' * 74}")
        if not problemas:
            print("\n  Nada está roto. Estos artículos entrarán en la próxima")
            print("  recolección. Para no esperar a mañana:")
            print(f"    python -m app.cli collect --columnist {columnist.id}\n")
        elif "muro de pago" in problemas or "vacío" in problemas:
            print("\n  El medio está sirviendo la columna recortada: la app llega a")
            print("  la página pero solo recibe el primer párrafo o nada.")
            print("\n  1. Guarda tus cookies de suscriptor de este medio:")
            print("     en la app, Ajustes › Credenciales por medio ›")
            print(f"     «{columnist.outlet}».")
            print("  2. Si ya las tienes guardadas, puede que hayan caducado:")
            print("     vuelve a copiarlas desde el navegador.")
            print("  3. Si no eres suscriptor de este medio, no hay nada que")
            print("     hacer: la app solo puede leer lo que tú puedes leer.\n")
        else:
            print("\n  La página del autor se lee, pero los artículos no. Suele ser")
            print("  que el medio cambió la plantilla. Prueba a activar el navegador")
            print("  headless para este columnista (Ajustes › Columnistas › Editar ›")
            print("  «Identificarse como navegador») y vuelve a ejecutar esto.\n")

    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    """Comprueba la red del contenedor: DNS y acceso HTTPS a cada fuente.

    Es el primer sitio al que mirar cuando una fuente falla: distingue entre
    «no resuelve el nombre» (problema de red o de DNS de Docker), «no deja
    entrar» (bloqueo del medio) y «entra pero no encuentra artículos»
    (problema del extractor).
    """
    import socket
    from urllib.parse import urlparse

    from app.collector.http_client import Fetcher, alternate_host_url
    from app.models import Columnist

    def resolve(host: str) -> str:
        try:
            infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            return f"OK  {infos[0][4][0]}"
        except Exception as exc:  # noqa: BLE001
            return f"FALLA  ({exc})"

    with session_scope() as db:
        fuentes = [
            (c.name, c.outlet, c.source_url)
            for c in db.scalars(select(Columnist).order_by(Columnist.name)).all()
        ]

    print("\n" + "=" * 72)
    print("DIAGNÓSTICO DE RED DESDE EL CONTENEDOR")
    print("=" * 72)

    print("\n1) ¿Hay internet y DNS en general?")
    for host in ("example.com", "google.com", "api.openai.com"):
        print(f"   {host:<28} {resolve(host)}")

    print("\n2) ¿Resuelven los dominios de tus fuentes?")
    print("   (se prueba también la variante con o sin «www.»)")
    for name, outlet, url in fuentes:
        host = urlparse(url).netloc
        alternate = urlparse(alternate_host_url(url) or "").netloc
        print(f"\n   {name} — {outlet}")
        print(f"     {host:<28} {resolve(host)}")
        if alternate and alternate != host:
            print(f"     {alternate:<28} {resolve(alternate)}")

    print("\n3) ¿Responden por HTTPS?")
    with Fetcher() as fetcher:
        for name, _outlet, url in fuentes:
            result = fetcher.get(url)
            if result.ok:
                estado = f"OK  HTTP {result.status_code}  {len(result.text):,} bytes"
                if urlparse(result.url).netloc != urlparse(url).netloc:
                    estado += f"  (respondió {urlparse(result.url).netloc})"
            else:
                estado = f"FALLA  {result.error}"
            print(f"   {name:<32} {estado}")

    print("\n4) Navegador headless (para los medios que rechazan al robot)")
    from app.collector.http_client import playwright_available

    activado = settings.enable_headless_browser
    instalado = playwright_available()
    print(f"   ENABLE_HEADLESS_BROWSER (en el .env)  {'sí' if activado else 'no'}")
    print(f"   Chromium instalado en la imagen       {'sí' if instalado else 'no'}")
    if activado and not instalado:
        print()
        print("   ⚠ Está pedido pero no instalado. Falta añadir al archivo .env")
        print("     esta línea, SIN almohadilla delante y en su propio renglón:")
        print()
        print("         INSTALL_PLAYWRIGHT=true")
        print()
        print("     (si solo aparece dentro de un comentario que empieza por «#»,")
        print("      no cuenta: Docker ignora todo lo que va después de la #)")
        print("     Después: docker compose up -d --build")
    elif not activado and not instalado:
        print("   → Ninguna fuente usará navegador. Está bien si ninguna lo pide.")
    elif instalado and not activado:
        print("   → Instalado pero apagado. Pon ENABLE_HEADLESS_BROWSER=true"
              " en el .env para usarlo.")
    else:
        print("   → Listo: las fuentes que lo necesiten lo usarán como respaldo.")

    print("\n" + "-" * 72)
    print("Cómo leer esto:")
    print("  · Si el punto 1 falla       -> el contenedor no tiene red.")
    print("    Prueba: docker compose restart, o reinicia Docker Desktop.")
    print("  · Si falla solo un dominio  -> ese medio no resuelve desde aquí.")
    print("    Si la variante con o sin «www.» sí resuelve, el sistema la")
    print("    usará automáticamente y corregirá la URL guardada.")
    print("  · Si resuelve pero el punto 3 da 403 -> el medio bloquea al bot.")
    print("  · Si el punto 3 va bien y aun así no hay artículos -> es el")
    print("    extractor: usa «python -m app.cli test-source <id>».")
    print("-" * 72 + "\n")
    return 0


def cmd_check_password(_: argparse.Namespace) -> int:
    """Comprueba si una contraseña coincide con la que espera el contenedor.

    No imprime la contraseña nunca. Sirve para distinguir «la estoy tecleando
    mal» de «el contenedor tiene otra distinta de la que puse en el .env».
    """
    import getpass

    from app.security import verify_password

    actual = settings.app_password

    print("\nContraseña que espera el contenedor ahora mismo:")
    print(f"  · longitud: {len(actual)} caracteres")

    avisos = []
    if not actual:
        avisos.append("está VACÍA: falta APP_PASSWORD en el .env")
    if actual == "columnistas":
        avisos.append("es la de por defecto: APP_PASSWORD no llegó al contenedor")
    if "<<<" in actual or ">>>" in actual:
        avisos.append("conserva los signos <<< >>> del archivo de ejemplo")
    if actual != actual.strip():
        avisos.append("empieza o acaba con espacios, seguramente sin querer")
    if len(actual) >= 2 and actual[0] == actual[-1] and actual[0] in "\"'":
        avisos.append("empieza y acaba con comillas: puede que sobren")

    for aviso in avisos:
        print(f"  ⚠ {aviso}")
    if not avisos:
        print("  · sin nada raro a primera vista")

    print("\nEscribe la contraseña que estás tecleando en la app.")
    print("(no se ve al escribir; pulsa Enter al terminar)")
    try:
        candidata = getpass.getpass("  contraseña: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        return 1

    print()
    if verify_password(candidata):
        print("  ✓ COINCIDE. Con esa contraseña deberías poder entrar.")
        print("    Si la app la sigue rechazando, recarga la página en el")
        print("    navegador o el teléfono para descartar una copia vieja.")
        return 0

    print("  ✗ NO COINCIDE con la que tiene el contenedor.")
    print()
    print("  Causas habituales, en orden:")
    print("   1. Cambiaste APP_PASSWORD en el .env pero no reiniciaste:")
    print("        docker compose up -d")
    print("   2. Tu contraseña lleva una almohadilla «#». En un archivo .env")
    print("      todo lo que va después de # se descarta, así que al")
    print("      contenedor le llega solo el trozo de antes.")
    print("   3. Lleva un signo de dólar «$». Docker lo interpreta como el")
    print("      principio del nombre de una variable y lo sustituye.")
    print("   4. La escribiste entre comillas en el .env y quedaron dentro.")
    print()
    print("  Lo más simple: pon en el .env una contraseña de letras, números")
    print("  y guiones, sin comillas ni símbolos, y ejecuta docker compose up -d")
    return 1


def cmd_check_sources(args: argparse.Namespace) -> int:
    """Prueba TODAS las fuentes de una vez, sin guardar nada.

    Con veinte columnistas, ir de uno en uno pulsando «Probar fuente» no es
    práctico. Esto recorre la lista y resume en una tabla qué funciona, qué
    encuentra cada una y por qué fallan las que fallan.
    """
    from app.collector.extractors.registry import get_extractor
    from app.collector.http_client import Fetcher
    from app.collector.runner import cookies_for_outlet
    from app.models import Columnist

    query = select(Columnist).order_by(Columnist.outlet, Columnist.name)
    if not args.all:
        query = query.where(Columnist.active.is_(True))

    with session_scope() as db:
        fuentes = [
            (c.id, c.name, c.outlet, c.source_url, c.feed_url,
             c.extractor_key, c.browser_identity,
             cookies_for_outlet(db, c.outlet))
            for c in db.scalars(query).all()
        ]

    print(f"\nProbando {len(fuentes)} fuentes. "
          f"Hay una espera de cortesía entre peticiones, así que tarda.\n")
    print(f"{'':>4} {'COLUMNISTA':<30} {'MEDIO':<16} {'RESULTADO'}")
    print("-" * 100)

    ok = degradadas = fallidas = 0
    detalles: list[tuple[str, str]] = []

    for cid, name, outlet, source_url, feed_url, extractor_key, browser, cookies in fuentes:
        extractor = get_extractor(source_url, extractor_key)
        try:
            with Fetcher(cookies=cookies, browser_identity=browser) as fetcher:
                if feed_url:
                    from app.collector import rss

                    refs = rss.parse_feed(feed_url, fetcher)
                    origen = "RSS"
                else:
                    refs = extractor.discover(source_url, fetcher)
                    origen = extractor.key
            if refs:
                ok += 1
                estado = f"✓  {len(refs):>2} artículos vía {origen}"
            else:
                degradadas += 1
                estado = f"~  0 artículos vía {origen} (¿no publicó, o extractor?)"
        except Exception as exc:  # noqa: BLE001 - una fuente rota no detiene el repaso
            fallidas += 1
            estado = "✗  falló"
            detalles.append((f"{name} ({outlet})", str(exc)))

        marca = "🌐" if browser else "  "
        print(f"{cid:>4} {name[:29]:<30} {outlet[:15]:<16} {marca} {estado}")

    print("-" * 100)
    print(f"  {ok} bien · {degradadas} sin artículos · {fallidas} con error")
    print("  🌐 = se identifica como navegador\n")

    if detalles:
        print("Errores:\n")
        for quien, error in detalles:
            print(f"  · {quien}")
            print(f"    {error[:300]}\n")

    return 0


def cmd_download_piper(args: argparse.Namespace) -> int:
    voice = args.voice
    if voice not in PIPER_PATHS:
        print(f"Voz desconocida. Disponibles: {', '.join(PIPER_PATHS)}", file=sys.stderr)
        return 1

    target_dir = Path(settings.piper_model_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".onnx", ".onnx.json"):
        url = f"{PIPER_BASE}/{PIPER_PATHS[voice]}{suffix}?download=true"
        target = target_dir / f"{voice}{suffix}"
        print(f"Descargando {target.name}…")
        urllib.request.urlretrieve(url, target)  # noqa: S310
    print(f"✓ Voz {voice} instalada en {target_dir}")
    return 0


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(prog="columnistas", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="crea o actualiza las tablas").set_defaults(func=cmd_migrate)
    sub.add_parser("seed", help="carga los datos iniciales").set_defaults(func=cmd_seed)
    sub.add_parser("status", help="resumen del sistema").set_defaults(func=cmd_status)
    sub.add_parser(
        "doctor", help="diagnostica la red: DNS y acceso a cada fuente"
    ).set_defaults(func=cmd_doctor)
    sub.add_parser(
        "check-password", help="comprueba si una contraseña es la que espera la app"
    ).set_defaults(func=cmd_check_password)

    p_collect = sub.add_parser("collect", help="recolecta artículos ahora")
    p_collect.add_argument("--columnist", type=int, help="solo esta fuente (id)")
    p_collect.add_argument("--no-audio", action="store_true", help="no generar audio")
    p_collect.set_defaults(func=cmd_collect)

    p_audio = sub.add_parser("audio", help="genera audio")
    p_audio.add_argument("--article", type=int)
    p_audio.add_argument("--missing", action="store_true")
    p_audio.add_argument("--force", action="store_true")
    p_audio.add_argument("--voice")
    p_audio.add_argument("--provider")
    p_audio.add_argument("--limit", type=int, default=50)
    p_audio.set_defaults(func=cmd_audio)

    p_check = sub.add_parser(
        "check-sources", help="prueba TODAS las fuentes de una vez")
    p_check.add_argument("--all", action="store_true",
                         help="incluir también las fuentes desactivadas")
    p_check.set_defaults(func=cmd_check_sources)

    p_fix = sub.add_parser(
        "fix-dates", help="corrige fechas mal leídas usando la dirección del artículo")
    p_fix.add_argument("--apply", action="store_true",
                       help="aplicar los cambios (sin esto solo se enseñan)")
    p_fix.set_defaults(func=cmd_fix_dates)

    p_why = sub.add_parser(
        "why", help="explica por qué no llegan artículos de un columnista")
    p_why.add_argument("columnista", help="id o parte del nombre")
    p_why.add_argument("--limit", type=int, default=8,
                       help="cuántos enlaces mirar (por defecto 8)")
    p_why.set_defaults(func=cmd_why)

    p_test = sub.add_parser("test-source", help="prueba una fuente sin guardar nada")
    p_test.add_argument("columnist_id", type=int)
    p_test.set_defaults(func=cmd_test_source)

    p_piper = sub.add_parser("download-piper-voice", help="descarga una voz local")
    p_piper.add_argument("voice")
    p_piper.set_defaults(func=cmd_download_piper)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
