"""Deterministic validation for AI-generated study schedules (eval / regression tests)."""


def validate_study_schedule_json(schedule: dict) -> tuple[bool, str | None]:
    """
    Return (ok, error_message). Matches expectations enforced after ``generate_study_schedule``.
    """
    if not isinstance(schedule, dict):
        return False, "schedule must be a dict"

    required_fields = ["title", "summary", "key_concepts", "learning_path", "practice_questions"]
    for field in required_fields:
        if field not in schedule:
            return False, f"missing field: {field}"

    kc = schedule["key_concepts"]
    pq = schedule["practice_questions"]
    if not isinstance(kc, list) or len(kc) < 3:
        return False, "key_concepts must be a list with at least 3 entries"
    if not isinstance(pq, list) or len(pq) < 5:
        return False, "practice_questions must be a list with at least 5 entries"

    return True, None
