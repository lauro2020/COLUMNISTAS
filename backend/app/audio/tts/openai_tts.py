"""Proveedor de voz: OpenAI (nube).

Voz neuronal muy natural en español. Se factura por caracteres; una columna
de 900 palabras cuesta aproximadamente 0.01–0.02 USD con `gpt-4o-mini-tts`.

Necesita la variable de entorno OPENAI_API_KEY.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import httpx

from app.audio.tts.base import TTSProvider, TTSProviderError, Voice
from app.config import settings

log = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/audio/speech"

VOICES = [
    Voice("onyx", "Onyx — grave, editorial", "es", "Tono serio, ideal para columnas políticas"),
    Voice("nova", "Nova — clara y cercana", "es", "Femenina, ritmo ágil"),
    Voice("alloy", "Alloy — neutra", "es", "Equilibrada, sin acento marcado"),
    Voice("echo", "Echo — pausada", "es", "Masculina, tranquila"),
    Voice("fable", "Fable — narrativa", "es", "Buena para textos largos"),
    Voice("shimmer", "Shimmer — brillante", "es", "Femenina, expresiva"),
    Voice("ash", "Ash — sobria", "es", ""),
    Voice("ballad", "Ballad — cálida", "es", ""),
    Voice("coral", "Coral — expresiva", "es", ""),
    Voice("sage", "Sage — reposada", "es", ""),
    Voice("verse", "Verse — versátil", "es", ""),
]

# Indicación de estilo: mejora bastante la lectura de una columna de opinión
DEFAULT_INSTRUCTIONS = (
    "Lee en español de México, con tono de narrador de periódico serio. "
    "Ritmo pausado, dicción clara, pausas naturales entre párrafos. "
    "No añadas comentarios ni cambies el texto."
)


class OpenAITTS(TTSProvider):
    key = "openai"
    label = "OpenAI (nube)"
    output_format = "mp3"
    max_chars = 3800  # el límite duro de la API es 4096
    supports_parallel = True

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    def voices(self) -> list[Voice]:
        return VOICES

    def synthesize(self, text: str, voice: str, out_path: Path) -> Path:
        if not self.is_configured():
            raise TTSProviderError(
                "Falta OPENAI_API_KEY. Ponla en el archivo .env o cambia la voz "
                "a Piper (local) en Configuración."
            )

        payload = {
            "model": settings.openai_tts_model,
            "input": text[: self.max_chars],
            "voice": voice or settings.openai_tts_voice,
            "response_format": "mp3",
        }
        # `instructions` solo existe en los modelos gpt-4o-*-tts
        if "gpt-4o" in settings.openai_tts_model:
            payload["instructions"] = DEFAULT_INSTRUCTIONS

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""
        for attempt in range(4):
            try:
                with httpx.Client(timeout=180) as client:
                    resp = client.post(API_URL, json=payload, headers=headers)
                if resp.status_code == 200:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(resp.content)
                    return out_path
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    time.sleep(min(2 ** (attempt + 1), 20) + random.uniform(0, 1))
                    continue
                raise TTSProviderError(f"OpenAI respondió {resp.status_code}: {resp.text[:300]}")
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(min(2 ** (attempt + 1), 20) + random.uniform(0, 1))

        raise TTSProviderError(f"OpenAI TTS falló tras varios intentos. {last_error}")
