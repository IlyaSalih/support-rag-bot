"""Диагностика поиска: на каком месте нужная статья для каждого вопроса.

Запуск из корня проекта:
    python -m eval.rank_check                # все вопросы с указанной статьёй
    python -m eval.rank_check --only q01,q10 # выборочно

Не вызывает GigaChat — только локальный поиск, поэтому быстро и бесплатно.
Показывает, помогло бы увеличение MAX_ARTICLES или поиск надо менять.
"""

import argparse
from collections import Counter

import yaml

from app import config
from app.retriever import search
from eval.run_eval import QUESTIONS_FILE


def article_ranks(question: str, top_k: int = 30) -> list[tuple[str, float]]:
    """Статьи в порядке, в котором их выдаёт поиск (по лучшему фрагменту)."""
    ranked, seen = [], set()
    for item in search(question, top_k=top_k):
        if item.article not in seen:
            seen.add(item.article)
            ranked.append((item.article, item.score))
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="id вопросов через запятую")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None

    questions = yaml.safe_load(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    stats = Counter()
    for q in questions:
        expected = q.get("article")
        if not expected or (only and q["id"] not in only):
            continue
        ranked = article_ranks(q["question"])
        place = next((i for i, (a, _) in enumerate(ranked, 1) if a == expected), None)
        score = next((s for a, s in ranked if a == expected), None)
        stats[place if place and place <= 5 else "дальше"] += 1

        mark = "OK " if place and place <= config.MAX_ARTICLES else "   "
        where = f"место {place}, score {score}" if place else "не найдена в топ-30"
        print(f"{mark}{q['id']}  {where:<26} лучшие: "
              + ", ".join(f"{a}({s})" for a, s in ranked[:3]))

    print("\nНужная статья на месте:")
    for key in (1, 2, 3, 4, 5, "дальше"):
        if stats[key]:
            print(f"  {key}: {stats[key]}")
    print(f"Сейчас модели отдаются статьи с мест 1–{config.MAX_ARTICLES}")


if __name__ == "__main__":
    main()
