"""The App Summary can't be confirmed while one of its own questions is
unanswered — the answers change what Explorer tests."""

from api.explorer import unanswered_questions


def test_confirm_needs_every_summary_question_answered() -> None:
    brief = {
        "questions_for_you": [
            {"question": "A?", "answer": "Yes"},
            {"question": "B?", "answer": ""},
        ]
    }
    assert unanswered_questions(brief) == 1
    assert unanswered_questions({"questions_for_you": [{"question": "A?", "answer": "Yes"}]}) == 0
    assert unanswered_questions(None) == 0
    assert unanswered_questions({}) == 0
