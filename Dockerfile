FROM python:3.12-slim

ENV PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Системные зависимости (ffmpeg для конвертации HLS → MP3)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python
COPY requirements.txt /srv/
RUN pip install --no-cache-dir -r requirements.txt

# Директории для данных
RUN mkdir -p /srv/books /srv/logs /srv/data

# Исходный код
COPY src ./src

VOLUME ["/srv/books", "/srv/logs", "/srv/data"]

CMD ["python", "src/srv.py"]
