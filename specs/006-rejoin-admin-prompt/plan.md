# Implementation Plan: Приветствие при возвращении бота и напоминание о правах администратора

**Branch**: `006-rejoin-admin-prompt` | **Date**: 2026-03-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-rejoin-admin-prompt/spec.md`

## Summary

Реализация различения первичного и повторного добавления бота в группу с адаптивным приветственным сообщением. При возвращении бот отправляет компактное тёплое сообщение с просьбой о правах администратора. Все инструкционные сообщения в группе (первичное приветствие, help) обновляются с упоминанием необходимости прав админа.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36
**Storage**: PostgreSQL 16 (asyncpg)
**Testing**: pytest
**Target Platform**: Linux server (Ubuntu VDS)
**Project Type**: web-service (Telegram bot + FastAPI)
**Performance Goals**: стандартная для single-family бота, без особых требований
**Constraints**: скромный VDS (2 CPU, 4 ГБ RAM)
**Scale/Scope**: одна семья, несколько групп

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Статус | Комментарий |
|---------|--------|-------------|
| I. Открытый исходный код | ✅ | Не затрагивается — изменения только в сообщениях и логике хендлера |
| II. Голос как приоритет | ✅ | Не затрагивается — фича работает на уровне системных событий (my_chat_member), не ввода |
| III. База знаний | ✅ | Не затрагивается — нет изменений в хранении данных о питомцах |
| IV. Проактивный уход | ✅ | Не затрагивается — фича про приветственные сообщения |
| V. Агентная архитектура | ✅ | Не затрагивается — фича вне агентного цикла |
| VI. Простота для семьи | ✅ | Улучшает — чёткие инструкции о правах администратора помогают семье настроить бота |
| VII. Самохостинг | ✅ | Не затрагивается — нет новых внешних зависимостей |

**Результат**: все гейты пройдены, нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/006-rejoin-admin-prompt/
├── plan.md              # Этот файл
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
backend/app/
├── bot/
│   ├── handlers/
│   │   ├── constants.py           # Обновление: GROUP_WELCOME_TEXT, HELP_GROUP_TEXT + новые константы
│   │   ├── group_events.py        # Обновление: логика различения new/rejoin + проверка admin-статуса
│   │   └── commands.py            # Без изменений (уже использует HELP_GROUP_TEXT из constants.py)
│   └── create.py                  # Без изменений
├── services/
│   └── workspace_service.py       # Обновление: get_or_create_workspace возвращает признак «создан / реактивирован»
└── db/models/
    └── workspace.py               # Без изменений

tests/
├── unit/
│   ├── test_group_events.py       # Новые тесты для различения new/rejoin
│   └── test_constants.py          # Проверка наличия admin-напоминания в текстах
```

**Structure Decision**: используем существующую структуру проекта. Изменения затрагивают только 3 файла: `constants.py`, `group_events.py`, `workspace_service.py`.
