# Quickstart: Docker-Only Dev/Prod

**Дата**: 2026-03-10

## Предварительные требования

- Docker + Docker Compose
- Telegram bot token для dev и prod (разные боты)
- OpenAI API key
- Публичный URL для prod webhook

## Шаг 1: Подготовка конфигурации

```bash
git clone <repo-url>
cd luna_the_dog

cp .env.dev.example .env.dev
cp .env.prod.example .env.prod
```

Заполните обязательные переменные:
- `.env.dev`: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`
- `.env.prod`: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `WEBHOOK_URL`, `WEBHOOK_SECRET`

## Шаг 2: Проверка compose-конфигурации

```bash
docker compose -f docker-compose.dev.yml config
docker compose config
```

## Шаг 3: DEV запуск (foreground)

```bash
docker compose -f docker-compose.dev.yml up
```

Ожидаемое поведение:
- `postgres` проходит healthcheck с `-d luna_dev_db`
- `migrate` выполняет `alembic upgrade head` и завершается с кодом `0`
- `app` стартует после `migrate` в polling-режиме с hot reload
- логи `postgres` и `app` отображаются в текущем терминале

## Шаг 4: DEV запуск в фоне (опционально)

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml logs -f app
```

## Шаг 5: PROD запуск

```bash
docker compose up -d
docker compose logs -f app
```

Ожидаемое поведение:
- `postgres` проходит healthcheck с `-d luna_db`
- `migrate` выполняется до старта `app`
- `app` работает в webhook-режиме (`APP_ENV=prod`)

## Проверка startup-поведения

- Dev: polling, `WEBHOOK_URL` игнорируется даже если случайно задан
- Prod: webhook, старт невозможен без `WEBHOOK_URL`
- Ручной шаг `docker compose exec app alembic upgrade head` не требуется
