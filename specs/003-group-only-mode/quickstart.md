# Quickstart: Групповой режим работы бота

**Branch**: `003-group-only-mode` | **Date**: 2026-03-12

## Предусловия

- Рабочее dev-окружение (Docker Compose, PostgreSQL)
- Telegram-бот зарегистрирован через BotFather
- Переменные окружения настроены (`.env`)

## Порядок реализации

### Шаг 1: Модели данных

Создать ORM-модели `Workspace`, `WorkspaceMember`, `WorkspaceSettings`. Обновить FK в `Pet` и `ConversationState`. Удалить модели `FamilyInvite`, `Family` (или пометить deprecated). Создать Alembic-миграцию.

**Файлы**: `backend/app/db/models/`
**Проверка**: `alembic upgrade head` проходит, таблицы созданы

### Шаг 2: Сервисный слой

Создать `workspace_service.py` с операциями:
- `get_or_create_workspace(session, telegram_chat_id, title)` → Workspace
- `deactivate_workspace(session, telegram_chat_id)` → None
- `reactivate_workspace(session, telegram_chat_id, title)` → Workspace
- `add_member(session, workspace_id, telegram_user_id, ...)` → WorkspaceMember
- `deactivate_member(session, workspace_id, telegram_user_id)` → None
- `get_user_workspaces(session, telegram_user_id)` → list[Workspace]
- `update_chat_id(session, old_chat_id, new_chat_id)` → None

**Файлы**: `backend/app/services/workspace_service.py`
**Проверка**: unit-тесты проходят

### Шаг 3: Обработчики групповых событий

Создать `group_events.py` с обработчиками:
- `my_chat_member` (бот добавлен / удалён)
- `chat_member` (участник вступил / покинул)
- `message(F.migrate_to_chat_id)` (миграция группы)

**Файлы**: `backend/app/bot/handlers/group_events.py`
**Проверка**: unit-тесты с мок-событиями

### Шаг 4: Маршрутизация private vs group

Разделить роутеры на private и group. Private-роутер: отклонение с инструкцией. Group-роутер: маршрутизация через workspace.

**Файлы**: `backend/app/bot/handlers/start.py`, `message.py`, `create.py`
**Проверка**: сообщение в личный чат → инструкция; сообщение в группу → обработка

### Шаг 5: Команда /invite

Переделать `/invite` — вместо генерации инвайт-кода, генерировать `create_chat_invite_link`. Обработать случай отсутствия прав админа.

**Файлы**: `backend/app/bot/handlers/commands.py`
**Проверка**: `/invite` в группе → ссылка; `/invite` в личном чате → перенаправление

### Шаг 6: Middleware и агент

Обновить `AuthMiddleware` — проверка workspace membership вместо `is_authorized`. Обновить `brain.py` — передавать `workspace_id` вместо `family_id`.

**Файлы**: `backend/app/bot/middlewares/auth.py`, `backend/app/agent/brain.py`
**Проверка**: полный цикл обработки сообщения в группе через агента

### Шаг 7: allowed_updates

Обновить `_start_polling()` и `_setup_webhook()` — передать `allowed_updates=dp.resolve_used_update_types()`.

**Файлы**: `backend/app/main.py`
**Проверка**: бот получает `chat_member` события

## Быстрая проверка (smoke test)

1. Запустить dev-окружение: `docker compose -f docker-compose.dev.yml up -d`
2. Написать боту в личный чат → получить инструкцию
3. Создать группу, добавить бота → получить приветствие
4. Написать сообщение в группу → бот обработает
5. Отправить `/invite` в группе → получить ссылку (если бот — админ)
6. Добавить нового пользователя → автоматическая регистрация
