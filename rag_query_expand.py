"""
Optional query expansion for retrieval (cheap chat model, JSON phrases).

Controlled by ``RAG_QUERY_EXPAND=true``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

EXPAND_MODEL = os.environ.get("RAG_EXPAND_MODEL", "gpt-4o-mini")


def maybe_expand_query(query: str, client: Any) -> str:
    if os.environ.get("RAG_QUERY_EXPAND", "false").lower() not in ("1", "true", "yes"):
        return query
    q = (query or "").strip()
    if not q:
        return query

    try:
        from openai_usage import timed_completion

        response = timed_completion(
            "rag_query_expand",
            lambda: client.chat.completions.create(
                model=EXPAND_MODEL,
                temperature=0.2,
                max_tokens=220,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You help retrieval for technical interview prep. "
                            'Reply with JSON only: {"phrases":["..."]} — 3–8 short '
                            "search phrases or synonyms (no full sentences) that "
                            "capture intent for lexical + semantic search."
                        ),
                    },
                    {"role": "user", "content": q},
                ],
            ),
        )
        payload = json.loads(response.choices[0].message.content)
        phrases = payload.get("phrases") or []
        extra = " ".join(str(p).strip() for p in phrases[:8] if p)
        if not extra:
            return query
        return f"{q}\n{extra}".strip()
    except Exception:
        logger.exception("query expansion failed; using original query")
        return query
