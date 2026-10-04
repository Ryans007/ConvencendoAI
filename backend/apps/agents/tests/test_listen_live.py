from apps.agents.graph import listen as listen_module


def _resume_with(monkeypatch, *values):
    sequence = iter(values)
    monkeypatch.setattr(listen_module, "interrupt", lambda _: next(sequence))
    return listen_module.listen_live({"turn_count": 2})


def test_plain_text_resume_gives_an_unmarked_turn(monkeypatch):
    result = _resume_with(monkeypatch, "Yes, I did.")

    message = result["messages"][0]
    assert message.content == "Yes, I did."
    assert message.additional_kwargs == {}
    assert result["turn_count"] == 3


def test_resume_after_a_hint_marks_the_turn(monkeypatch):
    result = _resume_with(monkeypatch, {"text": " I chose PostgreSQL. ", "after_hint": True})

    message = result["messages"][0]
    assert message.content == "I chose PostgreSQL."
    assert message.additional_kwargs == {"after_hint": True}


def test_empty_resumes_wait_for_a_real_turn(monkeypatch):
    result = _resume_with(monkeypatch, "  ", {"text": "", "after_hint": True}, "Yes.")

    assert result["messages"][0].content == "Yes."
    assert result["messages"][0].additional_kwargs == {}
