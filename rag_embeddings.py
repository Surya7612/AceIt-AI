"""
Phase 2 hybrid retrieval: BM25 shortlist → embedding similarity → score fusion.

Uses OpenAI ``text-embedding-3-small`` by default; caches vectors in Redis when available.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from typing import Any

from cache_helper import cache_data, get_cached_data
from embedding_store import embedding_vector_load, embedding_vector_save

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_POOL = int(os.environ.get("RAG_EMBEDDING_POOL", "48"))
EMBED_CACHE_TTL = int(os.environ.get("RAG_EMBEDDING_CACHE_TTL", str(7 * 24 * 3600)))
MAX_INPUT_CHARS = int(os.environ.get("RAG_EMBEDDING_MAX_CHARS", "6000"))


def _embed_cache_key(model: str, text: str) -> str:
    h = hashlib.sha256(f"{model}:{text}".encode("utf-8")).hexdigest()
    return f"rag_emb:v1:{model}:{h[:32]}"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def min_max_norm(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _trim(s: str) -> str:
    s = (s or "").strip()
    if len(s) > MAX_INPUT_CHARS:
        return s[:MAX_INPUT_CHARS] + "…"
    return s


def _fetch_embeddings_uncached(client: Any, texts: list[str], model: str) -> list[list[float]]:
    """Single API call; ``texts`` must be non-empty."""
    resp = client.embeddings.create(model=model, input=texts)
    ordered = sorted(resp.data, key=lambda d: getattr(d, "index", 0))
    return [list(item.embedding) for item in ordered]


def get_embeddings_for_texts(client: Any, texts: list[str], model: str = DEFAULT_MODEL) -> list[list[float]]:
    """Return one embedding per string: Redis → SQL cache → OpenAI API."""
    if not texts:
        return []

    results: list[list[float] | None] = [None] * len(texts)
    to_fetch: list[tuple[int, str, str]] = []

    for i, raw in enumerate(texts):
        t = _trim(raw)
        key = _embed_cache_key(model, t)
        cached = get_cached_data(key)
        if cached is not None and isinstance(cached, list):
            results[i] = [float(x) for x in cached]
            continue

        db_vec = embedding_vector_load(key)
        if db_vec is not None:
            results[i] = db_vec
            cache_data(key, db_vec, EMBED_CACHE_TTL)
            continue

        to_fetch.append((i, t, key))

    if to_fetch:
        batch_texts = [t for _, t, _ in to_fetch]
        try:
            fresh = _fetch_embeddings_uncached(client, batch_texts, model)
        except Exception:
            logger.exception("OpenAI embeddings.batch failed model=%s batch_len=%s", model, len(batch_texts))
            raise

        for (idx, t, key), vec in zip(to_fetch, fresh):
            results[idx] = vec
            cache_data(key, vec, EMBED_CACHE_TTL)
            embedding_vector_save(key, vec)

    out = []
    for i, r in enumerate(results):
        if r is None:
            raise RuntimeError(f"missing embedding at index {i}")
        out.append(r)
    return out


def hybrid_chunk_order(
    query: str,
    chunk_indices: list[int],
    bm25_scores: list[float],
    chunk_list: list[Any],
    client: Any,
    *,
    lex_weight: float,
    model: str = DEFAULT_MODEL,
) -> list[int]:
    """Return ``chunk_indices`` reordered by fused lexical + semantic score (desc)."""
    if not chunk_indices:
        return []

    subset_bm25 = [bm25_scores[i] for i in chunk_indices]
    texts = [_trim(chunk_list[i].text) for i in chunk_indices]

    q_emb = get_embeddings_for_texts(client, [_trim(query)], model=model)[0]
    doc_embs = get_embeddings_for_texts(client, texts, model=model)

    cos_vals = [cosine_similarity(q_emb, e) for e in doc_embs]
    n_lex = min_max_norm(subset_bm25)
    n_cos = min_max_norm(cos_vals)

    w = max(0.0, min(1.0, lex_weight))
    fused = [w * lx + (1.0 - w) * ce for lx, ce in zip(n_lex, n_cos)]

    order_local = sorted(range(len(chunk_indices)), key=lambda j: fused[j], reverse=True)
    return [chunk_indices[j] for j in order_local]


def select_ranked_chunks_hybrid(
    query: str,
    chunk_list: list[Any],
    client: Any,
    *,
    bm25_scores: list[float],
    top_k: int,
    max_chars: int,
    pool_size: int = DEFAULT_POOL,
    lex_weight: float = 0.35,
    model: str = DEFAULT_MODEL,
    retrieval_trace: list[str] | None = None,
) -> list[Any]:
    """BM25 pool → embeddings fuse → same greedy packing as lexical-only path."""
    from rag_context import TextChunk, tokenize  # noqa: PLC0415

    n = len(chunk_list)
    if n == 0:
        return []

    pool = min(pool_size, n)
    indexed = list(enumerate(bm25_scores))
    max_score = max(bm25_scores) if bm25_scores else 0.0

    if max_score <= 0:
        indexed.sort(key=lambda x: chunk_list[x[0]].updated_ts, reverse=True)
        candidate_indices = [i for i, _ in indexed[:pool]]
    else:
        indexed.sort(key=lambda x: x[1], reverse=True)
        candidate_indices = [i for i, _ in indexed[:pool]]

    ordered_indices = hybrid_chunk_order(
        query,
        candidate_indices,
        bm25_scores,
        chunk_list,
        client,
        lex_weight=lex_weight,
        model=model,
    )

    from rag_llm_rerank import maybe_llm_rerank_chunk_order

    before_rerank = tuple(ordered_indices)
    ordered_indices = maybe_llm_rerank_chunk_order(query, chunk_list, ordered_indices, client)
    if retrieval_trace is not None and tuple(ordered_indices) != before_rerank:
        retrieval_trace.append("llm_rerank")

    selected: list[TextChunk] = []
    total_chars = 0
    seen = set()

    for idx in ordered_indices:
        if idx in seen:
            continue
        seen.add(idx)
        if len(selected) >= top_k:
            break
        ch = chunk_list[idx]
        add_len = len(ch.text) + 80
        if total_chars + add_len > max_chars:
            remain = max_chars - total_chars - 80
            if remain < 200:
                break
            truncated = ch.text[:remain] + "…"
            sel = TextChunk(
                text=truncated,
                tokens=tuple(tokenize(truncated)),
                source_type=ch.source_type,
                source_id=ch.source_id,
                title=ch.title,
                chunk_index=ch.chunk_index,
                updated_ts=ch.updated_ts,
            )
            selected.append(sel)
            break
        selected.append(ch)
        total_chars += add_len

    return selected
