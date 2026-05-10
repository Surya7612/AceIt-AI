"""Baseline schema (all tables).

Existing databases created with ``db.create_all()`` are detected via the ``user``
table and skipped so ``flask db upgrade`` remains safe.

Revision ID: 001_baseline
Revises:
Create Date: 2026-05-10

"""

from alembic import op

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    if inspector.has_table("user"):
        return

    import models  # noqa: F401

    from extensions import db

    db.metadata.create_all(bind=conn)


def downgrade():
    raise NotImplementedError(
        "Baseline downgrade is disabled to avoid accidental data loss."
    )
