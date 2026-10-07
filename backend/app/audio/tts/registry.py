"""Registro de proveedores de texto a voz."""

from __future__ import annotations

from app.audio.tts.base import TTSProvider
from app.audio.tts.openai_tts import OpenAITTS
from app.audio.tts.piper_tts import PiperTTS
from app.config import settings

PROVIDERS: dict[str, type[TTSProvider]] = {
    OpenAITTS.key: OpenAITTS,
    PiperTTS.key: PiperTTS,
}


def get_provider(key: str | None = None) -> TTSProvider:
    chosen = (key or settings.tts_provider or "openai").lower()
    provider_cls = PROVIDERS.get(chosen, OpenAITTS)
    return provider_cls()


def describe_providers() -> list[dict]:
    """Para la pantalla de Configuración."""
    result = []
    for key, cls in PROVIDERS.items():
        provider = cls()
        result.append({
            "key": key,
            "label": provider.label,
            "configured": provider.is_configured(),
            "voices": [
                {"id": v.id, "label": v.label, "language": v.language,
                 "description": v.description}
                for v in provider.voices()
            ],
        })
    return result
