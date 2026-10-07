"""Identificación de navegador por fuente.

Algunos medios (Milenio, entre otros) devuelven 403 a cualquier cliente que no
sea un navegador, incluso para servir su robots.txt. Esta bandera permite
activar, fuente por fuente, que las peticiones se identifiquen como lo haría
el navegador del usuario.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "columnists",
        sa.Column(
            "browser_identity",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("columnists", "browser_identity")
