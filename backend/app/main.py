"""Punto de entrada de la API (FastAPI)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api import (
    routes_articles,
    routes_audio,
    routes_auth,
    routes_columnists,
    routes_health,
    routes_settings,
)
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)

app = FastAPI(
    title="Columnistas",
    description="Lectura y escucha diaria de columnas de opinión.",
    version="1.0.0",
    docs_url="/api/docs" if settings.enable_api_docs else None,
    openapi_url="/api/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    # En producción la app web y la API van tras el mismo dominio (nginx),
    # así que esto solo hace falta durante el desarrollo con Vite.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

app.include_router(routes_auth.router)
app.include_router(routes_columnists.router)
app.include_router(routes_articles.router)
app.include_router(routes_audio.router)
app.include_router(routes_settings.router)
app.include_router(routes_health.router)


@app.get("/api")
def root() -> dict:
    return {
        "app": "Columnistas",
        "version": "1.0.0",
        "docs": "/api/docs" if settings.enable_api_docs else "desactivada (ENABLE_API_DOCS)",
    }
