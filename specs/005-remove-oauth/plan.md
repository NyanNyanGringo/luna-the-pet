# Implementation Plan: Удаление функционала OAuth

**Branch**: `005-remove-oauth` | **Date**: 2026-03-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-remove-oauth/spec.md`

## Summary

Полное удаление OAuth-авторизации через OpenAI из кодовой базы. Бот переходит исключительно на работу через `OPENAI_API_KEY`. Операция затрагивает: OAuth-сервис, OAuth-эндпоинт, Telegram-команду `/connectai`, модель `OAuthCredential`, таблицу в БД, конфигурацию и зависимости. JWT Bearer-аутентификация для веб-API сохраняется без изменений.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, OpenAI SDK, python-jose
**Storage**: PostgreSQL 16 (asyncpg), Alembic для миграций
**Testing**: pytest
**Target Platform**: Ubuntu VDS (Docker Compose)
**Project Type**: Web-service (Telegram-бот + REST API)
**Performance Goals**: Нагрузка одной семьи (<10 пользователей)
**Constraints**: 2 CPU, 4 ГБ RAM VDS
**Scale/Scope**: ~15 файлов затронуты удалением

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Статус | Комментарий |
|---------|--------|-------------|
| I. Открытый исходный код | ✅ Проходит | Удаление OAuth не влияет на открытость |
| II. Голос как приоритет | ✅ Проходит | Голосовой ввод не затронут |
| III. База знаний о питомцах | ✅ Проходит | Данные питомцев не затронуты |
| IV. Проактивный уход | ✅ Проходит | Напоминания не затронуты |
| V. Архитектура агента | ✅ Проходит | Агент продолжает работать через API-ключ — единственное изменение в способе инстанцирования OpenAI-клиента |
| VI. Простота для семьи | ✅ Проходит | Упрощение: больше не нужен OAuth-поток для пользователей |
| VII. Самохостинг | ✅ Проходит | Уменьшение зависимостей упрощает развёртывание |

**Результат**: все принципы конституции соблюдены. Удаление OAuth упрощает систему (принцип VI).

## Project Structure

### Documentation (this feature)

```text
specs/005-remove-oauth/
├── plan.md              # Этот файл
├── research.md          # Исследование зависимостей и связей
├── data-model.md        # Изменения модели данных (удаление)
├── quickstart.md        # Порядок реализации
└── tasks.md             # Задачи (создаётся /speckit.tasks)
```

### Source Code (затронутые файлы)

```text
backend/
├── app/
│   ├── main.py                          # Удалить auth_router import и registration
│   ├── config.py                        # Удалить OPENAI_OAUTH_CLIENT_ID, OAUTH_ENCRYPTION_KEY
│   ├── api/
│   │   ├── auth.py                      # УДАЛИТЬ ЦЕЛИКОМ (только OAuth-эндпоинт)
│   │   └── deps.py                      # НЕ ТРОГАТЬ (JWT-авторизация)
│   ├── bot/
│   │   └── handlers/
│   │       └── commands.py              # Удалить /connectai обработчик
│   ├── db/
│   │   └── models/
│   │       └── family.py                # Удалить OAuthCredential, оставить ConversationState
│   ├── services/
│   │   └── openai_auth_service.py       # УДАЛИТЬ ЦЕЛИКОМ
│   └── agent/
│       └── brain.py                     # Упростить get_openai_client → прямой API-ключ
├── alembic/
│   └── versions/
│       └── XXXX_drop_oauth_credential.py  # НОВАЯ миграция
├── tests/
│   └── unit/
│       ├── test_openai_auth.py          # УДАЛИТЬ ЦЕЛИКОМ
│       ├── conftest.py                  # Убрать OAuth env vars
│       └── test_config.py              # Убрать OAuth-тесты
├── requirements.txt                     # Удалить cryptography, httpx
├── .env.example                         # Удалить OAuth-строки
```

**Structure Decision**: Существующая структура backend/ сохраняется. Изменения — удаление файлов и строк, без добавления новых модулей.

## Complexity Tracking

> Нарушений конституции нет. Таблица не заполняется.
