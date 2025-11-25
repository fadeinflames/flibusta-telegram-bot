FROM ubuntu:24.04

# Устанавливаем переменные окружения
ENV PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Устанавливаем рабочую директорию
WORKDIR /srv

# Устанавливаем Python и системные зависимости
RUN apt update && apt install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*

# Создаем симлинк для python
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Копируем файл с зависимостями
COPY requirements.txt /srv/

# Устанавливаем Python зависимости (используем --break-system-packages для Docker)
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Создаем директории для данных
RUN mkdir -p /srv/books /srv/logs

# Копируем исходный код
COPY src ./src

# Копируем .env файл (опционально, можно передавать через docker-compose)
# COPY .env ./

# Создаем volume для базы данных и логов
VOLUME ["/srv/books", "/srv/logs"]

# Указываем, что контейнер будет слушать (для документации)
EXPOSE 8080

# Запускаем бота
CMD ["python", "srv.py"]
