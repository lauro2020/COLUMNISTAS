"""Pruebas de la pantalla de inicio: un columnista por fila."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.api.common import overview_sort_key, recent_cutoff

MX = ZoneInfo("America/Mexico_City")
HOY = dt.date(2026, 8, 6)


def publicado(dias_atras: int, hora: int = 7) -> dt.datetime:
    return dt.datetime.combine(
        HOY - dt.timedelta(days=dias_atras), dt.time(hora), tzinfo=MX
    )


# ---------------------------------------------------------------------------
# La regla: solo se muestra el último artículo si es de los últimos 15 días
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dias_atras,es_reciente", [
    (0, True),    # hoy
    (1, True),    # ayer
    (14, True),
    (15, True),   # el límite entra: son 15 días naturales
    (16, False),  # un día más allá, ya no
    (30, False),
    (365, False),
])
def test_ventana_de_quince_dias(dias_atras, es_reciente):
    corte = recent_cutoff(HOY, 15, MX)
    assert (publicado(dias_atras) >= corte) is es_reciente


def test_una_columna_de_madrugada_del_dia_limite_sigue_contando():
    """El corte es a las 00:00 de ese día, no a la hora actual."""
    corte = recent_cutoff(HOY, 15, MX)
    assert publicado(15, hora=0) >= corte
    assert publicado(15, hora=23) >= corte


def test_la_ventana_es_configurable():
    assert publicado(20) >= recent_cutoff(HOY, 30, MX)
    assert not (publicado(20) >= recent_cutoff(HOY, 7, MX))


# ---------------------------------------------------------------------------
# El orden: primero quien publicó hoy
# ---------------------------------------------------------------------------
def test_orden_de_la_pantalla_de_inicio():
    filas = [
        ("Zulema (calló hace un mes)", False, 30),
        ("Ana (hoy)", True, 0),
        ("Beto (nunca publicó)", False, None),
        ("Carlos (anteayer)", False, 2),
        ("Berta (hoy)", True, 0),
    ]
    ordenadas = sorted(filas, key=lambda f: overview_sort_key(f[1], f[2], f[0]))

    assert [f[0] for f in ordenadas] == [
        "Ana (hoy)",
        "Berta (hoy)",
        "Carlos (anteayer)",
        "Zulema (calló hace un mes)",
        "Beto (nunca publicó)",
    ]


def test_entre_los_de_hoy_manda_el_orden_alfabetico():
    filas = [("Zoe", True, 0), ("Alba", True, 0)]
    ordenadas = sorted(filas, key=lambda f: overview_sort_key(f[1], f[2], f[0]))
    assert [f[0] for f in ordenadas] == ["Alba", "Zoe"]


def test_quien_nunca_publico_va_al_final():
    filas = [("Sin nada", False, None), ("Hace un año", False, 400)]
    ordenadas = sorted(filas, key=lambda f: overview_sort_key(f[1], f[2], f[0]))
    assert ordenadas[-1][0] == "Sin nada"
