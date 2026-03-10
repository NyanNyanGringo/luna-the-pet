# Контракт: поведение при запуске приложения

**Дата**: 2026-03-10

## Матрица поведения `APP_ENV`

| APP_ENV | WEBHOOK_URL | Результат | Поведение |
|---------|-------------|-----------|-----------|
| `dev` | не задан | OK | Polling mode, DEBUG logging |
| `dev` | задан | OK | Polling mode, `WEBHOOK_URL` игнорируется, warning в логах |
| `prod` | задан | OK | Webhook mode, INFO logging |
| `prod` | не задан | ОШИБКА | Приложение не стартует (валидация Settings) |
| не задан | любой | OK | Fallback на `dev` |

## Docker orchestration контракт

### DEV (`docker-compose.dev.yml`)

1. `postgres` стартует и становится `healthy` через `pg_isready -U luna -d luna_dev_db`.
2. `migrate` выполняет `alembic upgrade head` и завершается с кодом `0`.
3. `app` стартует только после `service_completed_successfully` для `migrate`.
4. `app` запускается с `uvicorn --reload` и работает через polling.

### PROD (`docker-compose.yml`)

1. `postgres` стартует и становится `healthy` через `pg_isready -U luna -d luna_db`.
2. `migrate` выполняет `alembic upgrade head` и завершается с кодом `0`.
3. `app` стартует только после `service_completed_successfully` для `migrate`.
4. `app` работает в webhook-режиме.

## Последовательность startup/shutdown приложения

### Dev mode (polling)

1. Загрузить Settings из `.env.dev` (fallback `.env`).
2. Настроить logging: `DEBUG`.
3. `await bot.delete_webhook(drop_pending_updates=True)`.
4. `asyncio.create_task(dp.start_polling(...))`.
5. При shutdown: `dp.stop_polling()` -> cancel polling task -> `bot.session.close()`.

### Prod mode (webhook)

1. Загрузить Settings из `.env.prod` (fallback `.env`).
2. Провалидировать обязательность `WEBHOOK_URL`.
3. Настроить logging: `INFO`.
4. `await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)`.
5. При shutdown: `bot.session.close()`.
