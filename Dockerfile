FROM python:3.12-slim

# Устанавливаем переменные окружения
ENV PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Устанавливаем рабочую директорию
WORKDIR /srv

# Устанавливаем системные зависимости (если нужны для lxml и других библиотек)
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями
COPY requirements.txt /srv/

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

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
