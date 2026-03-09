# Luna the Dog

AI-ассистент по уходу за питомцами для всей семьи.
Telegram-бот с голосовым вводом, AI-агент на базе OpenAI GPT с function calling.

> **Статус**: MVP (US1) — запись данных о питомце голосом и текстом через Telegram

## Что умеет сейчас

- **Голосовой и текстовый ввод** — отправьте боту «Луна весит 28 кг» или голосовое сообщение, агент извлечёт данные и сохранит в БД
- **AI-агент** — OpenAI GPT с function calling: понимает естественный язык, ведёт контекст диалога, вызывает нужные сервисы
- **Данные о здоровье** — вес, вакцинации, мед. записи, лекарства, заметки, экстренный профиль (аллергии, ветеринар, группа крови)
- **Питание** — диетические записи, записи кормлений
- **Семья** — регистрация через `/start`, инвайт-система (`/invite`) для добавления членов семьи
- **Аудит** — все изменения логируются (кто, когда, что изменил)
- **OpenAI OAuth** — подключение через `/connectai` (PKCE flow) или fallback на API-ключ
- **Локализация** — RU/EN, относительные даты («сегодня», «вчера»)

### Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация семьи / присоединение по инвайт-коду |
| `/help` | Справка |
| `/invite` | Создать / показать инвайт-код для добавления члена семьи |
| `/connectai` | Подключить OpenAI через OAuth (PKCE) |

Любое текстовое или голосовое сообщение обрабатывается AI-агентом.

## Технологии

| Слой | Стек |
|------|------|
| Backend | Python 3.11+, FastAPI, aiogram 3.x, SQLAlchemy 2.x async |
| AI | OpenAI GPT (function calling), Whisper (голосовая транскрипция) |
| База данных | PostgreSQL 16, Alembic (миграции) |
| Инфраструктура | Docker Compose |

## Требования

- Docker + Docker Compose
- Telegram Bot Token (через [@BotFather](https://t.me/BotFather))
- OpenAI API Key ([platform.openai.com](https://platform.openai.com))

Для локальной разработки без Docker дополнительно:

- Python 3.11+
- PostgreSQL 16
- ffmpeg (для обработки голосовых сообщений)

## Быстрый старт

### Docker Compose (продакшн / полный запуск)

```bash
git clone https://github.com/user/luna-the-dog.git
cd luna-the-dog
cp .env.example .env
# Заполнить .env (см. раздел «Переменные окружения»)

docker compose up -d
docker compose exec app alembic upgrade head
```

Для работы webhook нужен публичный URL. Для локального тестирования — ngrok:

```bash
ngrok http 8000
# Скопировать HTTPS-URL в .env → WEBHOOK_URL=https://xxx.ngrok-free.app/webhook
docker compose restart app
```

### Локальная разработка

```bash
# PostgreSQL через Docker
docker compose up -d postgres

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Миграции
alembic upgrade head

# Запуск
uvicorn backend.app.main:app --reload
```

> **Примечание**: сейчас бот работает только через webhook. Для локальной разработки нужен туннель (ngrok, cloudflared). Режим polling (`DEBUG=true` без `WEBHOOK_URL`) планируется.

## Переменные окружения

Скопируйте `.env.example` → `.env` и заполните:

| Переменная | Обязательна | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | да | Токен бота от @BotFather |
| `OPENAI_API_KEY` | да | API-ключ OpenAI |
| `DATABASE_URL` | да | Строка подключения PostgreSQL (задана по умолчанию для Docker) |
| `POSTGRES_PASSWORD` | да | Пароль PostgreSQL (задан по умолчанию для Docker) |
| `WEBHOOK_URL` | да* | URL вебхука, напр. `https://example.com/webhook` |
| `WEBHOOK_SECRET` | да* | Секрет верификации вебхука |
| `JWT_SECRET` | нет | Секрет JWT (для будущей веб-панели) |
| `OPENAI_OAUTH_CLIENT_ID` | нет | OAuth Client ID для подключения через `/connectai` |
| `OAUTH_ENCRYPTION_KEY` | нет | Fernet-ключ для шифрования OAuth-токенов |
| `MEDIA_DIR` | нет | Путь к загрузкам (по умолчанию `/data/uploads`) |
| `DEBUG` | нет | Режим отладки (по умолчанию `false`) |

\* Обязательны при работе через webhook. При будущем режиме polling — не нужны.

## Команды разработки

| Команда | Описание |
|---------|----------|
| `uvicorn backend.app.main:app --reload` | Dev-сервер backend |
| `alembic upgrade head` | Применить миграции |
| `alembic revision --autogenerate -m "..."` | Новая миграция |
| `backend/.venv/bin/pytest backend/tests` | Запуск тестов |
| `backend/.venv/bin/pre-commit run --all-files` | Полная проверка качества |
| `ruff check . --fix` | Линтер с автофиксом |
| `ruff format .` | Форматирование |
| `docker compose up -d` | Запуск через Docker |

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
    db/models/      # SQLAlchemy: family, pet, health, nutrition, audit
    services/       # Бизнес-логика: pet, health, nutrition, family, audit, openai_auth
  alembic/          # Миграции БД
  tests/            # unit-тесты

frontend/           # Vue 3 SPA (заготовка, реализация в US5)
```

## Дорожная карта

- [x] **US1** — Запись данных голосом/текстом (MVP)
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
