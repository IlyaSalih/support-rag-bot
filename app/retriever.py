"""Гибридный поиск по базе знаний: по смыслу (эмбеддинги) + по словам (BM25).

Два списка результатов объединяются методом Reciprocal Rank Fusion (RRF):
фрагмент получает баллы за высокое место в каждом из списков. Так находится
и перефразированный вопрос («неужели каждого руками вбивать»), и вопрос
с конкретными словами («пишет недостаточно прав»).

Проверка из корня проекта:
    python -m app.retriever "нажимаю отправить в реестр, а ничего не происходит"
"""

import sys
from dataclasses import dataclass
from functools import lru_cache

import chromadb
import numpy as np

from app import config
from app.embeddings import embed_query
from app.lexical import build as build_bm25

RRF_K = 60  # стандартная константа RRF: сглаживает разницу между верхними местами


@dataclass
class Found:
    text: str
    article: str
    title: str
    heading: str
    score: float       # похожесть по смыслу, от 0 до 1 (для порога «ответа нет»)
    bm25: float = 0.0  # балл поиска по словам (0 — слова не совпали)


@lru_cache(maxsize=1)
def _corpus():
    """Загружает все фрагменты с векторами из Chroma один раз.

    Фрагментов около 200, поэтому сравнение со всеми сразу через numpy
    быстрее и проще, чем отдельный запрос к базе на каждый способ поиска.
    """
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        collection = client.get_collection(config.COLLECTION_NAME, embedding_function=None)
    except Exception as exc:
        raise RuntimeError("Индекс не найден. Сначала выполните: python -m app.ingest") from exc

    data = collection.get(include=["documents", "metadatas", "embeddings"])
    vectors = np.array(data["embeddings"], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)  # для косинусного сходства
    return data["documents"], data["metadatas"], vectors


def search(query: str, top_k: int = 4) -> list[Found]:
    """Возвращает top_k фрагментов в порядке гибридного рейтинга."""
    documents, metadatas, vectors = _corpus()

    # 1. По смыслу: косинусное сходство вопроса со всеми фрагментами
    q = np.array(embed_query(query), dtype=np.float32)
    semantic = vectors @ (q / np.linalg.norm(q))

    # 2. По словам: BM25
    lexical = np.array(build_bm25(tuple(documents)).scores(query))

    # 3. Объединение рейтингов (RRF). Фрагменты без совпадения слов
    #    в рейтинг BM25 не попадают — иначе они получали бы баллы за «место»
    fused = np.zeros(len(documents))
    for rank, idx in enumerate(np.argsort(-semantic), 1):
        fused[idx] += 1 / (RRF_K + rank)
    for rank, idx in enumerate(np.argsort(-lexical), 1):
        if lexical[idx] > 0:
            fused[idx] += 1 / (RRF_K + rank)

    found = []
    for idx in np.argsort(-fused)[:top_k]:
        meta = metadatas[idx]
        found.append(
            Found(
                text=documents[idx],
                article=meta["article"],
                title=meta["title"],
                heading=meta["heading"],
                score=round(float(semantic[idx]), 3),
                bm25=round(float(lexical[idx]), 2),
            )
        )
    return found


def best_semantic_score(query: str) -> float:
    """Максимальная похожесть по смыслу среди всех фрагментов."""
    _, _, vectors = _corpus()
    q = np.array(embed_query(query), dtype=np.float32)
    return round(float((vectors @ (q / np.linalg.norm(q))).max()), 3)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "нажимаю отправить в реестр, а ничего не происходит"
    print(f"Вопрос: {question}\n")
    for item in search(question, top_k=6):
        print(f"смысл {item.score:.3f}  слова {item.bm25:5.2f}  {item.article}  →  {item.heading}")
