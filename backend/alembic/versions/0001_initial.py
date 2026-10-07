"""Esquema inicial.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

source_type = postgresql.ENUM("rss", "html", "auto", name="source_type", create_type=False)
run_status = postgresql.ENUM("ok", "degraded", "error", "skipped", name="run_status", create_type=False)
audio_status = postgresql.ENUM("pending", "processing", "ready", "error", name="audio_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    source_type.create(bind, checkfirst=True)
    run_status.create(bind, checkfirst=True)
    audio_status.create(bind, checkfirst=True)

    # -- columnistas --------------------------------------------------------
    op.create_table(
        "columnists",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("outlet", sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("feed_url", sa.Text),
        sa.Column("source_type", source_type, nullable=False, server_default="auto"),
        sa.Column("expected_frequency", sa.String(120), server_default="diaria"),
        sa.Column("extractor_key", sa.String(80)),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "outlet", name="uq_columnist_name_outlet"),
    )

    # -- artículos ----------------------------------------------------------
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "columnist_id",
            sa.Integer,
            sa.ForeignKey("columnists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("author", sa.String(200)),
        sa.Column("outlet", sa.String(200)),
        sa.Column("canonical_url", sa.Text, nullable=False, unique=True),
        sa.Column("original_url", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("body", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("plain_text", sa.Text, nullable=False, server_default=""),
        sa.Column("summary", sa.Text),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("word_count", sa.Integer, server_default="0"),
        sa.Column("reading_minutes", sa.Integer, server_default="0"),
        sa.Column("is_paywalled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extractor_used", sa.String(80)),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_listened", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_favorite", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("audio_position_seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("reading_paragraph_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_updated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR,
            sa.Computed(
                "to_tsvector('spanish', coalesce(title, '') || ' ' || coalesce(plain_text, ''))",
                persisted=True,
            ),
        ),
        sa.UniqueConstraint("columnist_id", "content_hash", name="uq_article_columnist_hash"),
    )
    op.create_index("ix_articles_columnist_id", "articles", ["columnist_id"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_index("ix_articles_collected_at", "articles", ["collected_at"])
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])
    op.create_index("ix_articles_is_read", "articles", ["is_read"])
    op.create_index("ix_articles_is_archived", "articles", ["is_archived"])
    op.create_index("ix_articles_is_favorite", "articles", ["is_favorite"])
    op.create_index(
        "ix_articles_columnist_published", "articles", ["columnist_id", "published_at"]
    )
    op.create_index(
        "ix_articles_search_vector", "articles", ["search_vector"], postgresql_using="gin"
    )

    # -- audios -------------------------------------------------------------
    op.create_table(
        "audios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text),
        sa.Column("file_size", sa.Integer),
        sa.Column("duration_seconds", sa.Float),
        sa.Column("provider", sa.String(40)),
        sa.Column("voice", sa.String(80)),
        sa.Column("format", sa.String(10), server_default="mp3"),
        sa.Column("status", audio_status, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text),
        sa.Column("marks", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audios_article_id", "audios", ["article_id"])
    op.create_index("ix_audios_article_status", "audios", ["article_id", "status"])

    # -- ejecuciones --------------------------------------------------------
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("trigger", sa.String(20), server_default="scheduled"),
        sa.Column("status", run_status, nullable=False, server_default="ok"),
        sa.Column("sources_total", sa.Integer, server_default="0"),
        sa.Column("sources_failed", sa.Integer, server_default="0"),
        sa.Column("articles_new", sa.Integer, server_default="0"),
    )
    op.create_index("ix_collection_runs_started_at", "collection_runs", ["started_at"])

    op.create_table(
        "source_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("collection_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "columnist_id", sa.Integer, sa.ForeignKey("columnists.id", ondelete="SET NULL")
        ),
        sa.Column("columnist_name", sa.String(200)),
        sa.Column("status", run_status, nullable=False, server_default="ok"),
        sa.Column("articles_found", sa.Integer, server_default="0"),
        sa.Column("articles_new", sa.Integer, server_default="0"),
        sa.Column("duration_ms", sa.Integer, server_default="0"),
        sa.Column("extractor_used", sa.String(80)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_runs_run_id", "source_runs", ["run_id"])
    op.create_index("ix_source_runs_columnist_id", "source_runs", ["columnist_id"])
    op.create_index("ix_source_runs_created_at", "source_runs", ["created_at"])

    # -- preferencias -------------------------------------------------------
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("collect_hour", sa.Integer, nullable=False, server_default="6"),
        sa.Column("collect_minute", sa.Integer, nullable=False, server_default="0"),
        sa.Column("timezone", sa.String(60), server_default="America/Mexico_City"),
        sa.Column("tts_provider", sa.String(40), server_default="openai"),
        sa.Column("tts_voice", sa.String(80), server_default="onyx"),
        sa.Column("auto_generate_audio", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("playback_rate", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("retention_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("theme", sa.String(20), server_default="system"),
        sa.Column("font_size", sa.Integer, server_default="18"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- credenciales -------------------------------------------------------
    op.create_table(
        "media_credentials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("outlet", sa.String(200), nullable=False, unique=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="cookies"),
        sa.Column("encrypted_payload", sa.Text, nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("media_credentials")
    op.drop_table("user_preferences")
    op.drop_table("source_runs")
    op.drop_table("collection_runs")
    op.drop_table("audios")
    op.drop_table("articles")
    op.drop_table("columnists")
    bind = op.get_bind()
    audio_status.drop(bind, checkfirst=True)
    run_status.drop(bind, checkfirst=True)
    source_type.drop(bind, checkfirst=True)
