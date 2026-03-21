# Luna the Dog

AI-ассистент по уходу за питомцами для всей семьи.
Telegram-бот с голосовым вводом, AI-агент на базе OpenAI GPT с function calling.

> **Статус**: MVP — запись данных о питомце голосом и текстом через Telegram

## Что умеет

- **Голосовой и текстовый ввод** — отправьте боту «Луна весит 28 кг» или голосовое сообщение, агент извлечёт данные и сохранит в БД
- **AI-агент** — OpenAI GPT с function calling: понимает естественный язык, ведёт контекст диалога, вызывает нужные сервисы
- **Данные о здоровье** — запись и чтение: вес, вакцинации, мед. записи, лекарства, заметки, экстренный профиль (аллергии, ветеринар, группа крови)
- **Расширенные измерения** — произвольные измерения (температура, рост и др.), визиты к ветеринару, наблюдения за настроением и аппетитом, циклы течки
- **Документы** — хранение ссылок на ветеринарные документы с типом и датой выдачи
- **Питание** — диетические записи с брендом и типом корма, записи кормлений с размером порции
- **Чтение данных** — бот отвечает на вопросы о сохранённых данных: «сколько Луна весила в январе?», «какие прививки?», «покажи историю болезней»
- **Семья** — регистрация через `/start`, инвайт-система (`/invite`) для добавления членов семьи
- **Аудит** — все изменения логируются (кто, когда, что изменил)
- **OpenAI API** — бот и AI-агент работают только через `OPENAI_API_KEY`
- **Локализация** — RU/EN, относительные даты («сегодня», «вчера»)

### Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация семьи / присоединение по инвайт-коду |
| `/help` | Справка |
| `/invite` | Создать / показать инвайт-код для добавления члена семьи |

Любое текстовое или голосовое сообщение обрабатывается AI-агентом.

## Технологии

| Слой | Стек |
|------|------|
| Backend | Python 3.11+, FastAPI, aiogram 3.x, SQLAlchemy 2.x async |
| AI | OpenAI GPT (function calling), Whisper (голосовая транскрипция) |
| База данных | PostgreSQL 16, Alembic (миграции) |
| Инфраструктура | Docker Compose (dev + prod) |

## Режимы работы

Приложение поддерживает два режима, управляемых переменной `APP_ENV`:

| | Dev (`APP_ENV=dev`) | Prod (`APP_ENV=prod`) |
|---|---|---|
| Получение сообщений | Polling (без ngrok) | Webhook |
| Уровень логирования | DEBUG | INFO |
| Docker | Обязателен | Обязателен |
| WEBHOOK_URL | Игнорируется (даже если задан) | Обязателен |
| Env-файл | `.env.dev` | `.env.prod` |

## Требования

