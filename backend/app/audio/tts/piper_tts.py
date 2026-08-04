"""Proveedor de voz: Piper (local, gratis, sin internet).

Alternativa de respaldo cuando no quieras depender de una API de pago o te
quedes sin crédito. Corre dentro del propio contenedor.

Instalación de las voces (una sola vez):
    docker compose exec api python -m app.cli download-piper-voice es_MX-ald-medium
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from app.audio.tts.base import TTSProvider, TTSProviderError, Voice
from app.config import settings

log = logging.getLogger(__name__)

VOICES = [
    Voice("es_MX-ald-medium", "Español de México — Ald (media)", "es-MX", "Voz masculina mexicana"),
    Voice("es_MX-claude-high", "Español de México — Claude (alta)", "es-MX", "Mayor calidad, más lenta"),
    Voice("es_ES-davefx-medium", "Español de España — Davefx", "es-ES", ""),
    Voice("es_ES-sharvard-medium", "Español de España — Sharvard", "es-ES", ""),
    Voice("es_AR-daniela-high", "Español de Argentina — Daniela", "es-AR", ""),
]


class PiperTTS(TTSProvider):
    key = "piper"
    label = "Piper (local, gratis)"
    output_format = "wav"
    max_chars = 6000
    supports_parallel = False  # usa CPU: mejor de uno en uno

    def _model_path(self, voice: str) -> Path:
        return Path(settings.piper_model_dir) / f"{voice}.onnx"

    def is_configured(self) -> bool:
        binary_ok = shutil.which(settings.piper_binary) is not None
        model_ok = self._model_path(settings.piper_voice).exists()
        return binary_ok and model_ok

    def voices(self) -> list[Voice]:
        installed = {p.stem for p in Path(settings.piper_model_dir).glob("*.onnx")} \
            if Path(settings.piper_model_dir).exists() else set()
        result = []
        for voice in VOICES:
            marker = "" if voice.id in installed else " (no instalada)"
            result.append(Voice(voice.id, voice.label + marker, voice.language, voice.description))
        return result

    def synthesize(self, text: str, voice: str, out_path: Path) -> Path:
        voice = voice or settings.piper_voice
        model = self._model_path(voice)
        if shutil.which(settings.piper_binary) is None:
            raise TTSProviderError(
                "El binario de Piper no está instalado en el contenedor. "
                "Usa el proveedor OpenAI o revisa el README, sección «Piper»."
            )
        if not model.exists():
            raise TTSProviderError(
                f"Falta el modelo de voz {voice}. Descárgalo con:\n"
                f"  docker compose exec api python -m app.cli download-piper-voice {voice}"
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [settings.piper_binary, "--model", str(model), "--output_file", str(out_path)],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=600,
            )
        except subprocess.CalledProcessError as exc:
            raise TTSProviderError(
                f"Piper falló: {exc.stderr.decode('utf-8', 'ignore')[:300]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TTSProviderError("Piper tardó demasiado y se canceló") from exc

        return out_path
