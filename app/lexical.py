"""Поиск по словам (BM25) — вторая половина гибридного поиска.

Поиск по смыслу (эмбеддинги) хорошо понимает перефразировки, но может
промахнуться, когда клиент пишет конкретные слова: «csv», «недостаточно прав».
BM25 — классический поиск по совпадению слов, как в поисковиках до нейросетей.
Слова приводятся к основе стеммером, чтобы «администратора» совпало
с «администратор».
"""

import math
import re
from collections import Counter
from functools import lru_cache

from py_rust_stemmers import SnowballStemmer

# Частые слова, которые ничего не говорят о теме вопроса
STOPWORDS = {
    "а", "без", "бы", "в", "во", "вот", "все", "всё", "вы", "где", "да", "для",
    "до", "его", "ее", "её", "если", "есть", "еще", "ещё", "же", "за", "и", "из",
    "или", "их", "к", "как", "когда", "ли", "либо", "мне", "мы", "на", "над",
    "не", "нет", "ни", "но", "ну", "о", "об", "он", "она", "они", "от", "по",
    "под", "при", "с", "со", "так", "также", "то", "только", "у", "уже", "чем",
    "что", "чтобы", "это", "эта", "этот", "я", "можно", "нужно", "пожалуйста",
    "добрый", "день", "здравствуйте",
}

_stemmer = SnowballStemmer("russian")


def tokenize(text: str) -> list[str]:
    """Слова в нижнем регистре, без стоп-слов, приведённые к основе."""
    words = re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е"))
    return [_stemmer.stem_word(w) for w in words if w not in STOPWORDS and len(w) > 1]


class BM25:
    """Минимальная реализация BM25 Okapi (k1=1.5, b=0.75)."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.docs), 1)
        df = Counter(term for d in self.docs for term in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        result = []
        for doc, length in zip(self.docs, self.lengths):
            score = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * length / self.avg_len)
                    score += self.idf[t] * tf * (self.k1 + 1) / norm
            result.append(score)
        return result


@lru_cache(maxsize=1)
def build(documents: tuple[str, ...]) -> BM25:
    """Индекс строится один раз за время работы программы (документов ~200)."""
    return BM25(list(documents))
