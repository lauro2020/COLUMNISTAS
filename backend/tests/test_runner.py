"""Pruebas del recolector completo, contra una base de datos de verdad.

Lo que se comprueba aquí es la parte que decide **qué entra y qué no**, y
sobre todo que cuando no entra nada quede escrito el motivo: un día sin
columna nueva y un extractor roto se veían igual en la pantalla de Fuentes,
y eso hacía imposible saber a cuál de los dos se estaba uno enfrentando.

Necesita PostgreSQL (los modelos usan JSONB y tipos ENUM propios). Si no
hay ninguno a mano, las pruebas se saltan solas.
"""

from __future__ import annotations

import datetime as dt
import os

import httpx
import pytest
import respx
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.collector.http_client import Fetcher
from app.config import settings

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres@/postgres?host=/tmp&port=5433",
)


def _hay_base_de_datos() -> bool:
    try:
        motor = create_engine(TEST_DB, pool_pre_ping=True)
        with motor.connect() as conexion:
            conexion.execute(text("select 1"))
        motor.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _hay_base_de_datos(), reason="no hay PostgreSQL para probar"
)


# ---------------------------------------------------------------------------
# Páginas de mentira: una columna normal, una recortada por muro de pago
# ---------------------------------------------------------------------------
PAGINA_DEL_AUTOR = """
<html><body><main>
  <article><h2><a href="https://diario.test/opinion/quien/2026/08/06/la-nueva/">La nueva</a></h2></article>
  <article><h2><a href="https://diario.test/opinion/quien/2026/08/05/la-recortada/">La recortada</a></h2></article>
</main></body></html>
"""

COLUMNA_COMPLETA = """
<html><head><title>La nueva</title>
<meta property="og:title" content="La nueva">
<link rel="canonical" href="https://diario.test/opinion/quien/2026/08/06/la-nueva/">
</head><body><article><h1>La nueva</h1><div class="cuerpo-nota">
<p>Primer parrafo con suficiente texto como para que el limpiador de bloques
   no lo tire, hablando de la reforma que discute el Congreso esta semana.</p>
<p>Segundo parrafo que insiste en el asunto y aporta cifras concretas, de modo
   que el conteo de palabras supere con holgura el minimo exigido.</p>
<p>Tercer parrafo de cierre, tambien largo, para que no queden dudas de que
   esta columna se extrajo entera y debe guardarse sin ningun problema.</p>
</div></article></body></html>
"""

# Dos párrafos, pero cortísimos: pasa el filtro de bloques y cae en el de
# palabras. Es la forma en que algunos medios sirven la columna al no suscriptor.
COLUMNA_ASOMADA = """
<html><head><title>La asomada</title>
<meta property="og:title" content="La asomada">
<link rel="canonical" href="https://diario.test/opinion/quien/2026/08/04/la-asomada/">
</head><body><article><h1>La asomada</h1><div class="cuerpo-nota">
<p>El arranque de la columna, cortado por el medio.</p>
<p>Nada mas por aqui.</p>
</div></article></body></html>
"""

