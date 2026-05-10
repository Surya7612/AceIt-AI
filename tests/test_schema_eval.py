import pytest

from schema_eval import validate_study_schedule_json


def test_validate_minimal_schedule_ok():
    schedule = {
        "title": "System design",
        "summary": "Overview",
        "key_concepts": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
        "learning_path": [{"day": 1, "topics": ["x"], "activities": []}],
        "practice_questions": [{}, {}, {}, {}, {}],
    }
    ok, err = validate_study_schedule_json(schedule)
    assert ok is True
    assert err is None


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"title": "x", "summary": "y", "key_concepts": [], "learning_path": [], "practice_questions": []},
        {"title": "x", "summary": "y", "key_concepts": [1, 2], "learning_path": [], "practice_questions": [{}] * 5},
    ],
)
def test_validate_rejects_invalid(bad):
    ok, err = validate_study_schedule_json(bad)
    assert ok is False
    assert err
