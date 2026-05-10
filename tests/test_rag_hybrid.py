import pytest

from rag_embeddings import cosine_similarity, min_max_norm
from rag_context import TextChunk, tokenize


def test_cosine_similarity_basic():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_min_max_norm_spread():
    assert min_max_norm([1.0, 3.0]) == pytest.approx([0.0, 1.0])


def test_hybrid_chunk_order_prefers_embedding_alignment(monkeypatch):
    from rag_embeddings import hybrid_chunk_order

    chunks = [
        TextChunk(
            text="Detailed guide to pasta carbonara ingredients",
            tokens=tuple(tokenize("Detailed guide to pasta carbonara ingredients")),
            source_type="doc",
            source_id=1,
            title="Cooking",
            chunk_index=0,
            updated_ts=1.0,
        ),
        TextChunk(
            text="Python asyncio event loops for concurrent IO",
            tokens=tuple(tokenize("Python asyncio event loops for concurrent IO")),
            source_type="doc",
            source_id=2,
            title="Python",
            chunk_index=0,
            updated_ts=2.0,
        ),
    ]
    bm25_scores = [2.0, 2.0]

    def fake_embeddings(client, texts, model="ignored"):
        out = []
        for text in texts:
            low = text.lower()
            if "asyncio" in low:
                out.append([1.0, 0.0, 0.0])
            elif "carbonara" in low or "pasta" in low:
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([0.33, 0.33, 0.34])
        return out

    monkeypatch.setattr("rag_embeddings.get_embeddings_for_texts", fake_embeddings)

    ordered = hybrid_chunk_order(
        "explain asyncio tasks",
        [0, 1],
        bm25_scores,
        chunks,
        client=None,
        lex_weight=0.1,
        model="test-model",
    )
    assert ordered[0] == 1, "embedding-aligned asyncio chunk should rank first"
