# План реализации: Ассистент по уходу за питомцами

**Ветка**: `001-pet-care-assistant` | **Дата**: 2026-03-07 | **Спецификация**: [spec.md](spec.md)
**Входные данные**: Спецификация фичи из `/specs/001-pet-care-assistant/spec.md`

## Краткое описание

AI-ассистент по уходу за питомцами: Telegram-бот (голос/текст/фото) + веб-панель
с календарём, графиками и чатом. OpenAI-агент с function calling извлекает
структурированные данные из естественной речи, сохраняет в PostgreSQL
и проактивно напоминает о лекарствах, вакцинациях и событиях.

## Технический контекст

**Язык/Версия**: Python 3.11+
**Основные зависимости**: FastAPI, aiogram 3.x, SQLAlchemy 2.x async, Alembic, APScheduler 3.x, OpenAI Python SDK, pydub, httpx
**Фронтенд**: Vue 3 (Vite) + Tailwind CSS + DaisyUI
**Хранилище**: PostgreSQL 16 (asyncpg), локальная файловая система для медиа
**Тестирование**: pytest + pytest-asyncio + httpx AsyncClient + testcontainers
**Целевая платформа**: Ubuntu VDS (Linux), Docker Compose
**Тип проекта**: Веб-сервис + Telegram-бот + SPA-дашборд
**CI/CD**: GitHub Actions (lint -> test -> build Docker -> deploy по SSH)
**Линтинг**: Ruff + mypy + pre-commit hooks
**Производительность**: Нагрузка одной семьи, <3с загрузка страницы, <30с обработка голоса
**Ограничения**: 2 CPU, 4 ГБ RAM VDS; минимум данных во внешние API
**Масштаб**: 1 семья, ~5 пользователей, ~5 питомцев, ~10 напоминаний/день

## Проверка конституции

*GATE: Должна пройти перед Phase 0 research. Повторная проверка после Phase 1 design.*

| Принцип | Статус | Примечание |
|---------|--------|------------|
| I. Открытый исходный код | PASS | Нет платных функций, телеметрии, CLA |
| II. Голос как приоритет | PASS | Telegram voice -> Whisper -> Agent -> ответ |
| III. Комплексная база знаний | PASS | PostgreSQL, 15+ таблиц, историчность данных |
| IV. Проактивный уход | PASS | APScheduler + контрольные сообщения |
| V. Архитектура агента | PASS | OpenAI Responses API + function calling + strict mode |
| VI. Простота для семьи | PASS | Telegram основной, веб вторичный, понятные ошибки |
| VII. Самохостинг | PASS | Docker Compose на VDS, данные локально, минимум в API |

**Пост-дизайн проверка**: все 7 принципов соблюдены. Нарушений нет.

## Структура проекта

### Документация (эта фича)

```text
specs/001-pet-care-assistant/
├── plan.md              # Этот файл
├── research.md          # Результаты исследования (Phase 0)
├── data-model.md        # Модель данных (Phase 1)
├── quickstart.md        # Быстрый старт (Phase 1)
├── contracts/           # Контракты API (Phase 1)
│   ├── api.md           # REST API эндпоинты
│   ├── bot-commands.md  # Telegram-команды
│   └── websocket.md     # WebSocket-контракт чата
└── tasks.md             # Задачи (/speckit.tasks)
```

### Исходный код (корень репозитория)

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan + webhook
│   ├── config.py            # Pydantic Settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py          # DeclarativeBase, naming conventions
│   │   ├── session.py       # engine, async_session_maker
│   │   └── models/          # SQLAlchemy модели
│   │       ├── __init__.py
│   │       ├── pet.py
│   │       ├── health.py    # вакцинации, медзаписи, лекарства
│   │       ├── nutrition.py # диета, корм, запасы, кормление
│   │       ├── reminder.py
│   │       ├── media.py     # фото
│   │       ├── family.py    # члены семьи, языки
│   │       └── gift.py      # идеи подарков
│   ├── services/
│   │   ├── __init__.py
│   │   ├── pet_service.py
│   │   ├── health_service.py
│   │   ├── nutrition_service.py
│   │   ├── reminder_service.py
│   │   ├── media_service.py
│   │   ├── export_service.py
│   │   └── report_service.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── brain.py         # Агентный цикл (run_agent)
│   │   ├── tools.py         # Определения инструментов
│   │   ├── tool_handlers.py # Исполнители инструментов
│   │   ├── prompts.py       # System prompt builder
│   │   └── whisper.py       # Голосовая транскрипция
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py          # Depends() для FastAPI
│   │   ├── auth.py          # Telegram Login Widget
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── pets.py
│   │       ├── health.py
│   │       ├── dashboard.py
│   │       └── chat.py      # WebSocket чат
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── create.py        # bot + dp инициализация
│   │   ├── middlewares/
│   │   │   ├── __init__.py
│   │   │   ├── db.py        # DbSessionMiddleware
│   │   │   └── auth.py      # Проверка авторизации семьи
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── start.py     # /start, /help
│   │   │   ├── pets.py      # /newpet, /pets, /profile, /deletepet
│   │   │   ├── message.py   # Голос/текст/фото -> агент
│   │   │   ├── reminders.py # Callback от напоминаний
│   │   │   ├── commands.py  # /sos, /vetreport, /export, /import, /giftideas
│   │   │   └── dashboard.py # /dashboard
│   │   └── keyboards/
│   │       └── __init__.py
│   └── scheduler/
│       ├── __init__.py
│       └── jobs.py          # Задачи планировщика
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── contract/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
└── docker-compose.yml

frontend/
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/
│   │   └── index.js
│   ├── components/
│   │   ├── PetCard.vue
│   │   ├── Calendar.vue
│   │   ├── WeightChart.vue
│   │   ├── Timeline.vue
│   │   ├── ChatWidget.vue
│   │   └── TelegramLogin.vue
│   ├── pages/
│   │   ├── Dashboard.vue
│   │   ├── PetProfile.vue
│   │   ├── Analytics.vue
│   │   └── Login.vue
│   └── services/
│       └── api.js
├── index.html
├── vite.config.js
├── tailwind.config.js
├── package.json
└── postcss.config.js

.github/
└── workflows/
    ├── ci.yml              # lint -> test -> build
    └── deploy.yml          # deploy на VDS

.pre-commit-config.yaml
```

**Решение по структуре**: Веб-приложение (Option 2) — backend (Python/FastAPI) + frontend
(Vue 3/Vite). Frontend собирается в статику и раздаётся FastAPI через `StaticFiles`.
Один Docker-образ (multi-stage build). CI/CD и линтеры — отдельные артефакты
в `.github/workflows/` и `.pre-commit-config.yaml`.

## Отслеживание сложности

Нарушений конституции нет. Таблица не требуется.