- Docker + Docker Compose
- Telegram Bot Token (dev/prod боты через [@BotFather](https://t.me/BotFather))
- OpenAI API Key ([platform.openai.com](https://platform.openai.com))

Для локального запуска `pytest`/`pre-commit` дополнительно нужен Python 3.11+ и отдельное виртуальное окружение `backend/.venv`.

## Локальное Python-окружение

DEV и PROD работают через Docker Compose и не требуют локального `.venv`.
Но команды `pytest`, `pre-commit`, `mypy` и локальный `alembic` в этом репозитории ожидают установленное окружение в `backend/.venv`.

```bash
cd backend
python3.11 -m venv .venv                                                        
source .venv/bin/activate
pip install --upgrade pip -r requirements.txt -r requirements-dev.txt
```

После этого становятся доступны команды вида `backend/.venv/bin/pytest ...` и `backend/.venv/bin/pre-commit ...`.

## Быстрый старт

### DEV (Docker-only, polling + hot reload + foreground логи)

```bash
git clone https://github.com/user/luna-the-dog.git
cd luna-the-dog

cp .env.dev.example .env.dev
# Заполнить .env.dev (минимум: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY)

docker compose -f docker-compose.dev.yml up
```

`migrate` запускается автоматически перед `app`.
Логи `postgres` и `app` идут в текущий терминал; hot reload включён через `--reload`.
Даже если в `.env.dev` случайно задан `WEBHOOK_URL`, в dev-режиме используется polling.
В `docker-compose.dev.yml` `DATABASE_URL` принудительно направляется на `postgres` внутри compose-сети.

Опциональный фоновый запуск dev:

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml logs -f app
```

### PROD (Docker-only, webhook)

```bash
cp .env.prod.example .env.prod
# Заполнить .env.prod: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, WEBHOOK_URL, WEBHOOK_SECRET, ...

docker compose up -d
```

`migrate` запускается автоматически перед `app`, ручной шаг `alembic upgrade head` не нужен.
Для работы webhook нужен публичный URL (домен или туннель).

## Файлы конфигурации

| Файл | Назначение |
|------|------------|
| `.env.dev.example` | Шаблон для dev-окружения (в git) |
| `.env.prod.example` | Шаблон для prod-окружения (в git) |
| `.env.example` | Legacy fallback-шаблон (deprecated для запуска) |
| `.env.dev` | Реальная dev-конфигурация (gitignored) |
| `.env.prod` | Реальная prod-конфигурация (gitignored) |

## Переменные окружения

| Переменная | Dev | Prod | Описание |
|---|---|---|---|
| `APP_ENV` | `dev` | `prod` | Режим работы (по умолчанию `dev`) |
| `TELEGRAM_BOT_TOKEN` | да | да | Токен бота от @BotFather |
| `OPENAI_API_KEY` | да | да | API-ключ OpenAI |
| `DATABASE_URL` | да | да | Строка подключения PostgreSQL |
| `POSTGRES_PASSWORD` | да | да | Пароль PostgreSQL |
| `WEBHOOK_URL` | — | да | URL вебхука, напр. `https://example.com/webhook` |
| `WEBHOOK_SECRET` | — | да | Секрет верификации вебхука |
| `JWT_SECRET` | — | рек. | Секрет JWT (для будущей веб-панели) |
| `DEBUG` | `true` | `false` | Режим отладки |
| `MEDIA_DIR` | `./data/uploads` | `/data/uploads` | Путь к загрузкам |

## Команды разработки

| Команда | Описание |
|---------|----------|
| `docker compose -f docker-compose.dev.yml up` | Dev (foreground, polling, hot reload) |
| `docker compose -f docker-compose.dev.yml up -d` | Dev в фоне |
| `docker compose -f docker-compose.dev.yml logs -f app` | Логи app в dev после detached-запуска |
| `docker compose up -d` | Prod (webhook) |
| `docker compose logs -f app` | Логи app в prod |
| `backend/.venv/bin/alembic -c backend/alembic.ini revision --autogenerate -m "..."` | Новая миграция |
| `backend/.venv/bin/pytest backend/tests/unit/ -v` | Unit-тесты |
| `backend/.venv/bin/pytest backend/tests/ -v` | Все тесты (нужен Docker для testcontainers) |
| `backend/.venv/bin/pre-commit run --all-files` | Полная проверка качества |
| `ruff check . --fix` | Линтер с автофиксом |
| `ruff format .` | Форматирование |

## Тестирование

```bash
# Unit-тесты
backend/.venv/bin/pytest backend/tests/unit/ -v

# Все тесты с testcontainers (нужен Docker)
backend/.venv/bin/pytest backend/tests/ -v

# Integration-тесты с внешним PostgreSQL
TEST_DATABASE_URL=postgresql+asyncpg://luna:password@localhost:5432/luna_dev_db \
  backend/.venv/bin/pytest backend/tests/ -v
```

## Качество кода

Pre-commit хуки проверяют перед каждым коммитом:

- **ruff** — линтер
- **ruff-format** — форматирование
- **mypy** — типизация для core-слоёв (`app/services`, `app/db`, `app/api/deps.py`)

```bash
# Полная проверка
backend/.venv/bin/pre-commit run --all-files

# Диагностическая типизация (за пределами commit gate)
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend
```

## Структура проекта

```
backend/
  app/
    agent/          # AI-агент: brain, tools, prompts, whisper, i18n
    api/            # REST API (auth, deps, будущие роутеры)
    bot/
      handlers/     # Telegram: start, commands, message
      middlewares/  # DB-сессия, авторизация
    db/models/      # SQLAlchemy: family, pet, health, nutrition, audit, documents
    scheduler/      # APScheduler — напоминания
    services/       # Бизнес-логика: pet, health, nutrition, family, audit
    config.py       # Настройки (APP_ENV, динамическая загрузка env-файлов)
    main.py         # FastAPI lifespan (polling/webhook switching)
  alembic/          # Миграции БД
  tests/            # unit + integration тесты

frontend/           # Vue 3 SPA (заготовка)
specs/              # Спецификации фич (speckit)
```

## Дорожная карта

- [x] **001** — Запись данных голосом/текстом (MVP)
- [x] **002** — Разграничение dev/prod режимов
- [x] **007** — Расширение БД и инструментов AI-агента: чтение данных, новые сущности, расширенные поля
- [ ] **US2** — Управление питомцами (создание, просмотр, удаление)
- [ ] **US3** — Напоминания и контроль выполнения
- [ ] **US4** — Обработка фотографий (Vision AI)
- [ ] **US5** — Веб-панель (дашборд, календарь, чат)
- [ ] **US6** — Ветеринарный отчёт с переводом
- [ ] **US7** — Экстренная карточка `/sos`
- [ ] **US8** — Аналитика здоровья
- [ ] **US9** — Учёт запасов и расписание кормления
- [ ] **US10** — Экспорт/импорт данных
- [ ] **US11** — Идеи подарков для питомца

## Лицензия

[MIT](LICENSE)
