# Quickstart: Расширение базы данных и инструментов AI-агента

**Feature**: 007-extend-agent-tools
**Date**: 2026-03-17

## Предварительные требования

- Python 3.11+, PostgreSQL 16, Docker Compose
- Виртуальное окружение: `backend/.venv/`
- Переменные окружения: `.env` (OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, DATABASE_URL)

## Порядок реализации

### Шаг 1: Новые модели БД

Добавить 5 моделей в `backend/app/db/models/`:
- Measurement, VetVisit, MoodLog, HeatCycle → `health.py`
- Document → новый `documents.py`

Зарегистрировать в `__init__.py` для Alembic.

### Шаг 2: Alembic-миграция

```bash
alembic revision --autogenerate -m "add measurement vetvisit moodlog document heatcycle tables"
alembic upgrade head
```

### Шаг 3: Сервисный слой

Расширить `health_service.py`:
- add_measurement(), get_measurements()
- add_vet_visit(), get_vet_visits()
- add_mood_log(), get_mood_logs()
- add_heat_cycle(), get_heat_cycles()
- get_weight_history(), get_vaccinations(), get_medications_list(), get_notes_list()
- add_medical_record() (уже существует), get_medical_records()

Создать `document_service.py`:
- add_document(), get_documents()

### Шаг 4: Расширение инструментов записи

В `tools.py` — расширить определения: add_vaccination, add_medication, add_diet, add_feeding (новые параметры).
В `tool_handlers.py` — передать новые параметры в сервисный слой.
Расширить `_PET_UPDATE_FIELD_WHITELIST` в `tool_handlers.py`.

### Шаг 5: Новые инструменты (запись + чтение)

В `tools.py` — добавить определения: add_medical_record, add_measurement, add_vet_visit, add_mood_log, add_document, add_heat_cycle + все get_* инструменты.
В `tool_handlers.py` — добавить обработчики.

### Шаг 6: System prompt

В `prompts.py` — обновить текст, чтобы агент знал о возможности чтения данных.

### Шаг 7: Тесты

Юнит-тесты для новых моделей, сервисов, обработчиков.

## Проверка

```bash
# Миграции
alembic upgrade head

# Тесты
pytest

# Линтинг
backend/.venv/bin/pre-commit run --all-files

# Dev-сервер
docker compose -f docker-compose.dev.yml up -d
```
