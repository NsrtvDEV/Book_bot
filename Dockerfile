FROM python:3.13-slim

# Системные зависимости (libpq нужен для psycopg/asyncpg, gcc — для сборки колёс)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Сначала только файлы зависимостей — для кэширования слоя
COPY pyproject.toml uv.lock* ./

RUN uv sync --frozen --no-dev --no-install-project

# Теперь копируем остальной код
COPY . .

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Применяем миграции и запускаем бота
CMD ["sh", "-c", "alembic upgrade head && python main.py"] 