# Исследование: Ассистент по уходу за питомцами

**Дата**: 2026-03-07
**Статус**: Завершено

## 1. Совместный хостинг aiogram 3.x + FastAPI

**Решение**: Webhook-режим, единый ASGI-процесс (uvicorn)
**Обоснование**: У проекта уже есть VDS с HTTPS/nginx — webhook идеален.
Не требует лишних фоновых задач. Long-polling — только для локальной разработки.
**Отклонённые альтернативы**: Long-polling (не подходит для продакшна с FastAPI),
`SimpleRequestHandler` aiogram (рассчитан на aiohttp, не на FastAPI).

### Ключевые паттерны

- FastAPI `lifespan` context manager для startup/shutdown бота
- `dp.feed_update(bot, update)` для передачи webhook-обновлений
- `secret_token` в заголовке `X-Telegram-Bot-Api-Secret-Token` для верификации
- `dp.resolve_used_update_types()` вызывать ПОСЛЕ регистрации всех роутеров
- `drop_pending_updates=True` при разработке
- Обязательно `await bot.session.close()` при shutdown

### Общие зависимости между ботом и API

- Единый `async_session_maker` (SQLAlchemy) — общий для обоих
- FastAPI: `Depends()` -> `get_db()` -> `async_session_maker()`
- aiogram: `DbSessionMiddleware` -> `data["session"]` -> kwarg в хендлерах
- Сервисы (`services/`) — общий слой бизнес-логики

---

## 2. ORM и работа с базой данных

**Решение**: SQLAlchemy 2.x async + asyncpg + Alembic
**Обоснование**: Alembic — единственный зрелый инструмент миграций в Python.
SQLAlchemy 2.x с `Mapped[]` и `mapped_column()` — современный декларативный стиль.
Для ~15 таблиц и нагрузки одной семьи overhead ORM нерелевантен.
**Отклонённые альтернативы**:
- asyncpg raw — слишком много бойлерплейта при 15 таблицах, нет автомиграций
- Tortoise ORM — Aerich (миграции) нестабилен, баги с индексами и переименованием

### Рекомендуемые паттерны

- `MetaData(naming_convention=...)` для единообразных имён индексов
- `expire_on_commit=False` для `AsyncSession`
- Alembic: `alembic init -t async` для async-шаблона
- Шаблон миграций: `%%(year)d-%%(month).2d-%%(day).2d_%%(slug)s`

---

## 3. Планировщик напоминаний

**Решение**: APScheduler 3.x (стабильная ветка, 3.11.x)
**Обоснование**: In-process, работает в том же event loop (AsyncIOScheduler).
SQLAlchemyJobStore для PostgreSQL — задачи переживают перезагрузки.
`misfire_grace_time=None` + `coalesce=True` — пропущенные напоминания
срабатывают при восстановлении сервера. Для ~10 напоминаний/день — идеально.
**Отклонённые альтернативы**:
- APScheduler 4.x — альфа (4.0.0a6), баги с потерей задач и блокировками
- Celery Beat — оверкилл (Redis/RabbitMQ, worker-процессы) для одной семьи
- arq — нет PostgreSQL-бэкенда, нет обработки пропущенных задач
- Кастомный asyncio — недели работы для сомнительного результата

---

## 4. Хранение файлов (фото, документы)

**Решение**: Локальная файловая система с абстракцией `FileStorage` Protocol
**Обоснование**: Для одной семьи (десятки ГБ максимум) объектное хранилище —
оверинжиниринг. MinIO Community Edition в maintenance mode с конца 2025.
На VDS с 4 ГБ RAM MinIO сожрёт 200-400 МБ.
**Отклонённые альтернативы**: MinIO (maintenance mode, ресурсоёмкий),
SeaweedFS/Garage (молодые, непроверенные)

### Структура каталогов

```
/data/uploads/{pet_id}/{year}/{month}/
```

Docker: volume mount `/data/uploads`. Бэкап: `rsync` или `tar`.

### Абстракция для будущей гибкости

```python
class FileStorage(Protocol):
    async def save(self, path: str, data: bytes) -> str: ...
    async def get(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> None: ...
```

---

## 5. Frontend для веб-панели

**Решение**: Vue 3 (Vite) + Tailwind CSS + DaisyUI
**Обоснование**: Оптимальный баланс простоты и возможностей. Vue 3 Composition
API — самый понятный фреймворк для Python-разработчика. Зрелая экосистема:
vue3-apexcharts (графики), @fullcalendar/vue3 (календарь), DaisyUI (chat, timeline).
Бандл ~200-300 КБ. Деплой: `vite build` -> статика -> FastAPI `StaticFiles`.
**Отклонённые альтернативы**:
- HTMX — не подходит для графиков, календаря и стриминга чата
- React — избыточен для семейного проекта
- Svelte — меньше экосистема готовых компонентов

