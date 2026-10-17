"""Telegram-бот поддержки ТренингХаб.

Запуск из корня проекта:
    python -m app.bot

Что умеет:
  * отвечает на вопросы по базе знаний (app/answer.py);
  * под каждым ответом кнопки «Помогло» / «Не помогло»;
  * «Не помогло» и эскалации пересылаются в чат операторов (если задан
    OPERATORS_CHAT_ID в .env);
  * всё пишется в журнал logs/dialogs.jsonl с маскировкой персональных данных.

Работает через long polling: бот сам опрашивает сервера Telegram,
поэтому ему не нужны внешний IP и открытые порты.
"""

import asyncio
import logging
import re
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app import config, dialog_log
from app.answer import ESCALATE, answer
from app.retriever import best_semantic_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

WELCOME = (
    "Здравствуйте! Я бот поддержки ТренингХаб.\n\n"
    "Помогу со входом, сотрудниками, курсами, тестами, документами, "
    "отправкой в реестр и тарифом. Просто опишите проблему своими словами.\n\n"
    "Пожалуйста, не отправляйте в чат СНИЛС, пароли и другие персональные данные.\n\n"
    "Это учебный проект: продукт и компания вымышлены."
)
HELP = (
    "Примеры вопросов:\n"
    "• Как загрузить сотрудников из Excel?\n"
    "• Нажимаю «Отправить в реестр», а ничего не происходит\n"
    "• Сотрудник не видит назначенный курс\n\n"
    "Если я не смогу помочь, передам вопрос специалисту."
)
ERROR_TEXT = (
    "Извините, у меня временная техническая проблема. "
    "Попробуйте ещё раз через минуту — или напишите на support@traininghub.example."
)
PERSONAL_DATA_WARNING = (
    "⚠️ Пожалуйста, не отправляйте в чат СНИЛС, телефоны и другие персональные данные. "
    "Вносите их только в карточку сотрудника в личном кабинете: "
    "раздел «Сотрудники» → карточка сотрудника."
)
TELEGRAM_LIMIT = 4096

dp = Dispatcher()
# Ответы, ожидающие оценки: id ответа → данные для журнала и пересылки.
# Хранятся в памяти: после перезапуска бота старые кнопки просто перестанут работать
_pending: dict[str, dict] = {}


def to_plain(text: str) -> str:
    """Убирает markdown-разметку модели: Telegram показал бы её звёздочками."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    return text[:TELEGRAM_LIMIT]


def feedback_keyboard(answer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👍 Помогло", callback_data=f"ok:{answer_id}"),
        InlineKeyboardButton(text="👎 Не помогло", callback_data=f"no:{answer_id}"),
    ]])


async def notify_operators(bot: Bot, header: str, question: str, details: str = "") -> None:
    """Пересылает обращение в чат операторов. Персональные данные маскируются."""
    if not config.OPERATORS_CHAT_ID:
        return
    text = f"{header}\n\nВопрос клиента:\n{dialog_log.mask_personal_data(question)}"
    if details:
        text += f"\n\n{details}"
    try:
        await bot.send_message(config.OPERATORS_CHAT_ID, text[:TELEGRAM_LIMIT])
    except Exception as exc:  # чат операторов недоступен — клиент не должен это заметить
        log.warning("Не удалось отправить операторам: %s", exc)


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(WELCOME)


@dp.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP)


@dp.message(Command("chatid"))
async def on_chatid(message: Message) -> None:
    """Служебная команда: показывает id чата, чтобы настроить чат операторов."""
    await message.answer(f"id этого чата: {message.chat.id}")


@dp.message(F.text)
async def on_question(message: Message, bot: Bot) -> None:
    question = message.text.strip()
    user_id = message.from_user.id if message.from_user else 0

    # Клиент прислал СНИЛС или телефон — сразу предупреждаем, до ответа по сути.
    # Это проверка кодом: от модели такое предупреждение не гарантировано
    if dialog_log.has_personal_data(question):
        await message.answer(PERSONAL_DATA_WARNING)
        dialog_log.write("personal_data_warning", user_id, question=question)

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        # answer() синхронный (поиск + запрос к GigaChat) — уводим его в отдельный
        # поток, чтобы бот в это время продолжал обслуживать других клиентов
        result = await asyncio.to_thread(answer, question)
    except Exception as exc:
        log.exception("Ошибка при ответе")
        dialog_log.write("error", user_id, question=question, error=str(exc))
        await message.answer(ERROR_TEXT)
        return

    answer_id = uuid.uuid4().hex[:12]
    dialog_log.write(
        "answer", user_id, answer_id=answer_id, question=question,
        action=result.action, articles=result.articles, top_score=result.top_score,
        guard=result.guard, answer=result.text,
    )

    if result.action == ESCALATE:
        await message.answer(to_plain(result.text))
        reason = f"Причина: защита от выдумок ({result.guard})" if result.guard else "Причина: решение бота"
        await notify_operators(
            bot, "🔔 Эскалация", question,
            f"{reason}\nСтатьи: {', '.join(result.articles) or 'не найдены'}",
        )
        return

    _pending[answer_id] = {"question": question, "answer": result.text,
                           "articles": result.articles}
    await message.answer(to_plain(result.text), reply_markup=feedback_keyboard(answer_id))


@dp.callback_query(F.data.regexp(r"^(ok|no):"))
async def on_feedback(callback: CallbackQuery, bot: Bot) -> None:
    verdict, answer_id = callback.data.split(":", 1)
    user_id = callback.from_user.id
    item = _pending.pop(answer_id, None)

    # Убираем кнопки, чтобы ответ нельзя было оценить дважды
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    if item is None:
        await callback.answer("Эта оценка уже учтена")
        return

    dialog_log.write("feedback", user_id, answer_id=answer_id, helpful=(verdict == "ok"))

    if verdict == "ok":
        await callback.answer("Спасибо за оценку!")
        return

    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Жаль, что не помог. Передаю ваш вопрос специалисту поддержки — "
            "он ответит в рабочее время (будни с 9:00 до 18:00 по Москве)."
        )
    await notify_operators(
        bot, "👎 Ответ бота не помог", item["question"],
        f"Ответ бота:\n{item['answer']}\n\nСтатьи: {', '.join(item['articles'])}",
    )


async def main() -> None:
    token = config.require("TELEGRAM_BOT_TOKEN", config.TELEGRAM_BOT_TOKEN)
    log.info("Загружаю модель эмбеддингов и индекс...")
    # Прогрев: первая загрузка модели занимает секунды — пусть это будет при старте,
    # а не на первом вопросе клиента
    await asyncio.to_thread(best_semantic_score, "проверка")
    if not config.OPERATORS_CHAT_ID:
        log.warning("OPERATORS_CHAT_ID не задан: эскалации будут только в журнале")
    bot = Bot(token)
    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
