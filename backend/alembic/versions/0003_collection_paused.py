"""Pausa general de la recolección.

Sirve para dejar la app en modo lectura: se sigue leyendo y escuchando todo
lo ya recopilado, pero no entra nada nuevo, no se genera audio y no se borra
nada por retención.

Vive en la base de datos y no en un contenedor parado a propósito: parar
contenedores lo desharía el siguiente «docker compose up -d» sin avisar, y
el usuario se encontraría la app recolectando otra vez sin haberlo pedido.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column(
            "collection_paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "collection_paused")
