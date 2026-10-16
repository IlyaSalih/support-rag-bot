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


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Эмбеддинги для списка текстов (фрагментов базы знаний)."""
    return [vector.tolist() for vector in _model().embed(texts)]


def embed_query(text: str) -> list[float]:
    """Эмбеддинг для одного вопроса клиента."""
    return embed_texts([text])[0]
