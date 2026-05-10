"""
RAG over user materials: chunk → (BM25 and/or hybrid embeddings) → budget pack → citeable refs.

Phase 1: BM25 lexical. Phase 2 (optional): BM25 pool + OpenAI embeddings + fusion (see ``rag_embeddings``).
"""

from __future__ import annotations

import json
import os
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from models import Document, StudyPlan

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 8
DEFAULT_MAX_CHARS = 10_000


def should_attach_library_context(message: str, tutor_mode: bool) -> bool:
    """When True, fetch BM25-ranked excerpts for the chat turn."""
    if tutor_mode:
        return True
    m = (message or "").lower()
    triggers = (
        "document",
        "uploaded",
        "my notes",
        "study plan",
        "my study",
        "material",
        "according to my",
        "from my file",
    )
    return any(t in m for t in triggers)


@dataclass(frozen=True)
class TextChunk:
    text: str
    tokens: tuple[str, ...]
    source_type: str
    source_id: int
    title: str
    chunk_index: int
    updated_ts: float

    @property
    def source_ref(self) -> str:
        return f"{self.source_type}:{self.source_id}#{self.chunk_index}"


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return [t for t in lowered.split() if len(t) > 1]


def bm25_scores(query_tokens: list[str], corpus_tokens: list[list[str]], k1: float = 1.2, b: float = 0.75) -> list[float]:
    """BM25 score per document in corpus."""
    n = len(corpus_tokens)
    if n == 0:
        return []

    df: dict[str, int] = defaultdict(int)
    doc_lens: list[int] = []
    for doc in corpus_tokens:
        dl = len(doc)
        doc_lens.append(dl)
        seen = set(doc)
        for t in seen:
            df[t] += 1

    avgdl = sum(doc_lens) / n if n else 1.0
    idf_cache: dict[str, float] = {}

    def idf(term: str) -> float:
        if term not in idf_cache:
            dfi = df.get(term, 0)
            idf_cache[term] = math.log((n - dfi + 0.5) / (dfi + 0.5) + 1.0)
        return idf_cache[term]

    scores: list[float] = []
    q_terms = query_tokens
    for doc_tokens in corpus_tokens:
        dt = Counter(doc_tokens)
        dl = len(doc_tokens)
        score = 0.0
        for term in q_terms:
            if term not in df:
                continue
            freq = dt.get(term, 0)
            if freq == 0:
                continue
            idfv = idf(term)
            denom = freq + k1 * (1 - b + b * (dl / avgdl))
            score += idfv * (freq * (k1 + 1)) / denom
        scores.append(score)
    return scores


def _append_chunk(
    out: list[TextChunk],
    text: str,
    source_type: str,
    source_id: int,
    title: str,
    chunk_index: int,
    updated_ts: float,
) -> None:
    text = (text or "").strip()
    if not text:
        return
    if len(text) > 8000:
        text = text[:8000] + "…"
    toks = tuple(tokenize(text))
    if not toks:
        return
    out.append(
        TextChunk(
            text=text,
            tokens=toks,
            source_type=source_type,
            source_id=source_id,
            title=title,
            chunk_index=chunk_index,
            updated_ts=updated_ts,
        )
    )


def chunks_from_document_row(doc: Document) -> list[TextChunk]:
    out: list[TextChunk] = []
    ts = doc.updated_at.timestamp() if doc.updated_at else 0.0
    title_base = doc.original_filename or "document"

    if doc.structured_content:
        try:
            data = json.loads(doc.structured_content)
        except (json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict):
            st = data.get("title") or title_base
            summary = data.get("summary") or ""
            if summary:
                _append_chunk(out, f"{st}\n{summary}", "doc", doc.id, st, 0, ts)
            for i, sec in enumerate(data.get("sections") or []):
                if not isinstance(sec, dict):
                    continue
                heading = sec.get("heading") or "Section"
                body = sec.get("content") or ""
                kps = sec.get("key_points") or []
                kp_txt = "\n".join(f"- {p}" for p in kps if p) if isinstance(kps, list) else ""
                block = f"{heading}\n{body}"
                if kp_txt:
                    block += f"\nKey points:\n{kp_txt}"
                _append_chunk(out, block, "doc", doc.id, st, i + 1, ts)
            return out or []

    raw = (doc.content or "").strip()
    if raw:
        _append_chunk(out, raw[:12000], "doc", doc.id, title_base, 0, ts)
    return out


def chunks_from_study_plan_row(plan: StudyPlan) -> list[TextChunk]:
    out: list[TextChunk] = []
    ts = plan.updated_at.timestamp() if plan.updated_at else 0.0
    content = plan.get_content()
    if not isinstance(content, dict):
        return out

    summary = content.get("summary") or ""
    title = content.get("title") or plan.title
    head = f"{plan.title}\n{summary}".strip()
    if head:
        _append_chunk(out, head, "plan", plan.id, title, 0, ts)

    for i, concept in enumerate(content.get("key_concepts") or []):
        if not isinstance(concept, dict):
            continue
        block = f"{concept.get('name', 'Concept')}: {concept.get('description', '')}"
        _append_chunk(out, block, "plan", plan.id, title, i + 1, ts)

    lp = content.get("learning_path") or []
    if isinstance(lp, list):
        for j, day in enumerate(lp[:21]):
            if not isinstance(day, dict):
                continue
            topics = day.get("topics") or []
            t_str = ", ".join(str(t) for t in topics) if isinstance(topics, list) else ""
            acts = day.get("activities") or []
            parts = [f"Day {day.get('day', j + 1)}: {t_str}"]
            if isinstance(acts, list):
                for act in acts[:6]:
                    if isinstance(act, dict):
                        parts.append(f"- ({act.get('type')}) {act.get('description', '')}")
            _append_chunk(out, "\n".join(parts), "plan", plan.id, title, 100 + j, ts)

    return out


