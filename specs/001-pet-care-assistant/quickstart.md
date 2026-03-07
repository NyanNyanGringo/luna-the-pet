# Быстрый старт: Luna the Dog

## Требования

- Python 3.11+
- Node.js 20+ (для frontend)
- Docker + Docker Compose
- PostgreSQL 16 (или через Docker)
- ffmpeg (для обработки голосовых сообщений)

## Переменные окружения

Создать `.env` в корне проекта:

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
WEBHOOK_URL=https://luna.example.com/webhook
WEBHOOK_SECRET=random-secret-string

# OpenAI (API key = fallback, OAuth = primary)
OPENAI_API_KEY=sk-...
OPENAI_OAUTH_CLIENT_ID=...
OAUTH_ENCRYPTION_KEY=...  # Fernet key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Database
DATABASE_URL=postgresql+asyncpg://luna:password@localhost:5432/luna_db

# JWT
JWT_SECRET=random-jwt-secret

# App
DEBUG=true
MEDIA_DIR=/data/uploads
```

## Локальная разработка

### 1. Backend

```bash
# Клонировать и перейти в директорию
git clone https://github.com/user/luna-the-dog.git
cd luna-the-dog

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Поднять PostgreSQL (если нет локально)
docker compose up -d postgres

# Применить миграции
alembic upgrade head

# Запустить сервер (long-polling для разработки)
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev    # Vite dev server на :5173
```

### 3. Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

## Docker Compose (продакшн)

```bash
# Скопировать .env и настроить
cp .env.example .env

# Запустить
docker compose up -d

# Проверить логи
docker compose logs -f app
```

### docker-compose.yml (ожидаемая структура)

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - media_data:/data/uploads
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: luna
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: luna_db
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: pg_isready -U luna
      interval: 5s
      retries: 5

volumes:
  pg_data:
  media_data:
```

## Тестирование

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=app --cov-report=html

# Только юнит-тесты
pytest tests/unit/

# Линтинг
ruff check .
ruff format --check .
mypy app/
```

## Структура команд разработки

| Команда | Описание |
|---------|----------|
| `uvicorn backend.app.main:app --reload` | Dev-сервер |
| `alembic upgrade head` | Применить миграции |
| `alembic revision --autogenerate -m "описание"` | Создать миграцию |
| `pytest` | Запуск тестов |
| `ruff check . --fix` | Линтер с автофиксом |
| `ruff format .` | Форматирование |
| `mypy app/` | Проверка типов |
| `docker compose up -d` | Запуск продакшна |
| `docker compose logs -f app` | Логи приложения |
