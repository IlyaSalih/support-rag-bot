"""Тесты постобработки ответа: без GigaChat и поиска (они подменяются)."""

import app.answer as a


def _answer_with(raw: str):
    a._pick_articles = lambda q: ([], 0.3)
    a.complete = lambda system, user: raw
    return a.answer("вопрос")


def test_escalation_drops_send_to_support_phrase():
    # Реальный случай из журнала: противоречие «напишите в поддержку» + «передаю специалисту»
    res = _answer_with("[ESCALATE]\nПожалуйста, напишите в поддержку с официальным письмом от компании.")
    assert res.action == a.ESCALATE
    assert "напишите в поддержку" not in res.text
    assert res.text == a.ESCALATION_TEXT


def test_escalation_keeps_empathy_phrase():
    res = _answer_with("[ESCALATE]\nПонимаю, как это неприятно.")
    assert res.text.startswith("Понимаю, как это неприятно.")
    assert res.text.endswith(a.ESCALATION_TEXT)


def test_unknown_label_escalates():
    res = _answer_with("Просто текст без метки")
    assert res.action == a.ESCALATE


def test_answer_send_to_support_replaced_with_button_hint():
    # Реальный ответ из журнала
    text = ("Проверьте, пожалуйста, прошли ли 15 минут после сдачи теста. "
            "Если прошло больше часа, напишите нам с указанием email сотрудника и курса.")
    result = a.replace_send_to_support(text)
    assert "напишите нам" not in result
    assert result.startswith("Проверьте, пожалуйста, прошли ли 15 минут после сдачи теста.")
    assert result.endswith(a.NOT_HELPED_HINT)


def test_answer_without_phrase_is_untouched():
    text = "1. Откройте раздел «Сотрудники».\n2. Нажмите «Добавить сотрудника»."
    assert a.replace_send_to_support(text) == text


def test_list_structure_is_kept():
    text = ("1. Проверьте папку «Спам».\n2. Проверьте email.\n\n"
            "Если письмо не пришло, напишите в поддержку.")
    result = a.replace_send_to_support(text)
    assert result.startswith("1. Проверьте папку «Спам».\n2. Проверьте email.")
    assert "поддержку" not in result.replace(a.NOT_HELPED_HINT, "")
