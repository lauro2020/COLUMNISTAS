"""Registro de extractores.

Descubre automáticamente todas las clases que heredan de `BaseExtractor`
dentro de este paquete. Para añadir un medio nuevo basta con crear un
archivo `.py` aquí con tu clase: el registro lo detecta sin tocar nada más.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from functools import lru_cache

from app.collector.extractors.base import BaseExtractor
from app.collector.extractors.generic import GenericExtractor


@lru_cache(maxsize=1)
def all_extractors() -> list[type[BaseExtractor]]:
    package = importlib.import_module("app.collector.extractors")
    found: list[type[BaseExtractor]] = []

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in {"base", "registry"}:
            continue
        module = importlib.import_module(f"app.collector.extractors.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseExtractor)
                and obj not in (BaseExtractor, GenericExtractor)
                and obj.__module__ == module.__name__
                and obj.domains
            ):
                found.append(obj)

    return sorted(found, key=lambda c: c.key)


def get_extractor(url: str, forced_key: str | None = None) -> BaseExtractor:
    """Devuelve el extractor adecuado para una URL.

    Orden: extractor forzado en la ficha del columnista -> extractor por
    dominio -> extractor genérico de respaldo.
    """
    if forced_key:
        for cls in all_extractors():
            if cls.key == forced_key:
                return cls()
        if forced_key == "generic":
            return GenericExtractor()

    for cls in all_extractors():
        if cls.matches(url):
            return cls()

    return GenericExtractor()


def extractor_keys() -> list[str]:
    return ["generic", *[cls.key for cls in all_extractors()]]
