import json
from pathlib import Path

import pytest

from schema_eval import validate_study_schedule_json

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_study_schedule_fixture_passes_schema():
    raw = (FIXTURES / "study_schedule_valid.json").read_text(encoding="utf-8")
    schedule = json.loads(raw)
    ok, err = validate_study_schedule_json(schedule)
    assert ok, err


def test_bm25_prefers_expected_terms_from_fixture():
    """Lexical expectations file documents product intent; enforce BM25 ordering."""
    expectations = json.loads((FIXTURES / "rag_expectations.json").read_text(encoding="utf-8"))
    case = expectations["bm25_queries"][0]
    from rag_context import bm25_scores, tokenize

    query_tokens = tokenize(case["query"])
    corpus_tokens = [
        tokenize("Italian pasta carbonara recipe with eggs"),
        tokenize("Python asyncio event loop tasks and futures"),
    ]
    scores = bm25_scores(query_tokens, corpus_tokens)
    assert scores[1] > scores[0], "asyncio doc should score above unrelated recipe"
