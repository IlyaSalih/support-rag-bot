"""Журнал диалогов бота: logs/dialogs.jsonl, одна строка — одно событие.

Журнал нужен для того, ради чего в поддержке вообще разбирают диалоги бота:
находить неверные и неполные ответы, повторяющиеся вопросы и дыры в базе знаний.

Персональные данные в журнал не пишутся: номера, похожие на СНИЛС, телефоны
и email маскируются до записи.
"""

import json
import re
from datetime import datetime, timezone

from app import config

_SNILS = re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}[- ]?\d{2}\b")
_PHONE = re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Адреса самой платформы (рассылка, поддержка) — не персональные данные
_OWN_DOMAIN = "@traininghub.example"


def _mask_email(match: re.Match) -> str:
    email = match.group(0)
    return email if email.lower().endswith(_OWN_DOMAIN) else "[EMAIL]"


def has_personal_data(text: str) -> bool:
    """Есть ли в тексте СНИЛС или телефон — то, что клиенту не стоит слать в чат."""
    return bool(_PHONE.search(text) or _SNILS.search(text))


def mask_personal_data(text: str) -> str:
    """Заменяет СНИЛС, телефоны и email клиентов на заглушки."""
    # Сначала телефоны: 11-значный номер на 8 иначе подошёл бы под шаблон СНИЛС
    text = _PHONE.sub("[ТЕЛЕФОН]", text)
    text = _SNILS.sub("[СНИЛС]", text)
    return _EMAIL.sub(_mask_email, text)


def write(event: str, user_id: int, **fields) -> None:
    """Добавляет запись в журнал. Ошибка записи не должна ронять бота."""
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "user": user_id,
    }
    for key, value in fields.items():
        record[key] = mask_personal_data(value) if isinstance(value, str) else value
    try:
        config.LOGS_DIR.mkdir(exist_ok=True)
        with config.DIALOG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"Не удалось записать журнал: {exc}")
