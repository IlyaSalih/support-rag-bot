"""Юнит-тесты защиты от выдумок. Не требуют GigaChat и модели эмбеддингов.

Примеры взяты из реальных ответов GigaChat-2 в прогонах eval/.

Запуск из корня проекта:
    pytest
"""

from app.grounding import check, coverage, invented_numbers, numbers

ARTICLE = """
## Тарифы

| Тариф | Активных сотрудников |
|---|---|
| Старт | до 50 |
| Бизнес | до 300 |

## Как оплатить

1. Раздел «Тариф» → «Продлить».
2. Выберите срок: 3, 6 или 12 месяцев.

Оплата только по безналичному расчёту от юридического лица или ИП.
Доступ продлевается в течение **1 рабочего дня** после поступления денег.
"""


# ---------- числа ----------

def test_invented_prices_are_caught():
    # Реальный ответ модели на «Сколько стоит тариф Бизнес?» — цен в базе нет
    answer = ("Стоимость тарифа «Бизнес» зависит от срока оплаты: 3 месяца — 15 000 ₽, "
              "6 месяцев — 27 000 ₽, 12 месяцев — 54 000 ₽.")
    assert invented_numbers(answer, ARTICLE) == {"15000", "27000", "54000"}
    assert check(answer, ARTICLE).startswith("числа не из статей")


def test_numbers_from_article_pass():
    assert invented_numbers("На тарифе Бизнес до 300 сотрудников, оплата на 3, 6 или 12 месяцев.",
                            ARTICLE) == set()


def test_numbers_from_question_pass():
    # Клиент сам назвал число — повторить его в ответе не выдумка
    assert invented_numbers("Для 200 сотрудников подойдёт тариф Бизнес.", ARTICLE,
                            question="У нас 200 сотрудников, какой тариф?") == set()


def test_list_markers_are_not_numbers():
    answer = "4. Откройте раздел «Тариф».\n5. Нажмите «Продлить»."
    assert numbers(answer) == set()


def test_thousands_separator():
    assert numbers("Цена 1 500 000 рублей") == {"1500000"}


# ---------- совпадение по словам ----------

def test_honest_answer_passes():
    answer = "Откройте раздел «Тариф» → «Продлить» и выберите срок. Оплата — безналичным расчётом от юрлица или ИП."
    assert check(answer, ARTICLE) == ""


def test_off_topic_invention_is_caught():
    # Похоже на реальный выдуманный отказ про интеграцию с 1С
    answer = "Подключение платформы к 1С через API сейчас недоступно."
    assert coverage(answer, ARTICLE) < 0.35
    assert check(answer, ARTICLE) != ""


def test_empty_answer_is_caught():
    assert check("", ARTICLE) != ""
