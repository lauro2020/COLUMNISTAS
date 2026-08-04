"""Formas de entrada y salida de la API (Pydantic)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models import AudioStatus, RunStatus, SourceType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    token: str
    expires_days: int


# ---------------------------------------------------------------------------
# Columnistas
# ---------------------------------------------------------------------------
class ColumnistBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    outlet: str = Field(min_length=2, max_length=200)
    source_url: str = Field(min_length=8)
    feed_url: str | None = None
    source_type: SourceType = SourceType.auto
    expected_frequency: str = "diaria"
    extractor_key: str | None = None
    active: bool = True
    notes: str | None = None


class ColumnistCreate(ColumnistBase):
    pass


class ColumnistUpdate(BaseModel):
    name: str | None = None
    outlet: str | None = None
    source_url: str | None = None
    feed_url: str | None = None
    source_type: SourceType | None = None
    expected_frequency: str | None = None
    extractor_key: str | None = None
    active: bool | None = None
    notes: str | None = None


class ColumnistOut(ORMModel, ColumnistBase):
    id: int
    consecutive_failures: int
    last_success_at: dt.datetime | None
    last_error: str | None
    created_at: dt.datetime
    article_count: int = 0
    unread_count: int = 0


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
class AudioOut(ORMModel):
    id: int
    status: AudioStatus
    duration_seconds: float | None
    voice: str | None
    provider: str | None
    generated_at: dt.datetime | None
    error_message: str | None
    marks: list[dict] = []
    url: str | None = None


# ---------------------------------------------------------------------------
# Artículos
# ---------------------------------------------------------------------------
class ArticleListItem(ORMModel):
    id: int
    columnist_id: int
    title: str
    author: str | None
    outlet: str | None
    canonical_url: str
    published_at: dt.datetime | None
    summary: str | None
    reading_minutes: int
    word_count: int
    is_paywalled: bool
    is_read: bool
    is_listened: bool
    is_archived: bool
    is_favorite: bool
    audio_position_seconds: float
    audio_id: int | None = None
    audio_status: AudioStatus | None = None
    audio_duration: float | None = None


class ArticleDetail(ArticleListItem):
    body: list[dict]
    plain_text: str
    original_url: str | None
    extractor_used: str | None
    reading_paragraph_index: int
    audio: AudioOut | None = None


class ArticleStateUpdate(BaseModel):
    is_read: bool | None = None
    is_listened: bool | None = None
    is_archived: bool | None = None
    is_favorite: bool | None = None


class ProgressUpdate(BaseModel):
    audio_position_seconds: float | None = None
    reading_paragraph_index: int | None = None
    mark_listened: bool = False


class InboxGroup(BaseModel):
    columnist_id: int
    columnist_name: str
    outlet: str
    articles: list[ArticleListItem]


class InboxResponse(BaseModel):
    date: dt.date
    total: int
    unread: int
    groups: list[InboxGroup]
    last_run_at: dt.datetime | None = None


# ---------------------------------------------------------------------------
# Preferencias
# ---------------------------------------------------------------------------
class PreferencesOut(ORMModel):
    collect_hour: int
    collect_minute: int
    timezone: str
    tts_provider: str
    tts_voice: str
    auto_generate_audio: bool
    playback_rate: float
    retention_months: int
    theme: str
    font_size: int


class PreferencesUpdate(BaseModel):
    collect_hour: int | None = Field(default=None, ge=0, le=23)
    collect_minute: int | None = Field(default=None, ge=0, le=59)
    timezone: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    auto_generate_audio: bool | None = None
    playback_rate: float | None = Field(default=None, ge=0.5, le=3.0)
    retention_months: int | None = Field(default=None, ge=0, le=120)
    theme: str | None = None
    font_size: int | None = Field(default=None, ge=12, le=32)


# ---------------------------------------------------------------------------
# Credenciales
# ---------------------------------------------------------------------------
class CredentialIn(BaseModel):
    outlet: str
    kind: str = "cookies"
    label: str | None = None
    #: para kind="cookies": la cadena que copias del navegador
    #: (formato "nombre=valor; otro=valor")
    cookies_raw: str | None = None
    username: str | None = None
    password: str | None = None


class CredentialOut(BaseModel):
    id: int
    outlet: str
    kind: str
    label: str | None
    has_secret: bool
    cookie_names: list[str] = []
    updated_at: dt.datetime
    last_used_at: dt.datetime | None


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------
class SourceRunOut(ORMModel):
    id: int
    columnist_id: int | None
    columnist_name: str | None
    status: RunStatus
    articles_found: int
    articles_new: int
    duration_ms: int
    error_message: str | None
    created_at: dt.datetime


class RunOut(ORMModel):
    id: int
    started_at: dt.datetime
    finished_at: dt.datetime | None
    trigger: str
    status: RunStatus
    sources_total: int
    sources_failed: int
    articles_new: int
    source_runs: list[SourceRunOut] = []


class SourceHealth(BaseModel):
    columnist_id: int
    name: str
    outlet: str
    active: bool
    status: str  # sana | degradada | caida | sin-datos
    consecutive_failures: int
    last_success_at: dt.datetime | None
    last_error: str | None
    last_days: list[dict] = []