### Библиотеки

| Задача | Библиотека |
|--------|-----------|
| Графики веса | vue3-apexcharts |
| Календарь | @fullcalendar/vue3 |
| Таймлайн | DaisyUI timeline (CSS) |
| Чат | Кастомный Vue + DaisyUI chat |
| HTTP-клиент | ofetch или нативный fetch |
| Формы | VeeValidate |

### Telegram Login Widget

Стандартный `<script>` тег + callback на FastAPI эндпоинт.
FastAPI верифицирует hash через HMAC-SHA-256 с токеном бота -> JWT.

### Деплой

Multi-stage Dockerfile: node:slim (vite build) -> python:3.11-slim (uvicorn).
FastAPI: `app.mount("/", StaticFiles(directory="frontend/dist", html=True))`.

---

## 6. AI-агент (OpenAI)

**Решение**: OpenAI Responses API + gpt-4o-mini (основной) + gpt-4o (Vision)
**Обоснование**: Responses API — актуальная платформа OpenAI для агентов.
Встроенное управление состоянием через `previous_response_id`.
Strict mode в function calling гарантирует валидный JSON.
gpt-4o-mini дешёвый и быстрый для CRUD через tools.
**Отклонённые альтернативы**: Chat Completions API (устаревает для агентов),
Anthropic Claude (нет нативного function calling с strict mode)

### Модели по задачам

| Задача | Модель | Стоимость |
|--------|--------|-----------|
| Основной агент | gpt-4o-mini | ~$0.15/1M input |
| Обработка паспортов | gpt-4o | ~$2.50/1M input |
| Описание фото | gpt-4o-mini | ~$0.15/1M input |
| Транскрипция голоса | gpt-4o-mini-transcribe | $0.003/мин |

### Архитектура агентного цикла

1. Пользователь отправляет сообщение (голос/текст/фото)
2. Голос -> gpt-4o-mini-transcribe -> текст
3. Фото -> классификация (паспорт/обычное/документ) -> соответствующий pipeline
4. Текст -> `run_agent()` с system prompt + tools + `previous_response_id`
5. Агент вызывает инструменты (CRUD) -> получает результаты -> отвечает
6. Ответ отправляется пользователю

### Управление контекстом

- System prompt: список питомцев, активные лекарства, ближайшие напоминания (~300-500 токенов)
- Подробные данные подгружаются через tools (lazy loading)
- `previous_response_id` для краткосрочной истории диалога
- Обрезка после ~8-10 ходов с суммаризацией
- Бюджет: ~4000-8500 токенов на запрос

### Обработка голоса

- Telegram: OGG/Opus -> pydub -> MP3 (64k bitrate) -> Whisper API
- `language="ru"` принудительно (повышает точность на ~5-10%)
- ffmpeg обязателен в Docker-образе
- Лимит: 25 МБ на файл (для голосовых Telegram — не проблема)

---

## 7. CI/CD Pipeline

**Решение**: GitHub Actions с 4 этапами
**Обоснование**: Нативная интеграция с GitHub, бесплатно для open source.
Service containers для PostgreSQL в тестах. GHA cache для Docker layers.

### Этапы

1. **lint** — `ruff check`, `ruff format --check`, `mypy app/`
2. **test** — pytest с PostgreSQL service container, coverage >=80%
3. **build** — Docker multi-stage image -> ghcr.io (только main)
4. **deploy** — SSH на VDS -> `docker compose pull && up -d` (только main)

### Триггеры

- Push в `main` и `feature/**` ветки
- Pull requests в `main`

---

## 8. Линтинг и качество кода

**Решение**: Ruff + mypy + pre-commit
**Обоснование**: Ruff заменяет black + isort + flake8 + pyupgrade. В 10-100x
быстрее. FastAPI, Pydantic, pandas уже перешли на Ruff. mypy дополняет
проверкой типов (Ruff не заменяет type checker).

### Ruff правила

`E, W, F, UP, B, C4, I, N, S, T20, PT, SIM, ASYNC, RUF` — полный набор
для FastAPI/aiogram проекта, включая безопасность (bandit) и async-проверки.

### Pre-commit hooks

1. `ruff-check --fix` (линтер с автоисправлениями)
2. `ruff-format` (форматтер)
3. `mypy` (проверка типов)
