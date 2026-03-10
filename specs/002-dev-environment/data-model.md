# Модель данных: 002-dev-environment (Docker-Only)

**Дата**: 2026-03-10  
**Ветка**: `002-dev-environment`

## Обзор

Изменения не добавляют новые таблицы в PostgreSQL.  
Фича меняет orchestration и контракт запуска через Docker Compose.

## Runtime-сущности (инфраструктурный уровень)

### `postgres` service

| Поле | Значение (dev) | Значение (prod) |
|------|----------------|-----------------|
| `POSTGRES_DB` | `luna_dev_db` | `luna_db` |
| `healthcheck` | `pg_isready -U luna -d luna_dev_db` | `pg_isready -U luna -d luna_db` |

### `migrate` service

| Поле | Значение |
|------|----------|
| Роль | Одноразовый запуск Alembic миграций |
| Команда | `alembic upgrade head` |
| Зависимость | `depends_on: postgres (service_healthy)` |
| Результат | `exit 0` как условие старта `app` |

### `app` service

| Поле | Значение |
|------|----------|
| Зависимость | `depends_on: migrate (service_completed_successfully)` |
| Dev режим | polling + hot reload |
| Prod режим | webhook |

## Settings-контракт (приложение)

| Поле | Тип | Описание |
|------|-----|----------|
| `APP_ENV` | enum(`dev`, `prod`) | Определяет режим polling/webhook |
| `WEBHOOK_URL` | string \| null | Игнорируется в dev, обязателен в prod |

## Миграции БД

- Изменений схемы БД нет.
- Миграции выполняются автоматически в orchestration-слое (`migrate` сервис), а не вручную из `app`.
