"""Проверка, что ответ бота опирается на базу знаний (защита от выдумок).

Две проверки кодом, без участия модели. Если ответ их не проходит, клиенту
он не отправляется — вопрос передаётся специалисту.

1. Числа. Каждое число в ответе (цена, срок, лимит, процент) должно быть
   в найденных статьях или в вопросе клиента. Выдуманные цифры — самый
   опасный вид ошибки в поддержке: клиент принимает по ним решения.

2. Слова. Доля значимых слов ответа, которые есть в статьях. Ловит грубые
   выдумки: ответ «про другое», которого в статьях нет вообще.

Пороги подобраны по 58 реальным ответам GigaChat-2 из прогонов eval/:
у честных ответов совпадение по словам 0.42–1.00, у выдуманного отказа
про 1С — 0.14. Лишние числа были только в выдуманном ответе про цены.

Известное ограничение: тонкую выдумку, сказанную словами из статей
(«загрузить свой курс нельзя» — 0.59, как у честных ответов), эти проверки
не ловят. Для неё нужна отдельная проверка второй моделью.

Пробовали и отказались (подробности в истории коммитов):
- цитата из статьи в ответе модели — модель цитирует формально, настоящая
  цитата не доказывает правильность ответа (выдуманные цены шли с честной цитатой);
- проверка отрицаний — срабатывала на 16 честных ответах из 51.
"""

import re

from app.lexical import STOPWORDS, _stemmer

MIN_COVERAGE = 0.35

# Числа с разделителями разрядов: «15 000», «1 000 000»
_NUMBER = re.compile(r"\d{1,3}(?:[   ]\d{3})+|\d+")
# Номера пунктов списка в начале строки: «1. Откройте…», «2) Нажмите…»
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def content_words(text: str) -> list[str]:
    """Значимые слова, приведённые к основе."""
    words = re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е"))
    return [_stemmer.stem_word(w) for w in words
            if w not in STOPWORDS and (len(w) > 1 or w.isdigit())]


def coverage(text: str, articles_text: str) -> float:
    """Доля значимых слов текста, которые встречаются в статьях."""
    words = content_words(text)
    if not words:
        return 0.0
    source = set(content_words(articles_text))
    return sum(w in source for w in words) / len(words)


def numbers(text: str) -> set[str]:
    """Все числа в тексте, без пробелов-разделителей и номеров пунктов списка."""
    text = _LIST_MARKER.sub(" ", text)
    return {re.sub(r"\s", "", n) for n in _NUMBER.findall(text)}


def invented_numbers(text: str, articles_text: str, question: str = "") -> set[str]:
    """Числа из ответа, которых нет ни в статьях, ни в вопросе клиента."""
    return numbers(text) - numbers(articles_text) - numbers(question)


def check(text: str, articles_text: str, question: str = "") -> str:
    """Пустая строка — ответ можно отправлять. Иначе — причина, почему нельзя."""
    extra = invented_numbers(text, articles_text, question)
    if extra:
        return "числа не из статей: " + ", ".join(sorted(extra))
    if coverage(text, articles_text) < MIN_COVERAGE:
        return "ответ не похож на статьи"
    return ""
