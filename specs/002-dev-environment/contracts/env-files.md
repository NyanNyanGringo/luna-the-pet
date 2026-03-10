# Контракт: файлы конфигурации окружения

**Дата**: 2026-03-10

## Структура файлов

```text
project-root/
├── .env.dev.example      # Шаблон для dev-окружения (в git)
├── .env.prod.example     # Шаблон для prod-окружения (в git)
├── .env.dev              # Реальная dev-конфигурация (gitignored)
├── .env.prod             # Реальная prod-конфигурация (gitignored)
└── .env.example          # Legacy fallback (deprecated для запуска)
```

## Правила использования

1. Docker dev использует `env_file: .env.dev` (compose: `docker-compose.dev.yml`).
2. Docker prod использует `env_file: .env.prod` (compose: `docker-compose.yml`).
3. `.env.example` не используется в основном сценарии запуска и сохраняется только для fallback-совместимости Settings.
4. Для запуска приложения не допускается сценарий, где единственным env-файлом является `.env`.

## Формат `.env.dev.example`

```env
# === Режим ===
APP_ENV=dev

# === Telegram (dev-бот) ===
TELEGRAM_BOT_TOKEN=<ваш-dev-bot-token>
# WEBHOOK_URL в dev не используется

# === OpenAI ===
OPENAI_API_KEY=sk-...

# === База данных (локальный fallback) ===
# В docker-compose.dev.yml DATABASE_URL принудительно переопределяется
# на postgres внутри docker-сети.
DATABASE_URL=postgresql+asyncpg://luna:password@localhost:5432/luna_dev_db
POSTGRES_PASSWORD=password

# === Приложение ===
DEBUG=true
MEDIA_DIR=./data/uploads
```

## Формат `.env.prod.example`

```env
# === Режим ===
APP_ENV=prod

# === Telegram (production-бот) ===
TELEGRAM_BOT_TOKEN=<ваш-prod-bot-token>
WEBHOOK_URL=https://your-domain.com/webhook
WEBHOOK_SECRET=<random-secret>

# === OpenAI ===
OPENAI_API_KEY=sk-...

# === База данных ===
DATABASE_URL=postgresql+asyncpg://luna:password@postgres:5432/luna_db
POSTGRES_PASSWORD=<strong-password>

# === JWT ===
JWT_SECRET=<random-jwt-secret>

# === Приложение ===
DEBUG=false
MEDIA_DIR=/data/uploads
```

## Правила загрузки в приложении

1. `APP_ENV` читается из системного окружения до загрузки `.env` файлов.
2. При `APP_ENV=dev` приоритетный файл: `.env.dev`.
3. При `APP_ENV=prod` приоритетный файл: `.env.prod`.
4. Если env-файл окружения не найден, Settings может использовать fallback `.env`, но это не является Docker-only happy path.
