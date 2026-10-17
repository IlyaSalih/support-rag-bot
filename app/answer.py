"""Сборка ответа клиенту: поиск по базе знаний + GigaChat + решение об эскалации.

Проверка из корня проекта:
    python -m app.answer "нажимаю отправить в реестр, а ничего не происходит"
"""

import re
import sys
from dataclasses import dataclass, field

from app import config
from app.ingest import parse_article
from app.llm import complete
from app.retriever import best_semantic_score, search

# Возможные решения бота
ANSWER = "answer"      # ответил сам по базе знаний
ESCALATE = "escalate"  # передаёт обращение оператору
DECLINE = "decline"    # вежливо отказал (не по теме или запрещённое действие)

ESCALATION_TEXT = (
    "Передаю ваш вопрос специалисту поддержки — он ответит в рабочее время "
    "(будни с 9:00 до 18:00 по Москве). Пожалуйста, не отправляйте в чат "
    "СНИЛС, пароли и другие персональные данные."
)

SYSTEM_PROMPT = """Ты — бот первой линии поддержки онлайн-платформы ТренингХаб \
(обучение сотрудников по охране труда). Отвечаешь клиентам в чате.

Правила:
1. Отвечай ТОЛЬКО на основе статей базы знаний, приведённых ниже. Не придумывай \
функции, кнопки, сроки и цифры, которых нет в статьях.
2. Если в статьях есть решение — дай понятную пошаговую инструкцию. Пиши \
дружелюбно, коротко, без канцелярита. Обращайся на «вы».
3. Ты ничего не можешь сделать в системе за клиента: не можешь сбросить попытки, \
сменить администратора, внести данные, отправить в реестр. Никогда не пиши, \
что сделал это. Если клиент просит сделать такое за него, а в статье сказано, кто \
и как это делает (например, администратор компании), — это [DECLINE]: объясни, \
к кому обратиться и что именно сделать. Специалисту поддержки такие просьбы НЕ передавай.
4. Никогда не проси прислать в чат СНИЛС, пароли, номера документов и другие \
персональные данные.
5. Передавай вопрос специалисту ([ESCALATE]) только в трёх случаях:
   а) вопрос про ТренингХаб, но в статьях нет прямого ответа на него. Статьи \
могут быть найдены по ошибке и говорить о другом — проверь, отвечают ли они \
именно на этот вопрос. Никогда не утверждай, что какой-то функции, интеграции \
или возможности НЕТ, если об этом прямо не сказано в статье: отсутствие \
упоминания не значит отсутствие функции;
   б) в статье в разделе «Когда писать в поддержку» есть условия, и из слов \
клиента видно, что они уже выполнены. Сравни сроки: например, если в статье \
«больше 5 рабочих дней», а клиент пишет «неделю назад» — условие выполнено, \
передавай. Если срок ещё не прошёл — отвечай сам и назови срок из статьи;
   в) клиент раздражён и пишет без конкретики, так что непонятно, в чём проблема.
   Если клиент пишет, что пробовал несколько раз, но описывает конкретную \
проблему, у которой в статье есть решение, — отвечай сам ([ANSWER]).
   Клиент уже пишет в поддержку: никогда не отвечай «напишите в поддержку» или \
«напишите нам». Если по статье нужно обратиться в поддержку — это [ESCALATE].
6. Если вопрос не относится к ТренингХаб — вежливо откажи и скажи, с чем можешь помочь.

Формат ответа: первая строка — ровно одна метка решения:
[ANSWER] — ты отвечаешь сам;
[ESCALATE] — передаёшь специалисту;
[DECLINE] — вопрос не по теме или просьба сделать что-то за клиента (правило 3).
Со второй строки — текст для клиента. Для [ESCALATE] напиши одну короткую фразу \
с сочувствием, без обещаний сроков: стандартный текст о передаче добавится сам."""

NO_CONTEXT_NOTE = (
    "В базе знаний не найдено статей по этому вопросу. "
    "Если вопрос про ТренингХаб — передай его специалисту ([ESCALATE]). "
    "Если вопрос не про ТренингХаб — вежливо откажи ([DECLINE])."
)

_LABELS = {"[ANSWER]": ANSWER, "[ESCALATE]": ESCALATE, "[DECLINE]": DECLINE}


@dataclass
class BotAnswer:
    text: str                     # что увидит клиент
    action: str                   # answer / escalate / decline
    articles: list[str] = field(default_factory=list)  # на какие статьи опирался
    top_score: float = 0.0        # похожесть лучшего найденного фрагмента


def _pick_articles(question: str) -> tuple[list[str], float]:
    """Ищет фрагменты и возвращает до MAX_ARTICLES разных статей, от лучшей к худшей.

    Если вопрос по смыслу ни на что в базе не похож (погода, посторонние темы),
    статьи не отдаются вовсе — модель сама решит: отказ или эскалация.
    """
    top_score = best_semantic_score(question)
    if top_score < config.MIN_SCORE:
        return [], top_score

    articles = []
    for item in search(question, top_k=config.SEARCH_TOP_K):
        if item.article not in articles:
            articles.append(item.article)
        if len(articles) == config.MAX_ARTICLES:
            break
    return articles, top_score


def _articles_text(articles: list[str]) -> str:
    """Подставляет статьи целиком: в одном фрагменте может не быть всего решения."""
    parts = []
    for slug in articles:
        meta, body = parse_article(config.KNOWLEDGE_BASE_DIR / f"{slug}.md")
        parts.append(f"=== Статья: {meta.get('title', slug)} ===\n{body}")
    return "\n\n".join(parts)


def _parse(raw: str) -> tuple[str, str]:
    """Отделяет метку решения от текста. Нет понятной метки — эскалация (безопасный вариант)."""
    match = re.match(r"\s*(\[(?:ANSWER|ESCALATE|DECLINE)\])\s*(.*)", raw, re.DOTALL)
    if not match:
        return ESCALATE, ""
    return _LABELS[match.group(1)], match.group(2).strip()


def answer(question: str) -> BotAnswer:
    articles, top_score = _pick_articles(question)

    if articles:
        context = "Статьи базы знаний:\n\n" + _articles_text(articles)
    else:
        context = NO_CONTEXT_NOTE

    raw = complete(SYSTEM_PROMPT, f"{context}\n\nВопрос клиента:\n{question}")
    action, text = _parse(raw)

    if action == ESCALATE:
        # Своими словами модель может пообещать лишнее — даём стандартный текст,
        # а её пояснение (если есть) ставим перед ним
        text = f"{text}\n\n{ESCALATION_TEXT}" if text else ESCALATION_TEXT

    return BotAnswer(text=text, action=action, articles=articles, top_score=top_score)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "нажимаю отправить в реестр, а ничего не происходит"
    result = answer(question)
    print(f"Вопрос: {question}")
    print(f"Решение: {result.action}  |  статьи: {result.articles}  |  лучший score: {result.top_score}")
    print("-" * 60)
    print(result.text)
