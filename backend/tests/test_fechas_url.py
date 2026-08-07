"""La fecha que los medios llevan dentro de la dirección del artículo.

Rascar la fecha del HTML es frágil: basta con que en la barra lateral asome
una nota vieja para fechar la columna de hoy hace meses. La dirección
(/2026/08/06/) no tiene ese problema, y estas pruebas la acotan: qué se
acepta, qué no, y cuándo se prefiere a la de la página.
"""

from __future__ import annotations

import datetime as dt

import pytest


def test_la_fecha_de_la_direccion_se_reconoce():
    from app.collector import dates

    fecha = dates.from_url("https://diario.test/opinion/quien/2026/08/06/la-de-hoy")
    assert fecha is not None
    assert (fecha.year, fecha.month, fecha.day) == (2026, 8, 6)


@pytest.mark.parametrize("url", [
    "https://diario.test/opinion/sin-fecha-ninguna",
    "https://diario.test/opinion/2026/13/40/imposible",   # mes y día inventados
    "https://diario.test/opinion/1998/08/06/demasiado-antigua",
    "https://diario.test/opinion/2099/08/06/del-futuro",
])
def test_direcciones_sin_fecha_utilizable(url):
    from app.collector import dates

    assert dates.from_url(url) is None



def test_una_diferencia_pequena_no_toca_la_fecha_de_la_pagina():
    """Zona horaria y «actualizado el…» no son motivo para corregir nada."""
    from app.collector.runner import _mejor_fecha
    from app.collector import dates

    leida = dt.datetime(2026, 8, 6, 23, 30, tzinfo=dates.local_tz())
    url = "https://diario.test/opinion/quien/2026/08/07/la-de-hoy"

    assert _mejor_fecha(leida, url) == leida
