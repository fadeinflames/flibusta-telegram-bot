FROM python:3.12-slim AS base

ENV PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /srv

# Системные зависимости (ffmpeg для ужатия аудио под лимит Telegram, aria2 для торрентов)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg aria2 \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python — тяжёлые пакеты в отдельном слое для лучшего кэширования
COPY requirements.txt /srv/
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# Директории для данных
RUN mkdir -p /srv/books /srv/logs /srv/data /srv/downloads

# Исходный код
COPY src ./src
COPY api ./api

VOLUME ["/srv/books", "/srv/logs", "/srv/data", "/srv/downloads"]


# ── Stage: frontend build ──
FROM node:20-alpine AS frontend

ARG VITE_BOT_USERNAME
ENV VITE_BOT_USERNAME=${VITE_BOT_USERNAME}

WORKDIR /build
COPY web/package.json web/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY web/ ./
RUN npm run build


# ── Stage: bot (default) ──
FROM base AS bot
CMD ["python", "src/srv.py"]


# ── Stage: web API ──
FROM base AS web
COPY --from=frontend /build/dist /srv/web/dist
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
