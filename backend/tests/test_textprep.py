"""Pruebas de la preparación del texto para el motor de voz."""

from __future__ import annotations

import datetime as dt

from app.audio import textprep


def test_porcentajes():
    assert "treinta y cinco por ciento" in textprep.normalize_for_speech("el 35% de los votos")


def test_cifras_con_separador_de_miles():
    salida = textprep.normalize_for_speech("costó 1,200 pesos")
    assert "mil doscientos" in salida
    assert "1,200" not in salida


def test_decimales():
    assert "tres punto cinco" in textprep.normalize_for_speech("creció 3.5 en el trimestre")


def test_fechas_numericas():
    salida = textprep.normalize_for_speech("el 12/03/2025 ocurrió todo")
    assert "de marzo de" in salida
    assert "12/03/2025" not in salida


def test_abreviaturas():
    salida = textprep.normalize_for_speech("El Dr. Pérez citó el art. 4o. y etc.")
    assert "doctor" in salida
    assert "artículo" in salida
    assert "etcétera" in salida


def test_siglas_conocidas():
    salida = textprep.normalize_for_speech("La SHCP y el PIB")
    assert "Secretaría de Hacienda" in salida
    assert "producto interno bruto" in salida


def test_siglas_sin_vocales_se_deletrean():
    assert "P-J-F" in textprep.normalize_for_speech("el PJF resolvió")


def test_montos_abreviados():
    salida = textprep.normalize_for_speech("un recorte de 500 mdp")
    assert "millones de pesos" in salida


def test_introduccion_hablada():
    intro = textprep.build_intro(
        "La ciudad de noche",
        "Héctor de Mauleón",
        "El Universal",
        dt.datetime(2025, 3, 12, tzinfo=dt.timezone.utc),
    )
    assert "La ciudad de noche." in intro
    assert "Por Héctor de Mauleón." in intro
    assert "El Universal." in intro
    assert "de marzo de" in intro


# ---------------------------------------------------------------------------
# Troceado
# ---------------------------------------------------------------------------
def test_los_fragmentos_respetan_el_limite():
    parrafos = [f"Párrafo número {i} con texto suficiente para ocupar sitio." * 3 for i in range(20)]
    chunks = textprep.build_chunks(parrafos, intro="Introducción.", max_chars=400)

    assert all(len(c.text) <= 400 for c in chunks)
    assert chunks[0].paragraph_indices == [-1], "el primer fragmento es la introducción"


def test_no_se_pierde_ningun_parrafo():
    parrafos = [f"Este es el párrafo {i}." for i in range(30)]
    chunks = textprep.build_chunks(parrafos, max_chars=120)

    cubiertos = sorted({i for c in chunks for i in c.paragraph_indices if i >= 0})
    assert cubiertos == list(range(30))


def test_parrafo_gigante_se_parte_por_frases():
    gigante = " ".join(f"Frase número {i} del párrafo." for i in range(200))
    chunks = textprep.build_chunks([gigante], max_chars=300)

    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    assert all(c.paragraph_indices == [0] for c in chunks)


def test_parrafos_vacios_se_ignoran():
    chunks = textprep.build_chunks(["", "   ", "Texto real."], max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].paragraph_indices == [2]
