from explorer_worker.memory import similar


def test_similar_questions_are_recognised():
    assert similar(
        "What policy number should I use?", "Which policy number should I use for testing?"
    )
    assert similar(
        "May I press Approve on the leave request?", "Can I press Approve on leave request"
    )
    assert not similar("What policy number should I use?", "May I press Delete on the customer?")
    assert not similar("", "anything")
