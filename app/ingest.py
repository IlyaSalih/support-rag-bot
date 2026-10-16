"""Индексация базы знаний.

Читает статьи из knowledge_base/, режет на фрагменты по заголовкам «##»,
считает эмбеддинги и сохраняет всё в векторную базу Chroma (data/chroma/).

Запуск из корня проекта:
    python -m app.ingest

Перезапускать после любого изменения статей: индекс собирается заново целиком.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
import yaml

from app import config
from app.embeddings import embed_texts


@dataclass
class Chunk:
    id: str        # уникальный id фрагмента, например "15-registry-export-errors#2"
    text: str      # текст, по которому идёт поиск и который увидит LLM
    article: str   # имя файла статьи без .md
    title: str     # заголовок статьи
    section: str   # раздел базы знаний (Доступ, Реестр...)
    heading: str   # подзаголовок фрагмента внутри статьи


def parse_article(path: Path) -> tuple[dict, str]:
    """Отделяет метаданные (блок между ---) от текста статьи."""
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        raise ValueError(f"{path.name}: нет блока метаданных между ---")
    meta = yaml.safe_load(match.group(1)) or {}
    return meta, match.group(2).strip()


def split_into_chunks(path: Path) -> list[Chunk]:
    """Режет статью на фрагменты по заголовкам второго уровня (##).

    Текст до первого «##» (вступление статьи) — отдельный фрагмент.
    К каждому фрагменту приклеивается заголовок статьи и теги: без них
    кусок вроде «Проверьте по порядку» теряет смысл и хуже находится.
    """
    meta, body = parse_article(path)
    article = path.stem
    title = meta.get("title", article)
    section = meta.get("section", "")
    tags = ", ".join(meta.get("tags", []))

    # Убираем заголовок первого уровня — он и так есть в метаданных
    body = re.sub(r"^# .*\n?", "", body, count=1).strip()

    # Делим по строкам, начинающимся с «## »
    parts = re.split(r"^## ", body, flags=re.MULTILINE)

    chunks = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if i == 0:
            heading, content = "Вступление", part
        else:
            heading, _, content = part.partition("\n")
            heading, content = heading.strip(), content.strip()
        if not content:
            continue

        text = f"{title}. {heading}\n{content}\nТеги: {tags}"
        chunks.append(
            Chunk(
                id=f"{article}#{i}",
                text=text,
                article=article,
                title=title,
                section=section,
                heading=heading,
            )
        )
    return chunks


def load_chunks() -> list[Chunk]:
    """Собирает фрагменты из всех статей базы знаний."""
    files = sorted(config.KNOWLEDGE_BASE_DIR.glob("*.md"))
    if not files:
        raise RuntimeError(f"В {config.KNOWLEDGE_BASE_DIR} нет статей (*.md)")
    chunks = []
    for path in files:
        chunks.extend(split_into_chunks(path))
    return chunks


def build_index(chunks: list[Chunk]) -> None:
    """Пересоздаёт коллекцию в Chroma и загружает в неё фрагменты."""
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))

    # Индекс собираем с нуля, чтобы удалённые статьи не оставались в базе
    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass  # коллекции ещё нет — это нормально при первом запуске

    collection = client.create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=None,  # эмбеддинги считаем сами (локально)
        metadata={"hnsw:space": "cosine"},  # сходство по косинусу
    )
    collection.add(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=embed_texts([c.text for c in chunks]),
        metadatas=[
            {
                "article": c.article,
                "title": c.title,
                "section": c.section,
                "heading": c.heading,
            }
            for c in chunks
        ],
    )


def main() -> None:
    chunks = load_chunks()
    articles = len({c.article for c in chunks})
    print(f"Статей: {articles}, фрагментов: {len(chunks)}")
    print("Считаю эмбеддинги и сохраняю индекс...")
    build_index(chunks)
    print(f"Готово. Индекс сохранён в {config.CHROMA_DIR}")


if __name__ == "__main__":
    main()
