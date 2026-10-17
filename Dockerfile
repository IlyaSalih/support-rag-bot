# Образ Telegram-бота поддержки ТренингХаб
#
# Сборка:   docker build -t support-rag-bot .
# Запуск:   docker compose up -d   (см. docker-compose.yml)

FROM python:3.12-slim

# Не создавать .pyc и не буферизовать вывод — логи сразу видны в docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Корневые сертификаты Минцифры: без них API GigaChat не проходит проверку SSL.
# Сертификаты публичные, лежат в репозитории в certs/
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Отдельный пользователь вместо root. uid 1000 совпадает с обычным
# пользователем на хосте, поэтому тома data/ и logs/ доступны на запись
RUN useradd --create-home --uid 1000 bot
WORKDIR /app

# Зависимости ставим отдельным слоем до копирования кода:
# при правке кода этот долгий шаг берётся из кеша
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ app/
COPY knowledge_base/ knowledge_base/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p data logs && chown -R bot:bot /app

USER bot

# Путь к сертификатам внутри контейнера — общий системный файл
ENV GIGACHAT_CA_BUNDLE_FILE=/etc/ssl/certs/ca-certificates.crt

ENTRYPOINT ["/entrypoint.sh"]
