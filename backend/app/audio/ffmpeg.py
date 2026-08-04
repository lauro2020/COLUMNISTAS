"""Utilidades de audio basadas en ffmpeg.

ffmpeg viene instalado en la imagen Docker. Se usa para:
  * medir la duración exacta de cada fragmento (para sincronizar texto y audio),
  * convertir WAV (Piper) a MP3,
  * unir todos los fragmentos en un solo archivo.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    pass


def probe_duration(path: Path) -> float:
    """Duración en segundos de un archivo de audio."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(path),
            ],
            check=True, capture_output=True, timeout=60,
        )
        data = json.loads(out.stdout)
        return float(data["format"]["duration"])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        raise FFmpegError(f"No se pudo medir la duración de {path.name}: {exc}") from exc


def to_mp3(source: Path, target: Path, bitrate: str = "64k") -> Path:
    """Convierte cualquier audio a MP3 mono 22 kHz (voz: suena igual y pesa 5x menos)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "22050", "-b:a", bitrate, str(target),
    ])
    return target


def concat(parts: list[Path], target: Path, bitrate: str = "64k") -> Path:
    """Une varios audios en uno solo, re-codificando para que la duración sea exacta."""
    if not parts:
        raise FFmpegError("No hay fragmentos que unir")
    if len(parts) == 1:
        return to_mp3(parts[0], target, bitrate)

    target.parent.mkdir(parents=True, exist_ok=True)
    listing = target.with_suffix(".txt")
    listing.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8"
    )
    try:
        _run([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(listing), "-vn", "-ac", "1", "-ar", "22050",
            "-b:a", bitrate, str(target),
        ])
    finally:
        listing.unlink(missing_ok=True)
    return target


def silence(seconds: float, target: Path) -> Path:
    """Genera un silencio (se intercala entre párrafos)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
        "-t", str(seconds), "-b:a", "64k", str(target),
    ])
    return target


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(
            f"ffmpeg falló: {exc.stderr.decode('utf-8', 'ignore')[:400]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("ffmpeg tardó demasiado") from exc
    except FileNotFoundError as exc:
        raise FFmpegError(
            "ffmpeg no está instalado. En Docker viene incluido; si corres "
            "el backend a mano instálalo con `brew install ffmpeg` o "
            "`apt install ffmpeg`."
        ) from exc
