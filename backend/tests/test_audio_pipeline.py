"""Pruebas de la canalización de audio.

No se llama a ningún proveedor real ni a ffmpeg: se sustituyen por dobles
de prueba. Lo que se comprueba es la lógica propia:
  * que todos los párrafos acaban sintetizados,
  * que las marcas de sincronía son coherentes y monótonas,
  * que un fallo del proveedor no rompe nada más.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audio import ffmpeg, pipeline, textprep
from app.audio.tts.base import TTSProvider, TTSProviderError


class FakeTTS(TTSProvider):
    """Escribe un archivo falso y recuerda lo que le pidieron leer."""

    key = "fake"
    label = "Falso"
    output_format = "mp3"
    max_chars = 300
    supports_parallel = True

    def __init__(self, fail_on: int | None = None):
        self.calls: list[str] = []
        self.fail_on = fail_on

    def is_configured(self) -> bool:
        return True

    def voices(self):
        return []

    def synthesize(self, text: str, voice: str, out_path: Path) -> Path:
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            raise TTSProviderError("proveedor caído")
        self.calls.append(text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-audio-" + str(len(text)).encode())
        return out_path


@pytest.fixture
def sin_ffmpeg(monkeypatch, tmp_path):
    """Sustituye ffmpeg: la duración es proporcional al tamaño del archivo."""
    monkeypatch.setattr(
        ffmpeg, "probe_duration", lambda path: max(1.0, Path(path).stat().st_size / 10)
    )
    monkeypatch.setattr(
        ffmpeg, "silence",
        lambda seconds, target: (Path(target).write_bytes(b"s" * 4), Path(target))[1],
    )

    def fake_concat(parts, target, bitrate="64k"):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"".join(Path(p).read_bytes() for p in parts))
        return target

    monkeypatch.setattr(ffmpeg, "concat", fake_concat)
    monkeypatch.setattr(ffmpeg, "to_mp3", lambda src, dst, bitrate="64k": Path(src))
    monkeypatch.setattr(pipeline.settings, "audio_dir", str(tmp_path / "audio"))
    return tmp_path


def hacer_articulo(n_parrafos: int = 8) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        title="La columna de prueba",
        author="Autor de Prueba",
        outlet="Diario X",
        published_at=dt.datetime(2025, 3, 12, tzinfo=dt.timezone.utc),
        body=[
            {"type": "p", "text": f"Párrafo {i} con contenido suficiente para leerse en voz alta.",
             "html": ""}
            for i in range(n_parrafos)
        ],
    )


# ---------------------------------------------------------------------------
def test_se_sintetiza_todo_el_articulo(sin_ffmpeg):
    provider = FakeTTS()
    rel_path, duracion, marcas, tamano = pipeline._synthesize(
        hacer_articulo(), provider, "onyx"
    )

    assert provider.calls, "debe haberse llamado al proveedor"
    assert "Por Autor de Prueba." in provider.calls[0], "el audio abre con la introducción"
    assert duracion > 0
    assert tamano > 0
    assert rel_path.endswith(".mp3")
    assert "2025/03" in rel_path


def test_las_marcas_cubren_todos_los_parrafos(sin_ffmpeg):
    articulo = hacer_articulo(10)
    _, _, marcas, _ = pipeline._synthesize(articulo, FakeTTS(), "onyx")

    indices = sorted({m["paragraph_index"] for m in marcas if m["paragraph_index"] >= 0})
    assert indices == list(range(10))


def test_las_marcas_son_crecientes(sin_ffmpeg):
    _, total, marcas, _ = pipeline._synthesize(hacer_articulo(12), FakeTTS(), "onyx")

    inicios = [m["start"] for m in marcas]
    assert inicios == sorted(inicios), "las marcas deben ir hacia adelante"
    for marca in marcas:
        assert marca["end"] >= marca["start"]


def test_articulo_sin_texto_da_error_claro(sin_ffmpeg):
    vacio = hacer_articulo(0)
    with pytest.raises(TTSProviderError, match="no tiene texto"):
        pipeline._synthesize(vacio, FakeTTS(), "onyx")


def test_fallo_del_proveedor_se_propaga_como_error_controlado(sin_ffmpeg):
    with pytest.raises(TTSProviderError, match="proveedor caído"):
        pipeline._synthesize(hacer_articulo(6), FakeTTS(fail_on=2), "onyx")


def test_reparto_de_marcas_dentro_de_un_fragmento():
    chunk = textprep.Chunk(text="a" * 300, paragraph_indices=[3, 4, 5])
    marcas = pipeline._chunk_marks(chunk, start=10.0, duration=30.0)

    assert [m["paragraph_index"] for m in marcas] == [3, 4, 5]
    assert marcas[0]["start"] == 10.0
    assert marcas[-1]["end"] == pytest.approx(40.0, abs=0.05)


def test_la_introduccion_se_marca_como_indice_menos_uno():
    chunk = textprep.Chunk(text="Introducción.", paragraph_indices=[-1])
    marcas = pipeline._chunk_marks(chunk, start=0.0, duration=5.0)
    assert marcas == [{"paragraph_index": -1, "start": 0.0, "end": 5.0}]
