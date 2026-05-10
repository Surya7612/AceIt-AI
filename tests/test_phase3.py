import json
from pathlib import Path
from unittest.mock import MagicMock

from rag_llm_rerank import maybe_llm_rerank_chunk_order
from rag_query_expand import maybe_expand_query
from rag_context import TextChunk, tokenize

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_eval_manifest_points_to_existing_fixtures():
    manifest = json.loads((FIXTURES / "eval_manifest.json").read_text(encoding="utf-8"))
    for name in manifest["fixtures"]:
        assert (FIXTURES / name).is_file(), f"missing fixture {name}"


def test_expand_disabled_returns_original():
    client = MagicMock()
    assert maybe_expand_query("hello asyncio", client) == "hello asyncio"
    client.chat.completions.create.assert_not_called()


def test_llm_rerank_disabled_returns_same_order():
    chunks = [
        TextChunk(
            text="a",
            tokens=tuple(tokenize("alpha beta")),
            source_type="doc",
            source_id=1,
            title="t",
            chunk_index=0,
            updated_ts=1.0,
        )
    ]
    client = MagicMock()
    order = [0]
    assert maybe_llm_rerank_chunk_order("q", chunks, order, client) == order


def test_embedding_store_roundtrip(app):
    with app.app_context():
        from embedding_store import embedding_vector_load, embedding_vector_save

        key = "rag_emb:v1:test-model:deadbeef"
        vec = [0.25, 0.5, 0.75]
        embedding_vector_save(key, vec)
        loaded = embedding_vector_load(key)
        assert loaded == vec


def test_llm_rerank_reorders(monkeypatch):
    monkeypatch.setenv("RAG_LLM_RERANK", "true")

    chunks = [
        TextChunk(
            text="recipe pasta",
            tokens=tuple(tokenize("recipe pasta")),
            source_type="doc",
            source_id=1,
            title="cook",
            chunk_index=0,
            updated_ts=1.0,
        ),
        TextChunk(
            text="asyncio python tasks",
            tokens=tuple(tokenize("asyncio python tasks")),
            source_type="doc",
            source_id=2,
            title="py",
            chunk_index=0,
            updated_ts=2.0,
        ),
    ]

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.model = "gpt-4o-mini"
    mock_resp.usage = None
    mock_resp.choices[0].message.content = json.dumps({"order": [1, 0]})

    monkeypatch.setattr("openai_usage.timed_completion", lambda op, fn: mock_resp)

    client = MagicMock()
    out = maybe_llm_rerank_chunk_order(
        "explain asyncio",
        chunks,
        [0, 1],
        client,
        pool=12,
    )
    assert out == [1, 0]
