FROM python:3.11-slim

# Системные зависимости для psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала копируем только зависимости — чтобы кэш Docker не инвалидировался
# при каждом изменении кода.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код проекта.
COPY . .

# Создаём папку для загруженных файлов.
RUN mkdir -p /app/uploads

EXPOSE 8000

# Команда по умолчанию: запускаем uvicorn.
# В docker-compose переопределяем для применения миграций перед стартом.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
