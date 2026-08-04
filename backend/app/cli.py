"""Línea de comandos.

Cada componente se puede ejecutar y probar por separado:

    python -m app.cli migrate                 # crea/actualiza las tablas
    python -m app.cli seed                    # carga los columnistas iniciales
    python -m app.cli collect                 # recolecta ahora mismo
    python -m app.cli collect --columnist 2   # solo una fuente
    python -m app.cli audio --article 12      # genera el audio de un artículo
    python -m app.cli audio --missing         # genera todos los que falten
    python -m app.cli status                  # resumen del sistema
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
        with Fetcher(cookies=cookies) as fetcher:
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
