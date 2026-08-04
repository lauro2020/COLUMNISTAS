"""Modelo de datos.

Entidades:
  Columnist        -> un columnista y su fuente (RSS o página de autor)
  Article          -> una columna ya normalizada a texto limpio
  Audio            -> el MP3 generado para un artículo
  CollectionRun    -> una ejecución completa de la recolección diaria
  SourceRun        -> resultado de esa ejecución para UNA fuente concreta
  UserPreference   -> preferencias (fila única)
  MediaCredential  -> credenciales/cookies por medio, cifradas
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SourceType(str, enum.Enum):
    rss = "rss"
    html = "html"
    auto = "auto"  # intenta RSS y si no existe cae a HTML


class RunStatus(str, enum.Enum):
    ok = "ok"
    degraded = "degraded"  # respondió pero no se pudo extraer todo
    error = "error"
    skipped = "skipped"


class AudioStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    error = "error"


# Los tipos ENUM de PostgreSQL se declaran UNA sola vez y se reutilizan en
# cada tabla; así SQLAlchemy no intenta crear el mismo tipo dos veces.
source_type_enum = Enum(SourceType, name="source_type", metadata=Base.metadata)
run_status_enum = Enum(RunStatus, name="run_status", metadata=Base.metadata)
audio_status_enum = Enum(AudioStatus, name="audio_status", metadata=Base.metadata)


# ---------------------------------------------------------------------------
# Columnistas
# ---------------------------------------------------------------------------
class Columnist(Base):
    __tablename__ = "columnists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    outlet: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    feed_url: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(
        source_type_enum, default=SourceType.auto, nullable=False
    )
    # Frecuencia esperada de publicación: "diaria", "lunes,miércoles,viernes", "semanal"...
    expected_frequency: Mapped[str] = mapped_column(String(120), default="diaria")
    # Fuerza un extractor concreto; si va vacío se elige por dominio.
    extractor_key: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # Salud de la fuente
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )

    articles: Mapped[list["Article"]] = relationship(
        back_populates="columnist", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("name", "outlet", name="uq_columnist_name_outlet"),
    )


# ---------------------------------------------------------------------------
# Artículos
# ---------------------------------------------------------------------------
class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    columnist_id: Mapped[int] = mapped_column(
        ForeignKey("columnists.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    outlet: Mapped[str | None] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    collected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )

    # Cuerpo normalizado: lista de bloques
    #   [{"type": "p"|"h2"|"quote"|"li", "html": "...", "text": "..."}]
    body: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Mismo cuerpo en texto plano: se usa para TTS, hash y búsqueda.
    plain_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    reading_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_paywalled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extractor_used: Mapped[str | None] = mapped_column(String(80))

    # Estado de lectura
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_listened: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # Punto donde me quedé (se sincroniza entre dispositivos)
    audio_position_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reading_paragraph_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('spanish', coalesce(title, '') || ' ' || coalesce(plain_text, ''))",
            persisted=True,
        ),
    )

    columnist: Mapped[Columnist] = relationship(back_populates="articles")
    audios: Mapped[list["Audio"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_articles_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_articles_columnist_published", "columnist_id", "published_at"),
        UniqueConstraint("columnist_id", "content_hash", name="uq_article_columnist_hash"),
    )


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
class Audio(Base):
    __tablename__ = "audios"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True, nullable=False
    )

    file_path: Mapped[str | None] = mapped_column(Text)
    file_size: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(40))
    voice: Mapped[str | None] = mapped_column(String(80))
    format: Mapped[str] = mapped_column(String(10), default="mp3")

    status: Mapped[AudioStatus] = mapped_column(
        audio_status_enum, default=AudioStatus.pending, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    # Sincronía texto <-> audio:
    #   [{"paragraph_index": 0, "start": 12.4, "end": 31.0}, ...]
    marks: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    generated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="audios")

    __table_args__ = (
        Index("ix_audios_article_status", "article_id", "status"),
    )


# ---------------------------------------------------------------------------
# Ejecuciones de recolección
# ---------------------------------------------------------------------------
class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled | manual
    status: Mapped[RunStatus] = mapped_column(
        run_status_enum, default=RunStatus.ok, nullable=False
    )
    sources_total: Mapped[int] = mapped_column(Integer, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, default=0)

    source_runs: Mapped[list["SourceRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    columnist_id: Mapped[int | None] = mapped_column(
        ForeignKey("columnists.id", ondelete="SET NULL"), index=True
    )
    columnist_name: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[RunStatus] = mapped_column(
        run_status_enum, default=RunStatus.ok, nullable=False
    )
    articles_found: Mapped[int] = mapped_column(Integer, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    extractor_used: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )

    run: Mapped[CollectionRun] = relationship(back_populates="source_runs")


# ---------------------------------------------------------------------------
# Preferencias (fila única, id = 1)
# ---------------------------------------------------------------------------
class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    collect_hour: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    collect_minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="America/Mexico_City")

    tts_provider: Mapped[str] = mapped_column(String(40), default="openai")
    tts_voice: Mapped[str] = mapped_column(String(80), default="onyx")
    auto_generate_audio: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    playback_rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    retention_months: Mapped[int] = mapped_column(Integer, default=12, nullable=False)

    theme: Mapped[str] = mapped_column(String(20), default="system")  # light | dark | system
    font_size: Mapped[int] = mapped_column(Integer, default=18)

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Credenciales por medio (cifradas en reposo)
# ---------------------------------------------------------------------------
class MediaCredential(Base):
    __tablename__ = "media_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    # "cookies" (pegas las cookies del navegador) | "login" (usuario/contraseña)
    kind: Mapped[str] = mapped_column(String(20), default="cookies", nullable=False)
    # Blob cifrado con Fernet a partir de APP_SECRET_KEY
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200))
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )
