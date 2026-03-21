# Implementation Plan: Расширение базы данных и инструментов AI-агента

**Branch**: `007-extend-agent-tools` | **Date**: 2026-03-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-extend-agent-tools/spec.md`

## Summary

Расширить возможности AI-агента «Луна» в двух направлениях: (1) добавить инструменты чтения для всех существующих данных (вес, прививки, лекарства, заметки, кормления, диеты, медицинские записи), (2) добавить 5 новых таблиц (измерения, визиты к ветеринару, самочувствие, документы, течка) с полным набором инструментов. Дополнительно — расширить параметры существующих инструментов записи до полного соответствия схеме БД и обновить system prompt для поддержки режима чтения.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, OpenAI SDK, APScheduler 3.x
**Storage**: PostgreSQL 16 (asyncpg), Alembic для миграций
**Testing**: pytest, pre-commit (ruff + mypy)
**Target Platform**: Ubuntu VDS (2 CPU, 4 ГБ RAM), Docker Compose
**Project Type**: web-service (Telegram-бот + FastAPI)
**Performance Goals**: нагрузка одной семьи, без специальных требований
**Constraints**: все данные на собственном сервере, минимум данных во внешние API
**Scale/Scope**: мультитенант (несколько workspace), несколько питомцев на workspace

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Статус | Обоснование |
| ------- | ------ | ----------- |
| I. Открытый код | PASS | Никаких платных функций, телеметрии, CLA |
| II. Голос как приоритет | PASS | Фича не затрагивает каналы ввода, работает через существующий NLP-пайплайн |
| III. Комплексная база знаний | PASS | Фича напрямую расширяет базу знаний: новые таблицы + инструменты чтения |
| IV. Проактивный уход | PASS | Новые таблицы (визиты, измерения) дают основу для будущих напоминаний |
| V. Архитектура агента | PASS | Добавляются инструменты чтения/записи через OpenAI function calling |
| VI. Простота для семьи | PASS | Взаимодействие через естественный язык, без новых команд |
| VII. Самохостинг | PASS | Все данные в PostgreSQL на собственном сервере |

**Результат**: все гейты пройдены, нарушений нет.

**Post-Phase 1 Re-check**: ✅ Дизайн соответствует конституции. Все данные остаются в PostgreSQL на собственном сервере. Новые инструменты работают через существующий OpenAI function calling. Интерфейс — естественный язык через Telegram.

## Project Structure

### Documentation (this feature)

```text
specs/007-extend-agent-tools/
├── spec.md              # Спецификация фичи
├── plan.md              # Этот файл
├── research.md          # Phase 0: исследование
├── data-model.md        # Phase 1: модель данных
├── quickstart.md        # Phase 1: быстрый старт
├── contracts/           # Phase 1: контракты инструментов
│   ├── read-tools.md    # Контракты инструментов чтения
│   └── write-tools.md   # Контракты инструментов записи (расширения)
└── tasks.md             # Phase 2: задачи (/speckit.tasks)
```

### Source Code (repository root)

```text
backend/app/
├── agent/
│   ├── tools.py              # + определения новых инструментов
│   ├── tool_handlers.py      # + обработчики новых инструментов
│   └── prompts.py            # + обновлённый system prompt
├── db/models/
│   ├── health.py             # + новые модели: Measurement, VetVisit, MoodLog, HeatCycle
│   ├── nutrition.py          # (без изменений)
│   ├── pet.py                # (без изменений)
│   └── documents.py          # + новая модель: Document
├── services/
│   ├── health_service.py     # + методы чтения/записи для новых моделей здоровья
│   ├── nutrition_service.py  # (используются существующие методы)
│   └── document_service.py   # + новый сервис для документов

alembic/versions/
└── xxxx_add_measurement_vetvisit_moodlog_document_heatcycle.py  # Миграция

backend/tests/unit/
├── test_read_tools.py        # Тесты инструментов чтения
├── test_new_models.py        # Тесты новых моделей
└── test_extended_tools.py    # Тесты расширенных инструментов
```

**Structure Decision**: Следуем существующей структуре проекта. Новые модели здоровья (Measurement, VetVisit, MoodLog, HeatCycle) добавляются в `health.py`, документы — в отдельный `documents.py`. Сервисы расширяются аналогично.

## Complexity Tracking

> Нарушений конституции нет, таблица не требуется.
