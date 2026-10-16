"""Клиент GigaChat: генерация ответов.

Эмбеддинги здесь не считаются — они локальные, см. app/embeddings.py.
"""

from functools import lru_cache

from gigachat import GigaChat

from app import config


@lru_cache(maxsize=1)
def _client() -> GigaChat:
    """Создаёт клиента один раз; токен доступа SDK обновляет сам."""
    return GigaChat(
        credentials=config.require(
            "GIGACHAT_CREDENTIALS", config.GIGACHAT_CREDENTIALS
        ),
        scope=config.GIGACHAT_SCOPE,
        model=config.GIGACHAT_MODEL,
        ca_bundle_file=config.GIGACHAT_CA_BUNDLE_FILE,
    )


def complete(system_prompt: str, user_message: str, temperature: float = 0.2) -> str:
    """Отправляет системную инструкцию и сообщение пользователя, возвращает ответ.

    Низкая temperature — чтобы ответы были стабильными и без фантазий.
    """
    response = _client().chat(
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
        }
    )
    return response.choices[0].message.content.strip()
