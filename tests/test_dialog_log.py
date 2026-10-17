"""Тесты маскировки персональных данных в журнале диалогов."""

from app.dialog_log import mask_personal_data


def test_snils_is_masked():
    assert mask_personal_data("Вот СНИЛС 123-456-789 01, внесите") == "Вот СНИЛС [СНИЛС], внесите"
    assert "12345678901" not in mask_personal_data("снилс 12345678901")


def test_phone_is_masked():
    assert "[ТЕЛЕФОН]" in mask_personal_data("Позвоните +7 (912) 345-67-89")
    assert "[ТЕЛЕФОН]" in mask_personal_data("мой номер 89123456789")


def test_email_is_masked():
    assert mask_personal_data("пишите на ivanova@company.ru") == "пишите на [EMAIL]"


def test_ordinary_numbers_are_kept():
    # Обычные числа из вопросов — не персональные данные
    text = "Загружаю файл на 800 сотрудников, тест на 80%"
    assert mask_personal_data(text) == text


def test_own_domain_is_not_masked():
    text = "Письмо приходит с адреса no-reply@traininghub.example, пишите ivanova@company.ru"
    assert mask_personal_data(text) == "Письмо приходит с адреса no-reply@traininghub.example, пишите [EMAIL]"


def test_personal_data_detection():
    from app.dialog_log import has_personal_data
    assert has_personal_data("Вот СНИЛС сотрудника 123-456-789 01, внесите его")
    assert has_personal_data("мой номер +7 912 345-67-89")
    assert not has_personal_data("Загружаю файл на 800 сотрудников")
    assert not has_personal_data("Как указать СНИЛС в карточке?")
