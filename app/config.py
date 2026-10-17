"""Настройки проекта.

Все значения берутся из переменных окружения (файл .env в корне проекта).
Пути к папкам вычисляются от корня проекта, поэтому скрипты работают
независимо от того, из какой папки их запустили.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта: папка на уровень выше app/
BASE_DIR = Path(__file__).resolve().parent.parent

# Явно указываем путь к .env (без автопоиска — он ненадёжен)
load_dotenv(BASE_DIR / ".env")

# --- Папки ---
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"   # векторная база
MODELS_DIR = DATA_DIR / "models"   # кеш локальной модели эмбеддингов

# --- Векторная база ---
COLLECTION_NAME = "knowledge_base"

# --- Поиск ---
# Сколько фрагментов искать и сколько статей целиком отдавать модели
SEARCH_TOP_K = 12
MAX_ARTICLES = 3
# Порог похожести: если лучший фрагмент ниже, считаем, что в базе ответа нет.
# Зависит от модели эмбеддингов! Для paraphrase-multilingual-mpnet-base-v2:
# релевантное ~0.42–0.85, явно постороннее ~0.2. Порог низкий сознательно:
# лишнюю статью отсеет модель (правило 5а в answer.py), а пропущенную — никто.
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.40"))

# --- Эмбеддинги (локально, fastembed) ---
EMBEDDINGS_MODEL = os.getenv(
    "EMBEDDINGS_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

# --- GigaChat (генерация ответов) ---
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
GIGACHAT_CA_BUNDLE_FILE = os.getenv(
    "GIGACHAT_CA_BUNDLE_FILE", "/etc/ssl/certs/ca-certificates.crt"
)


def require(name: str, value: str) -> str:
    """Проверяет, что обязательная настройка заполнена, иначе понятная ошибка."""
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. Добавьте её в файл .env"
        )
    return value
