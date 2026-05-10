"""
Optional LLM rerank on the fused candidate list (Phase 3).

Uses a small chat model to reorder top passages by relevance. Env: ``RAG_LLM_RERANK=true``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

RERANK_MODEL = os.environ.get("RAG_RERANK_MODEL", "gpt-4o-mini")
DEFAULT_POOL = int(os.environ.get("RAG_RERANK_POOL", "12"))


def maybe_llm_rerank_chunk_order(
    query: str,
    chunk_list: list[Any],
    ordered_indices: list[int],
    client: Any,
    *,
    pool: int | None = None,
) -> list[int]:
    if os.environ.get("RAG_LLM_RERANK", "false").lower() not in ("1", "true", "yes"):
        return ordered_indices
    if not ordered_indices:
        return ordered_indices

    lim = min(pool or DEFAULT_POOL, len(ordered_indices))
    head = ordered_indices[:lim]
    tail = ordered_indices[lim:]

    passages = []
    for pos, idx in enumerate(head):
        ch = chunk_list[idx]
        excerpt = ch.text[:1400]
        passages.append(
            {
                "position": pos,
                "source_ref": ch.source_ref,
                "title": ch.title,
                "text": excerpt,
            }
        )

    try:
        from openai_usage import timed_completion

        response = timed_completion(
            "rag_llm_rerank",
            lambda: client.chat.completions.create(
                model=RERANK_MODEL,
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Rank passages for relevance to the user query for interview-study RAG. "
                            'JSON only: {"order":[...]} where order is a permutation of passage '
                            '"position" integers 0..n-1 (best first). No extra keys.'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"query": query, "passages": passages}, ensure_ascii=False),
                    },
                ],
            ),
        )
        data = json.loads(response.choices[0].message.content)
        order = data.get("order")
        if not isinstance(order, list) or len(order) != len(head):
            raise ValueError("invalid order length")
        valid = set(range(len(head)))
        seen = set()
        for x in order:
            if not isinstance(x, int) or x not in valid or x in seen:
                raise ValueError("invalid permutation")
            seen.add(x)
        reranked_head = [head[i] for i in order]
        return reranked_head + tail
    except Exception:
        logger.exception("LLM rerank failed; keeping embedding order")
        return ordered_indices
