"""Configuración global de la aplicación.

Todo lo sensible se lee de variables de entorno (ver `.env.example`).
Nada de esto vive escrito en el código.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Seguridad ---
    app_secret_key: str = "dev-secret-key-cambiala"
    app_password: str = "columnistas"
    auth_token_days: int = 90
    #: publicar /api/docs. Apagado por defecto: si expones la app a internet,
    #: no hay razón para enseñar el mapa de la API a quien pase por ahí.
    enable_api_docs: bool = False
    #: intentos fallidos de contraseña seguidos antes de bloquear un rato
    login_max_attempts: int = 10
    login_lockout_minutes: int = 15

    # --- Base de datos / cola ---
    database_url: str = "postgresql+psycopg://columnistas:columnistas@db:5432/columnistas"
    redis_url: str = "redis://redis:6379/0"

    # --- TTS ---
    tts_provider: str = "openai"
    openai_api_key: str = ""
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "onyx"
    piper_model_dir: str = "/data/piper"
    piper_voice: str = "es_MX-ald-medium"
    piper_binary: str = "piper"

    # --- Recolección ---
    collect_hour: int = 6
    collect_minute: int = 0
    timezone: str = "America/Mexico_City"
    user_agent: str = (
        "ColumnistasBot/1.0 (lector personal; "
        "+https://github.com/lauro2020/columnistas)"
    )
    request_delay_seconds: float = 3.0
    request_timeout_seconds: int = 30
    max_retries: int = 3
    respect_robots: bool = True
    enable_headless_browser: bool = False

    # --- Almacenamiento ---
    audio_dir: str = "/data/audio"
    retention_months: int = 12

    # --- Avisos ---
    notify_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # --- Varios ---
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
