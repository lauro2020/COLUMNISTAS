"""Interfaz común de los proveedores de texto a voz.

Cambiar de proveedor no debe obligar a reescribir la aplicación: todo el
resto del sistema habla solo con esta interfaz.

Para añadir un proveedor nuevo:
  1. crea `app/audio/tts/mi_proveedor.py` con una clase que herede de TTSProvider
  2. regístrala en `app/audio/tts/registry.py`
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Voice:
    id: str
    label: str
    language: str = "es"
    description: str = ""


class TTSProviderError(RuntimeError):
    pass


class TTSProvider:
    key: str = "base"
    label: str = "Proveedor"
    #: formato del archivo que produce ("mp3" o "wav")
    output_format: str = "mp3"
    #: máximo de caracteres por petición
    max_chars: int = 3500
    #: si soporta varias peticiones a la vez
    supports_parallel: bool = True

    def is_configured(self) -> bool:
        """¿Tiene todo lo necesario (clave, binario, modelo) para funcionar?"""
        raise NotImplementedError

    def voices(self) -> list[Voice]:
        raise NotImplementedError

    def synthesize(self, text: str, voice: str, out_path: Path) -> Path:
        """Escribe el audio de `text` en `out_path` y devuelve la ruta."""
        raise NotImplementedError
