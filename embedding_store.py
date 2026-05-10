"""Persist embedding vectors in SQL so caches survive Redis eviction (Phase 3)."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def embedding_vector_load(cache_key: str) -> list[float] | None:
    try:
        from flask import has_app_context

        if not has_app_context():
            return None
        from models import ChunkEmbeddingCache

        row = ChunkEmbeddingCache.query.filter_by(cache_key=cache_key).first()
        if not row:
            return None
        data = json.loads(row.vector_json)
        return [float(x) for x in data]
    except Exception:
        logger.debug("embedding DB load miss key=%s", cache_key[:48], exc_info=True)
        return None


def embedding_vector_save(cache_key: str, vector: list[float]) -> None:
    try:
        from flask import has_app_context

        if not has_app_context():
            return
        from models import ChunkEmbeddingCache
        from extensions import db

        if ChunkEmbeddingCache.query.filter_by(cache_key=cache_key).first():
            return
        row = ChunkEmbeddingCache(cache_key=cache_key, vector_json=json.dumps(vector))
        db.session.add(row)
        db.session.commit()
    except Exception:
        logger.debug("embedding DB save failed key=%s", cache_key[:48], exc_info=True)
        try:
            from extensions import db

            db.session.rollback()
        except Exception:
            pass
