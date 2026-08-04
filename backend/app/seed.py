"""Datos semilla: los tres columnistas iniciales y las preferencias.

Es idempotente: se puede ejecutar cuantas veces se quiera, no duplica nada.
La lista vive aquí solo para arrancar el proyecto en limpio; a partir de ese
momento se administra desde la pantalla de Configuración de la app.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Columnist, SourceType, UserPreference

log = logging.getLogger(__name__)

SEED_COLUMNISTS: list[dict] = [
    {
        "name": "Raymundo Riva Palacio",
        "outlet": "El Financiero",
        "source_url": "https://www.elfinanciero.com.mx/opinion/raymundo-riva-palacio/",
        "source_type": SourceType.auto,
        "expected_frequency": "lunes a viernes",
        "extractor_key": "elfinanciero",
        "browser_identity": False,
        "notes": "Estrictamente Personal. Contenido mixto: algunas columnas requieren suscripción.",
    },
    {
        "name": "Héctor de Mauleón",
        "outlet": "El Universal",
        "source_url": "https://www.eluniversal.com.mx/autores/hector-de-mauleon/",
        "source_type": SourceType.auto,
        "expected_frequency": "lunes a viernes",
        "extractor_key": "eluniversal",
        "notes": "En Tercera Persona. Normalmente de acceso abierto.",
    },
    {
        "name": "Jesús Silva-Herzog Márquez",
        "outlet": "Reforma",
        "source_url": "https://www.reforma.com/jesus-silva-herzog-marquez/",
        "source_type": SourceType.html,
        "expected_frequency": "lunes",
        "extractor_key": "reforma",
        "notes": (
            "Requiere suscripción. Guarda las cookies de tu sesión de Reforma "
            "en Configuración › Credenciales para obtener la columna completa."
        ),
    },
]


def seed_columnists(db: Session) -> int:
    created = 0
    for entry in SEED_COLUMNISTS:
        exists = db.scalar(
            select(Columnist)
            .where(Columnist.name == entry["name"])
            .where(Columnist.outlet == entry["outlet"])
        )
        if exists:
            continue
        db.add(Columnist(**entry))
        created += 1
    return created


def seed_preferences(db: Session) -> bool:
    if db.get(UserPreference, 1) is not None:
        return False
    db.add(
        UserPreference(
            id=1,
            collect_hour=settings.collect_hour,
            collect_minute=settings.collect_minute,
            timezone=settings.timezone,
            tts_provider=settings.tts_provider,
            tts_voice=(
                settings.openai_tts_voice
                if settings.tts_provider == "openai"
                else settings.piper_voice
            ),
            retention_months=settings.retention_months,
        )
    )
    return True


def run(db: Session) -> dict:
    created = seed_columnists(db)
    prefs = seed_preferences(db)
    db.commit()
    log.info("Semilla aplicada: %s columnistas nuevos, preferencias=%s", created, prefs)
    return {"columnists_created": created, "preferences_created": prefs}