def build_chunk_corpus(user_id: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    docs = Document.query.filter_by(user_id=user_id, processed=True).all()
    for d in docs:
        chunks.extend(chunks_from_document_row(d))
    plans = StudyPlan.query.filter_by(user_id=user_id).all()
    for p in plans:
        chunks.extend(chunks_from_study_plan_row(p))
    return chunks


def material_signature(user_id: int) -> str:
    """Cheap invalidation key for retrieval cache."""
    docs = Document.query.filter_by(user_id=user_id, processed=True).with_entities(
        Document.id, Document.updated_at
    ).all()
    plans = StudyPlan.query.filter_by(user_id=user_id).with_entities(StudyPlan.id, StudyPlan.updated_at).all()
    parts = [f"d:{i}:{u.timestamp() if u else 0}" for i, u in docs]
    parts += [f"p:{i}:{u.timestamp() if u else 0}" for i, u in plans]
    return "|".join(parts)


def select_ranked_chunks(
    query: str,
    chunks: Iterable[TextChunk],
    *,
    top_k: int = DEFAULT_TOP_K,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[TextChunk]:
    chunk_list = list(chunks)
    if not chunk_list:
        return []

    q_tokens = tokenize(query)
    if not q_tokens:
        q_tokens = tokenize("study interview preparation")

    corpus_tokens = [list(c.tokens) for c in chunk_list]
    scores = bm25_scores(q_tokens, corpus_tokens)

    indexed = list(enumerate(scores))
    max_score = max(scores) if scores else 0.0

    if max_score <= 0:
        indexed.sort(key=lambda x: chunk_list[x[0]].updated_ts, reverse=True)
        order = [i for i, _ in indexed]
    else:
        order = [i for i, _ in sorted(indexed, key=lambda x: x[1], reverse=True)]

    selected: list[TextChunk] = []
    total_chars = 0
    for idx in order:
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


def chunks_to_context_items(chunks: list[TextChunk], *, score_hint: str = "bm25_lexical") -> list[dict[str, Any]]:
    """Shape consumed by chat routes (JSON-serializable for caching)."""
    return [
        {
            "type": c.source_type,
            "title": c.title,
            "content": c.text,
            "source_ref": c.source_ref,
            "score_hint": score_hint,
        }
        for c in chunks
    ]


def format_context_block(items: list[dict[str, Any]]) -> str:
    lines = []
    for it in items:
        ref = it.get("source_ref", "?")
        title = it.get("title", "")
        body = it.get("content", "")
        lines.append(f"[{ref}] {title}\n{body}")
    return "\n\n---\n\n".join(lines)


def retrieve_ranked_context(
    query: str,
    user_id: int,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict[str, Any]]:
    chunks = build_chunk_corpus(user_id)
    if not chunks:
        logger.debug("rag: empty corpus user_id=%s", user_id)
        return []

    expand_enabled = os.environ.get("RAG_QUERY_EXPAND", "false").lower() in ("1", "true", "yes")
    use_emb = os.environ.get("RAG_USE_EMBEDDINGS", "true").lower() in ("1", "true", "yes")
    lex_w = float(os.environ.get("RAG_HYBRID_LEX_WEIGHT", "0.35"))

    trace_parts: list[str] = []
    eq = query
    if expand_enabled or use_emb:
        from extensions import openai_client

        if expand_enabled:
            from rag_query_expand import maybe_expand_query

            eq = maybe_expand_query(query, openai_client)
            trace_parts.append("expand")

    hint_base = "bm25_lexical"
    ranked: list[TextChunk]

    if use_emb:
        q_tokens = tokenize(eq)
        if not q_tokens:
            q_tokens = tokenize("study interview preparation")
        corpus_tokens = [list(c.tokens) for c in chunks]
        scores = bm25_scores(q_tokens, corpus_tokens)
        try:
            from rag_embeddings import select_ranked_chunks_hybrid

            retrieval_trace: list[str] = []
            ranked = select_ranked_chunks_hybrid(
                eq,
                chunks,
                openai_client,
                bm25_scores=scores,
                top_k=top_k,
                max_chars=max_chars,
                lex_weight=lex_w,
                retrieval_trace=retrieval_trace,
            )
            hint_base = "hybrid_bm25_openai_embedding"
            trace_parts.extend(retrieval_trace)
        except Exception:
            logger.exception("hybrid RAG failed; falling back to BM25 only")
            ranked = select_ranked_chunks(eq, chunks, top_k=top_k, max_chars=max_chars)
    else:
        ranked = select_ranked_chunks(eq, chunks, top_k=top_k, max_chars=max_chars)

    score_hint = hint_base + ("+" + "+".join(trace_parts) if trace_parts else "")

    logger.debug(
        "rag: user_id=%s corpus_chunks=%s selected=%s mode=%s q_tokens=%s",
        user_id,
        len(chunks),
        len(ranked),
        score_hint,
        len(tokenize(eq)),
    )
    return chunks_to_context_items(ranked, score_hint=score_hint)
