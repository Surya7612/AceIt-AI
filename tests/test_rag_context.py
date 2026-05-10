from rag_context import TextChunk, bm25_scores, select_ranked_chunks, tokenize


def test_tokenize_strips_noise():
    assert "hello" in tokenize("Hello, world!")
    assert tokenize("a") == []


def test_bm25_prefers_matching_chunk():
    chunks = [
        TextChunk(
            text="Python asyncio event loops",
            tokens=tuple(tokenize("Python asyncio event loops")),
            source_type="doc",
            source_id=1,
            title="t",
            chunk_index=0,
            updated_ts=1.0,
        ),
        TextChunk(
            text="Cooking pasta carbonara recipe",
            tokens=tuple(tokenize("Cooking pasta carbonara recipe")),
            source_type="doc",
            source_id=2,
            title="t",
            chunk_index=0,
            updated_ts=1.0,
        ),
    ]
    q = tokenize("asyncio python concurrency")
    scores = bm25_scores(q, [list(c.tokens) for c in chunks])
    assert scores[0] > scores[1]


def test_select_respects_char_budget():
    big = "word " * 3000
    chunks = [
        TextChunk(
            text=big,
            tokens=tuple(tokenize(big)),
            source_type="doc",
            source_id=1,
            title="big",
            chunk_index=0,
            updated_ts=1.0,
        ),
        TextChunk(
            text="small tail chunk about graphs",
            tokens=tuple(tokenize("small tail chunk about graphs")),
            source_type="doc",
            source_id=2,
            title="small",
            chunk_index=1,
            updated_ts=2.0,
        ),
    ]
    picked = select_ranked_chunks("graphs tail", chunks, top_k=5, max_chars=1200)
    assert picked
    total = sum(len(p.text) for p in picked)
    assert total <= 1300
