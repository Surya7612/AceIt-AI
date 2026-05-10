"""SQL persistence for embedding vector cache (Phase 3).

Revision ID: 002_chunk_emb
Revises: 001_baseline
Create Date: 2026-05-11

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "002_chunk_emb"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if inspect(conn).has_table("chunk_embedding_cache"):
        return

    op.create_table(
        "chunk_embedding_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cache_key", sa.String(length=192), nullable=False),
        sa.Column("vector_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chunk_embedding_cache_cache_key",
        "chunk_embedding_cache",
        ["cache_key"],
        unique=True,
    )
    op.create_index(
        "idx_chunk_embedding_cache_created_at",
        "chunk_embedding_cache",
        ["created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_chunk_embedding_cache_created_at", table_name="chunk_embedding_cache")
    op.drop_index("ix_chunk_embedding_cache_cache_key", table_name="chunk_embedding_cache")
    op.drop_table("chunk_embedding_cache")