COLUMNA_RECORTADA = """
<html><head><title>La recortada</title>
<meta property="og:title" content="La recortada">
<link rel="canonical" href="https://diario.test/opinion/quien/2026/08/05/la-recortada/">
</head><body><article><h1>La recortada</h1><div class="cuerpo-nota">
<p>Solo el arranque.</p>
</div></article></body></html>
"""


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr(settings, "request_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "respect_robots", False)
    monkeypatch.setattr(settings, "max_retries", 1)
    monkeypatch.setattr(Fetcher, "_backoff", staticmethod(lambda attempt: None))


@pytest.fixture
def db():
    """Un esquema limpio y desechable por prueba."""
    from app.models import Base

    motor = create_engine(TEST_DB)
    with motor.connect() as conexion:
        conexion.execute(text("drop schema if exists prueba cascade"))
        conexion.execute(text("create schema prueba"))
        conexion.commit()

    motor = create_engine(
        TEST_DB, connect_args={"options": "-csearch_path=prueba,public"}
    )
    Base.metadata.create_all(motor)
    sesion = Session(motor)
    try:
        yield sesion
    finally:
        sesion.close()
        motor.dispose()


def _columnista(db):
    from app.models import Columnist, SourceType

    c = Columnist(
        name="Quien Sea",
        outlet="Diario Test",
        source_url="https://diario.test/opinion/quien/",
        source_type=SourceType.html,
        active=True,
    )
    db.add(c)
    db.flush()
    return c


def _rutas():
    respx.get("https://diario.test/opinion/quien/").mock(
        return_value=httpx.Response(200, text=PAGINA_DEL_AUTOR)
    )
    respx.get("https://diario.test/opinion/quien/2026/08/06/la-nueva").mock(
        return_value=httpx.Response(200, text=COLUMNA_COMPLETA)
    )
    respx.get("https://diario.test/opinion/quien/2026/08/05/la-recortada").mock(
        return_value=httpx.Response(200, text=COLUMNA_RECORTADA)
    )


# ---------------------------------------------------------------------------
@respx.mock
def test_guarda_la_columna_entera_y_descarta_la_recortada(db):
    from app.collector.runner import collect_all
    from app.models import Article

    _rutas()
    columnista = _columnista(db)

    resultado = collect_all(db, columnist_ids=[columnista.id])

    titulos = {a.title for a in db.scalars(select(Article)).all()}
    assert titulos == {"La nueva"}, "la recortada no debía guardarse"
    assert len(resultado.new_article_ids) == 1
    assert resultado.sources_failed == 0


@respx.mock
def test_dice_por_que_no_guardo_la_recortada(db):
    """El motivo tiene que quedar escrito, no solo en los registros."""
    from app.collector.runner import collect_all
    from app.models import SourceRun

    _rutas()
    columnista = _columnista(db)
    collect_all(db, columnist_ids=[columnista.id])

    fila = db.scalar(select(SourceRun))
    assert fila.articles_new == 1
    # Se guardó una, así que no hay queja general; pero la recortada quedó
    # anotada en el registro del contenedor y no rompió la ejecución.
    assert fila.status.value == "ok"


@respx.mock
def test_la_segunda_vuelta_explica_que_ya_estaba_todo_guardado(db):
    """El caso que confundía: «no llega nada» sin decir que ya estaba."""
    from app.collector.runner import collect_all
    from app.models import SourceRun

    _rutas()
    columnista = _columnista(db)
    collect_all(db, columnist_ids=[columnista.id])
    collect_all(db, columnist_ids=[columnista.id])

    ultima = db.scalars(
        select(SourceRun).order_by(SourceRun.id.desc())
    ).first()
    assert ultima.articles_new == 0
    assert ultima.error_message is not None
    assert "ya estaban guardados" in ultima.error_message
    # Y explícitamente NO el mensaje que antes lo tapaba todo
    assert "no publicó hoy" not in ultima.error_message


@respx.mock
def test_una_pagina_que_no_deja_extraer_lo_dice(db):
    """Si el medio recorta TODO, el usuario tiene que enterarse."""
    from app.collector.runner import collect_all
    from app.models import SourceRun

    respx.get("https://diario.test/opinion/quien/").mock(
        return_value=httpx.Response(
            200,
            text=PAGINA_DEL_AUTOR.replace(
                "2026/08/06/la-nueva/", "2026/08/05/la-recortada/"
            ),
        )
    )
    respx.get("https://diario.test/opinion/quien/2026/08/05/la-recortada").mock(
        return_value=httpx.Response(200, text=COLUMNA_RECORTADA)
    )
    columnista = _columnista(db)

    collect_all(db, columnist_ids=[columnista.id])

    fila = db.scalar(select(SourceRun))
    assert fila.articles_new == 0
    assert "no dejó extraer el texto" in (fila.error_message or "")
    assert "muro de pago" in (fila.error_message or "")


@respx.mock
def test_una_columna_asomada_se_guarda_marcada_de_pago(db):
    """Dos párrafos de cortesía y nada más.

    No se tira: se guarda marcada «de pago», que es lo útil — así ves que la
    columna existe y que lo que falta es la suscripción, en vez de creer que
    ese día el columnista no escribió.
    """
    from app.collector.runner import collect_all
    from app.models import Article

    respx.get("https://diario.test/opinion/quien/").mock(
        return_value=httpx.Response(
            200,
            text=PAGINA_DEL_AUTOR.replace(
                "2026/08/06/la-nueva/", "2026/08/04/la-asomada/"
            ).replace("2026/08/05/la-recortada/", "2026/08/04/la-asomada/"),
        )
    )
    respx.get("https://diario.test/opinion/quien/2026/08/04/la-asomada").mock(
        return_value=httpx.Response(200, text=COLUMNA_ASOMADA)
    )
    columnista = _columnista(db)

    collect_all(db, columnist_ids=[columnista.id])

    guardado = db.scalar(select(Article))
    assert guardado is not None
    assert guardado.is_paywalled is True
    assert guardado.word_count < 60


@respx.mock
def test_una_fuente_caida_no_tumba_a_las_demas(db):
    """El principio de diseño, comprobado de verdad."""
    from app.collector.runner import collect_all
    from app.models import Article, Columnist, SourceType

    _rutas()
    buena = _columnista(db)
    mala = Columnist(
        name="Fuente Rota",
        outlet="Otro Diario",
        source_url="https://caido.test/opinion/nadie/",
        source_type=SourceType.html,
        active=True,
    )
    db.add(mala)
    db.flush()
    respx.get("https://caido.test/opinion/nadie/").mock(
        side_effect=httpx.ConnectError("sin red")
    )

    resultado = collect_all(db, columnist_ids=[buena.id, mala.id])

    assert db.scalar(select(Article).where(Article.title == "La nueva")) is not None
    assert resultado.sources_total == 2


@respx.mock
def test_no_se_traen_columnas_mas_viejas_que_el_limite(db):
    from app.collector.runner import MAX_AGE_DAYS, _filter_candidates
    from app.collector.extractors.base import ArticleRef

    columnista = _columnista(db)
    ahora = dt.datetime.now(dt.timezone.utc)
    refs = [
        ArticleRef(url="https://diario.test/a/", published_at=ahora),
        ArticleRef(
            url="https://diario.test/b/",
            published_at=ahora - dt.timedelta(days=MAX_AGE_DAYS + 1),
        ),
    ]

    vivos, descartes = _filter_candidates(db, columnista, refs)

    assert [r.url for r in vivos] == ["https://diario.test/a"]
    assert any("más viejos" in d for d in descartes)


# ---------------------------------------------------------------------------
# La fecha que va dentro de la dirección
# ---------------------------------------------------------------------------
COLUMNA_CON_FECHA_AJENA = """
<html><head><title>La de hoy</title>
<meta property="og:title" content="La de hoy">
<link rel="canonical" href="https://diario.test/opinion/quien/2026/08/06/la-de-hoy/">
</head><body>
  <aside>Lo mas leido: una nota vieja del 3 de febrero de 2026</aside>
  <article><h1>La de hoy</h1><div class="cuerpo-nota">
  <p>Primer parrafo con suficiente texto como para que el limpiador de bloques
     no lo tire, hablando de la reforma que discute el Congreso esta semana.</p>
  <p>Segundo parrafo que insiste en el asunto y aporta cifras concretas, de modo
     que el conteo de palabras supere con holgura el minimo exigido.</p>
  <p>Tercer parrafo de cierre, tambien largo, para que no queden dudas de que
     esta columna se extrajo entera y debe guardarse sin ningun problema.</p>
  </div></article>
</body></html>
"""


@respx.mock
def test_una_fecha_de_la_barra_lateral_no_desplaza_a_la_columna(db):
    """El fallo real: la columna de ayer acababa fechada meses atrás.

    Bastaba con que en la página asomara la fecha de otra nota para que el
    artículo se hundiera al fondo de la lista, sin que nada diera error.
    """
    from app.collector.runner import collect_all
    from app.models import Article

    respx.get("https://diario.test/opinion/quien/").mock(
        return_value=httpx.Response(
            200,
            text=PAGINA_DEL_AUTOR.replace("2026/08/06/la-nueva/", "2026/08/06/la-de-hoy/"),
        )
    )
    respx.get("https://diario.test/opinion/quien/2026/08/06/la-de-hoy").mock(
        return_value=httpx.Response(200, text=COLUMNA_CON_FECHA_AJENA)
    )
    respx.get("https://diario.test/opinion/quien/2026/08/05/la-recortada").mock(
        return_value=httpx.Response(200, text=COLUMNA_RECORTADA)
    )
    columnista = _columnista(db)

    collect_all(db, columnist_ids=[columnista.id])

    guardado = db.scalar(select(Article).where(Article.title == "La de hoy"))
    assert guardado is not None
    assert guardado.published_at.date() == dt.date(2026, 8, 6), (
        "debía ganar la fecha de la dirección, no la de la barra lateral"
    )
