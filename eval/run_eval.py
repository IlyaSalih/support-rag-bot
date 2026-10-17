"""Прогон тестового набора через бота и подсчёт качества.

Запуск из корня проекта:
    python -m eval.run_eval                 # все вопросы
    python -m eval.run_eval --only q18,q25  # выборочно
    python -m eval.run_eval --delay 2       # пауза между запросами, сек
    python -m eval.run_eval --file holdout.yaml  # отложенный набор

Что проверяется для каждого вопроса:
  * решение бота (answer / escalate / decline) входит в допустимые;
  * в ответе есть все фрагменты из must_contain;
  * в ответе нет ни одного фрагмента из must_not_contain;
  * поиск нашёл нужную статью (отдельная метрика — качество поиска).

Отчёт сохраняется в eval/results/ (папка в .gitignore).
"""

import argparse
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from app.answer import ESCALATE, answer

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = EVAL_DIR / "questions.yaml"
RESULTS_DIR = EVAL_DIR / "results"


def normalize(text: str) -> str:
    """Нижний регистр и ё → е, чтобы проверки не спотыкались о мелочи."""
    return text.lower().replace("ё", "е")


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def check(q: dict, action: str, text: str, articles: list[str]) -> list[str]:
    """Возвращает список проблем. Пустой список — вопрос пройден."""
    problems = []
    expected = as_list(q["expected"])
    if action not in expected:
        problems.append(f"решение {action}, ожидалось {'/'.join(expected)}")

    body = normalize(text)
    # Для эскалации текст стандартный — обязательные слова не проверяем.
    # «сохран|остан» — достаточно любого из вариантов через |
    if action != ESCALATE:
        for fragment in as_list(q.get("must_contain")):
            variants = [normalize(v) for v in fragment.split("|")]
            if not any(v in body for v in variants):
                problems.append(f"нет «{fragment}»")
    for fragment in as_list(q.get("must_not_contain")):
        if normalize(fragment) in body:
            problems.append(f"лишнее «{fragment}»")
    return problems


def run(only: set[str] | None, delay: float, questions_file: Path = QUESTIONS_FILE) -> None:
    questions = yaml.safe_load(questions_file.read_text(encoding="utf-8"))["questions"]
    if only:
        questions = [q for q in questions if q["id"] in only]

    results = []
    for i, q in enumerate(questions, 1):
        try:
            res = answer(q["question"])
            action, text, articles, score = res.action, res.text, res.articles, res.top_score
            guard, raw = res.guard, res.raw
            problems = check(q, action, text, articles)
        except Exception as exc:  # ошибка API не должна ронять весь прогон
            action, text, articles, score = "error", str(exc), [], 0.0
            guard, raw = "", ""
            problems = [f"ошибка: {exc}"]

        expected_article = q.get("article")
        # Ошибки API не учитываем в метрике поиска: до поиска дело могло не дойти
        if expected_article and action != "error":
            retrieval_hit = expected_article in articles
        else:
            retrieval_hit = None

        status = "OK  " if not problems else "FAIL"
        print(f"[{i:02}/{len(questions)}] {status} {q['id']}  {action:<8}  {q['question'][:55]}")
        for p in problems:
            print(f"        - {p}")
        if guard:
            print(f"        ! защита от выдумок: {guard}")
        if retrieval_hit is False and action != "error":
            print(f"        ~ поиск не нашёл статью {expected_article}, нашёл {articles}")

        results.append({
            "id": q["id"],
            "question": q["question"],
            "expected": as_list(q["expected"]),
            "action": action,
            "passed": not problems,
            "problems": problems,
            "expected_article": expected_article,
            "found_articles": articles,
            "retrieval_hit": retrieval_hit,
            "top_score": score,
            "answer": text,
            "guard": guard,
            "raw": raw,
        })
        if delay and i < len(questions):
            time.sleep(delay)

    summarize(results, prefix=questions_file.stem)


def summarize(results: list[dict], prefix: str = "questions") -> None:
    total = len(results)
    passed = sum(r["passed"] for r in results)

    # Разбивка по основному ожидаемому решению (первому в списке)
    by_type, ok_by_type = Counter(), Counter()
    for r in results:
        kind = r["expected"][0]
        by_type[kind] += 1
        ok_by_type[kind] += r["passed"]

    with_article = [r for r in results if r["retrieval_hit"] is not None]
    hits = sum(r["retrieval_hit"] for r in with_article)

    print("\n" + "=" * 60)
    print(f"Итого пройдено: {passed}/{total} ({passed / total:.0%})")
    for kind in ("answer", "decline", "escalate"):
        if by_type[kind]:
            print(f"  {kind:<9} {ok_by_type[kind]}/{by_type[kind]}")
    if with_article:
        print(f"Поиск нашёл нужную статью: {hits}/{len(with_article)} ({hits / len(with_article):.0%})")
    guarded = sum(bool(r["guard"]) for r in results)
    if guarded:
        print(f"Защита от выдумок заменила ответ эскалацией: {guarded}")
    errors = sum(r["action"] == "error" for r in results)
    if errors:
        print(f"Ошибок API: {errors}")

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"eval_{prefix}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Подробный отчёт: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Прогон тестового набора")
    parser.add_argument("--only", help="id вопросов через запятую, например q18,q25")
    parser.add_argument("--delay", type=float, default=1.0, help="пауза между запросами, сек")
    parser.add_argument("--file", default="questions.yaml",
                        help="набор вопросов в папке eval/, например holdout.yaml")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    run(only, args.delay, EVAL_DIR / args.file)


if __name__ == "__main__":
    main()
