"""Datos semilla: los columnistas iniciales y las preferencias.

Es idempotente: se ejecuta en cada arranque y solo añade lo que falte, sin
duplicar ni pisar lo que hayas cambiado desde la app. Si borras un columnista
de esta lista desde la interfaz, **volverá a aparecer** en el siguiente
arranque; para quitarlo del todo, bórralo también de aquí, o simplemente
desactívalo (la casilla «activa») y dejará de recolectarse.

A partir del primer arranque todo se administra desde
Ajustes › Columnistas, sin tocar este archivo.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Columnist, SourceType, UserPreference

log = logging.getLogger(__name__)


def _c(
    name: str,
    outlet: str,
    source_url: str,
    frequency: str,
    *,
    extractor: str | None = None,
    source_type: SourceType = SourceType.auto,
    browser_identity: bool = False,
    active: bool = True,
    notes: str | None = None,
) -> dict:
    return {
        "name": name,
        "outlet": outlet,
        "source_url": source_url,
        "expected_frequency": frequency,
        "extractor_key": extractor,
        "source_type": source_type,
        "browser_identity": browser_identity,
        "active": active,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Notas sobre las banderas de esta lista
#
#   extractor="elfinanciero" / "eluniversal" / "reforma"
#       Medios con extractor propio, más preciso que el genérico.
#
#   browser_identity=True
#       Milenio devuelve 403 a cualquier cliente que no sea un navegador,
#       comprobado en la práctica. Los demás medios se dejan con la
#       identificación propia de la aplicación.
#
#   Sin extractor indicado -> se usa el genérico, que funciona razonablemente
#   bien en casi cualquier periódico. Si en alguno el resultado no convence,
#   escribir un módulo propio son ~30 líneas (ver docs/anadir-columnista.md).
# ---------------------------------------------------------------------------
SEED_COLUMNISTS: list[dict] = [
    # --- El Financiero -----------------------------------------------------
    _c("Raymundo Riva Palacio", "El Financiero",
       "https://www.elfinanciero.com.mx/opinion/raymundo-riva-palacio/",
       "lunes a viernes", extractor="elfinanciero",
       notes="Estrictamente Personal. Contenido mixto: algunas columnas requieren suscripción."),
    _c("Enrique Krauze", "El Financiero",
       "https://www.elfinanciero.com.mx/opinion/enrique-krauze1/",
       "irregular, mensual", extractor="elfinanciero",
       notes="Antes en Reforma y El País."),
    _c("Macario Schettino", "El Financiero",
       "https://www.elfinanciero.com.mx/opinion/macario-schettino/",
       "lunes a viernes", extractor="elfinanciero",
       notes="Fuera de la Caja."),
    _c("Antonio Navalón", "El Financiero",
       "https://www.elfinanciero.com.mx/opinion/antonio-navalon/",
       "semanal", extractor="elfinanciero",
       notes="Año Cero. También participa en Código Magenta (#AlPunto)."),

    # --- El Universal ------------------------------------------------------
    _c("Héctor de Mauleón", "El Universal",
       "https://www.eluniversal.com.mx/autores/hector-de-mauleon/",
       "lunes a viernes", extractor="eluniversal",
       notes="En Tercera Persona. Normalmente de acceso abierto."),
    _c("Carlos Loret de Mola", "El Universal",
       "https://www.eluniversal.com.mx/autores/carlos-loret-de-mola/",
       "lunes a viernes", extractor="eluniversal",
       notes="Historias de Reportero."),
    _c("Jorge G. Castañeda", "El Universal",
       "https://www.eluniversal.com.mx/opinion/jorge-castaneda/",
       "semanal", extractor="eluniversal",
       notes="Dejó El Financiero: ahora publica en El Universal."),

    # --- Reforma (requiere suscripción) ------------------------------------
    _c("Jesús Silva-Herzog Márquez", "Reforma",
       "https://www.reforma.com/jesus-silva-herzog-marquez/",
       "lunes", extractor="reforma", source_type=SourceType.html,
       notes="Requiere suscripción: guarda las cookies en Ajustes › Credenciales."),
    _c("Denise Dresser", "Reforma",
       "https://www.reforma.com/denise-dresser/",
       "lunes", extractor="reforma", source_type=SourceType.html,
       notes="Columna política semanal. Requiere suscripción."),
    _c("Carlos Elizondo Mayer-Serra", "Reforma",
       "https://www.reforma.com/carlos-elizondo-mayer-serra/",
       "domingos", extractor="reforma", source_type=SourceType.html,
       notes="Página editorial. Requiere suscripción."),
    _c("Sergio Sarmiento", "Reforma",
       "https://www.reforma.com/sergio-sarmiento/",
       "lunes a viernes", extractor="reforma", source_type=SourceType.html,
       notes="Jaque Mate. Sindicada en más de 20 diarios. Requiere suscripción."),

    # --- Milenio (rechaza al robot: necesita identidad de navegador) -------
    _c("Héctor Aguilar Camín", "Milenio",
       "https://www.milenio.com/opinion/hector-aguilar-camin",
       "semanal", browser_identity=True,
       notes="Milenio devuelve 403 al robot; puede requerir también el navegador headless."),
    _c("Joaquín López-Dóriga", "Milenio",
       "https://www.milenio.com/opinion/joaquin-lopezdoriga",
       "martes a viernes", browser_identity=True,
       notes="En privado."),
    _c("Francisco Abundis", "Milenio",
       "https://www.milenio.com/opinion/francisco-abundis",
       "semanal", browser_identity=True,
       notes="Columna de Parametría (encuestas). Día sin verificar."),

    # --- Excélsior ---------------------------------------------------------
    _c("Jorge Fernández Menéndez", "Excélsior",
       "https://www.excelsior.com.mx/opinion/jorge-fernandez-menendez",
       "lunes a viernes", notes="Razones."),
    _c("Leo Zuckermann", "Excélsior",
       "https://www.excelsior.com.mx/opinion/leo-zuckermann",
       "lunes a viernes", notes="Juegos de poder."),

    # --- Otros medios ------------------------------------------------------
    _c("Javier Solórzano", "La Razón",
       "https://www.razon.com.mx/autor/javier-solorzano-zinser/",
       "lunes a viernes",
       notes=(
           "De memoria. OJO: esta URL redirige a la portada de La Razón, así que "
           "la página de autor cambió de dirección. Abre cualquier columna suya "
           "y pulsa sobre su NOMBRE: ahí está la dirección buena. No pongas aquí "
           "la de una columna concreta; la app la rechaza a propósito."
       )),
    _c("María Amparo Casar", "UnoTV",
       "https://www.unotv.com/opinion/maria-amparo-casar/",
       "sin verificar",
       notes="Dejó Excélsior tras 11 años. Colabora en UnoTV y medios de radio."),
    _c("Ramón Alberto Garza", "Código Magenta",
       "https://www.codigomagenta.com.mx/seccion/que-alguien-me-explique/",
       "varias veces por semana", notes="¡Que alguien me explique!"),

    # --- Pendientes de completar (llegan desactivados) ----------------------
    _c("Denise Dresser", "Proceso",
       "https://www.proceso.com.mx/",
       "semanal", active=False,
       notes=(
           "DESACTIVADO: falta la URL de su página de autor en Proceso. "
           "Búscala en el sitio, pégala en «URL de su página de autor» y "
           "activa la casilla «activa»."
       )),
    _c("Eduardo Guerrero Gutiérrez", "Nexos",
       "https://www.nexos.com.mx/",
       "sin verificar", active=False,
       notes=(
           "DESACTIVADO: analista de seguridad, publica en Nexos y en "
           "colaboraciones sueltas, sin página de autor confirmada. Busca su "
           "página en nexos.com.mx, pega la URL y activa la casilla «activa»."
       )),
]


#: Columnistas que se cambiaron de medio.
#:
#: La semilla identifica a cada uno por (nombre, medio), así que al cambiarle
#: el medio crearía una ficha nueva y dejaría la vieja al lado, fallando para
#: siempre. Aquí se traslada la ficha existente: conserva su id y con él todo
#: su histórico, que sigue siendo suyo aunque lo publicara en otro periódico.
TRASLADOS = [
    {
        "name": "Jorge G. Castañeda",
        "desde": "El Financiero",
        "hasta": "El Universal",
        "source_url": "https://www.eluniversal.com.mx/opinion/jorge-castaneda/",
        "extractor_key": "eluniversal",
        "notes": "Dejó El Financiero: ahora publica en El Universal.",
    },
]


def apply_moves(db: Session) -> int:
    movidos = 0
    for traslado in TRASLADOS:
        antigua = db.scalar(
            select(Columnist)
            .where(Columnist.name == traslado["name"])
            .where(Columnist.outlet == traslado["desde"])
        )
        if antigua is None:
            continue  # ya se trasladó, o esta instalación nunca lo tuvo

        ya_existe = db.scalar(
            select(Columnist)
            .where(Columnist.name == traslado["name"])
            .where(Columnist.outlet == traslado["hasta"])
        )
        if ya_existe is not None:
            # Alguien lo dio de alta a mano en el medio nuevo. No se toca nada:
            # borrar la ficha vieja se llevaría por delante su histórico.
            log.warning(
                "%s ya existe en %s; la ficha de %s se queda como está",
                traslado["name"], traslado["hasta"], traslado["desde"],
            )
            continue

        antigua.outlet = traslado["hasta"]
        antigua.source_url = traslado["source_url"]
        antigua.extractor_key = traslado["extractor_key"]
        antigua.notes = traslado["notes"]
        # La fuente es otra: lo que se sabía de la anterior ya no vale
        antigua.feed_url = None
        antigua.consecutive_failures = 0
        antigua.last_error = None
        antigua.active = True
        movidos += 1
        log.info("%s trasladado de %s a %s",
                 traslado["name"], traslado["desde"], traslado["hasta"])
    return movidos


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
    # Los traslados van primero: así, cuando la semilla busque al columnista
    # en su medio nuevo, ya lo encuentra y no crea un duplicado.
    moved = apply_moves(db)
    created = seed_columnists(db)
    prefs = seed_preferences(db)
    db.commit()
    log.info("Semilla aplicada: %s columnistas nuevos, %s trasladados, preferencias=%s",
             created, moved, prefs)
    return {
        "columnists_created": created,
        "columnists_moved": moved,
        "preferences_created": prefs,
    }
