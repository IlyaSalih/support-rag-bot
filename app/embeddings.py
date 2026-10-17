"""Локальные эмбеддинги через fastembed.

Модель скачивается один раз в data/models/ и дальше работает без интернета.
"""

from functools import lru_cache

from fastembed import TextEmbedding

from app import config


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    """Загружает модель один раз за время работы программы."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(
        model_name=config.EMBEDDINGS_MODEL,
        cache_dir=str(config.MODELS_DIR),
    )


# Сколько фрагментов считать за один проход. По умолчанию fastembed берёт 256 —
# для модели ~1 ГБ это несколько ГБ памяти разом, и в контейнере процесс
# убивал OOM killer (exit 137). Небольшие пачки почти не медленнее, а пик памяти
# в разы ниже
BATCH_SIZE = 16


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Эмбеддинги для списка текстов (фрагментов базы знаний)."""
    return [vector.tolist() for vector in _model().embed(texts, batch_size=BATCH_SIZE)]


def embed_query(text: str) -> list[float]:
    """Эмбеддинг для одного вопроса клиента."""
    return embed_texts([text])[0]
