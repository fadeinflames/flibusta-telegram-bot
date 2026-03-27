FROM python:3.12-slim

ENV PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Системные зависимости (ffmpeg для конвертации HLS → MP3, aria2 для торрентов)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg aria2 \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python — тяжёлые пакеты в отдельном слое для лучшего кэширования
COPY requirements.txt /srv/
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
        pycryptodome \
    && pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# Директории для данных
RUN mkdir -p /srv/books /srv/logs /srv/data

# Исходный код
COPY src ./src

VOLUME ["/srv/books", "/srv/logs", "/srv/data"]

CMD ["python", "src/srv.py"]
