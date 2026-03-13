# Implementation Plan: Групповой режим работы бота

**Branch**: `003-group-only-mode` | **Date**: 2026-03-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-group-only-mode/spec.md`

## Summary

Перевод бота с singleton-модели (одна семья на deploy) на мультитенантную модель, где каждая Telegram-группа — изолированный workspace. Бот отклоняет личные сообщения с инструкцией по созданию группы, автоматически создаёт workspace при добавлении в группу, регистрирует участников группы как членов workspace, а команда `/invite` возвращает пригласительную ссылку на группу вместо одноразового кода.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, Pydantic Settings >=2.7.0, OpenAI SDK, APScheduler 3.x
**Storage**: PostgreSQL 16 (asyncpg), Alembic для миграций
**Testing**: pytest (asyncio_mode="auto"), pre-commit (ruff, mypy)
**Target Platform**: Ubuntu VDS (2 CPU, 4 ГБ RAM), Docker + Docker Compose
**Project Type**: web-service (Telegram-бот + FastAPI)
**Performance Goals**: обработка сообщений без деградации при работе в нескольких группах одновременно; `/invite` < 3 сек; регистрация нового участника < 5 сек
**Constraints**: скромный VDS, один процесс, асинхронный I/O
**Scale/Scope**: десятки-сотни групп, единицы-десятки пользователей на группу

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Статус | Комментарий |
|---------|--------|-------------|
| I. Открытый исходный код | ✅ PASS | Никаких платных функций, подписок. Мультитенантность — техническая основа для масштабирования, не paywall |
| II. Голос как приоритет | ✅ PASS | Голос, текст, фото обрабатываются в группе как раньше. В личном чате — отклонение без транскрибирования |
| III. Комплексная база знаний | ✅ PASS | Данные питомцев изолированы по workspace. Полная история сохраняется |
| IV. Проактивный уход | ✅ PASS | Напоминания привязываются к workspace, отправляются в группу |
| V. Архитектура агента | ✅ PASS | Агент получает workspace_id вместо family_id. Контекст питомца — в рамках workspace |
| VI. Простота для семьи | ✅ PASS | Упрощение: вступил в группу = получил доступ. Без инвайт-кодов |
| VII. Самохостинг | ✅ PASS | Все данные на собственном VDS. Один deploy обслуживает все группы |

**Результат**: все принципы соблюдены, нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/003-group-only-mode/
├── plan.md              # Этот файл
├── research.md          # Phase 0: исследование
├── data-model.md        # Phase 1: модель данных
├── quickstart.md        # Phase 1: быстрый старт
├── contracts/           # Phase 1: контракты
└── tasks.md             # Phase 2: задачи (создаётся /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── agent/
│   │   └── brain.py           # workspace_id вместо family_id
│   ├── bot/
│   │   ├── create.py          # регистрация роутеров + allowed_updates
│   │   ├── handlers/
│   │   │   ├── start.py       # логика private → инструкция по группе
│   │   │   ├── commands.py    # /invite → ссылка на группу
│   │   │   ├── message.py     # маршрутизация через workspace
│   │   │   └── group_events.py  # NEW: my_chat_member, chat_member, миграция
│   │   └── middlewares/
│   │       └── auth.py        # проверка membership через workspace
│   ├── db/
│   │   └── models/
│   │       ├── family.py      # Workspace (замена Family), WorkspaceMember
│   │       └── ...            # Pet и health-модели: FK → workspace_id
│   ├── services/
│   │   ├── workspace_service.py  # NEW: CRUD workspace
│   │   └── family_service.py     # рефакторинг / удаление invite-логики
│   └── config.py
├── alembic/
│   └── versions/              # новая миграция: Workspace + FK
└── tests/
    ├── test_workspace_service.py
    ├── test_group_events.py
    └── ...

frontend/
└── src/                       # минимальные изменения (если есть)
```

**Structure Decision**: Web application (backend + frontend). Основные изменения в `backend/app/`. Frontend на данном этапе не затрагивается — фича касается исключительно Telegram-бота.

## Complexity Tracking

Нарушений конституции нет — таблица не заполняется.
