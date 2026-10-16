"""Поиск фрагментов базы знаний, похожих по смыслу на вопрос клиента.

Проверка из корня проекта:
    python -m app.retriever "нажимаю отправить в реестр, а ничего не происходит"
"""

import sys
from dataclasses import dataclass
from functools import lru_cache

import chromadb

from app import config
from app.embeddings import embed_query


@dataclass
class Found:
    text: str
    article: str
    title: str
    heading: str
    score: float  # похожесть от 0 до 1: чем больше, тем ближе к вопросу


@lru_cache(maxsize=1)
def _collection():
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        return client.get_collection(config.COLLECTION_NAME, embedding_function=None)
    except Exception as exc:
        raise RuntimeError(
            "Индекс не найден. Сначала выполните: python -m app.ingest"
        ) from exc


def search(query: str, top_k: int = 4) -> list[Found]:
    """Возвращает top_k самых похожих фрагментов, от лучшего к худшему."""
    result = _collection().query(
        query_embeddings=[embed_query(query)],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    found = []
    for text, meta, distance in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        found.append(
            Found(
                text=text,
                article=meta["article"],
                title=meta["title"],
                heading=meta["heading"],
                score=round(1 - distance, 3),  # косинусное расстояние → похожесть
            )
        )
    return found


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "нажимаю отправить в реестр, а ничего не происходит"
    print(f"Вопрос: {question}\n")
    for item in search(question):
        print(f"{item.score:.3f}  {item.article}  →  {item.heading}")
