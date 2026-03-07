# Luna the Dog

AI-ассистент по уходу за питомцами для всей семьи.
Telegram-бот с голосовым вводом + веб-панель с календарём и аналитикой.

## Возможности

- **Голос и текст** — скажите боту «Луна весит 28 кг» или отправьте голосовое, данные сохранятся автоматически
- **Управление питомцами** — профили, история здоровья, вакцинации, лекарства, диета
- **Напоминания** — автоматическое планирование приёма лекарств и вакцинаций с контролем выполнения
- **Фотографии** — распознавание паспортов вакцинации и документов через Vision AI
- **Веб-панель** — дашборд с графиками веса, календарём событий и чатом с ассистентом
- **Ветеринарный отчёт** — генерация полного отчёта на любом языке мира
- **Экстренная карточка** — мгновенный доступ к критической информации по команде `/sos`
- **Экспорт/импорт** — полный бэкап и восстановление данных в JSON

## Технологии

| Слой | Стек |
|------|------|
| Backend | Python 3.11+, FastAPI, aiogram 3.x, SQLAlchemy 2.x async |
| Frontend | Vue 3, Vite, Tailwind CSS, DaisyUI |
| AI | OpenAI GPT (function calling), Whisper (голос), Vision (фото) |
| База данных | PostgreSQL 16, Alembic (миграции) |
| Инфраструктура | Docker Compose, GitHub Actions, APScheduler |

## Требования

- Python 3.11+
- Node.js 20+
- PostgreSQL 16 (или через Docker)
- ffmpeg
- Docker + Docker Compose (для продакшна)

## Быстрый старт

### Docker (рекомендуется)

```bash
git clone https://github.com/user/luna-the-dog.git
cd luna-the-dog
cp .env.example .env
# Заполнить .env реальными токенами

docker compose up -d
```

### Локальная разработка

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# PostgreSQL
docker compose up -d postgres
alembic upgrade head

# Запуск
uvicorn app.main:app --reload

# Frontend (в другом терминале)
cd frontend
npm ci
npm run dev
```

## Команды

| Команда | Описание |
|---------|----------|
| `uvicorn app.main:app --reload` | Dev-сервер backend |
| `npm run dev` | Dev-сервер frontend |
| `alembic upgrade head` | Применить миграции |
| `alembic revision --autogenerate -m "..."` | Новая миграция |
| `pytest` | Запуск тестов |
| `pytest --cov=app` | Тесты с покрытием |
| `ruff check . --fix` | Линтер с автофиксом |
| `ruff format .` | Форматирование |
| `mypy app/` | Проверка типов |
| `docker compose up -d` | Запуск продакшна |

## Качество кода и автопроверки

В проекте используется единый базовый цикл проверки качества перед коммитом:

- `ruff` как обязательный глобальный линтер
- `ruff-format` как обязательная проверка форматирования
- `mypy` как обязательная типизация для core-слоёв backend (`app/services`, `app/db`, `app/api/deps.py`)

Запуск из корня репозитория:

```bash
backend/.venv/bin/pre-commit run --all-files
```

Отдельно автотесты запускаются командой:

```bash
backend/.venv/bin/pytest backend/tests
```

Если нужно полное диагностическое типизирование backend (вне commit gate), используйте:

```bash
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend
```

## Структура проекта

```
backend/
  app/
    agent/          # AI-агент: мозг, инструменты, промпты, голос
    api/routers/    # REST API + WebSocket чат
    bot/            # Telegram-бот: хендлеры, мидлвари, клавиатуры
    db/models/      # SQLAlchemy-модели
    scheduler/      # Планировщик напоминаний
    services/       # Бизнес-логика
  alembic/          # Миграции БД
  tests/            # unit / integration / contract

frontend/
  src/
    components/     # Vue-компоненты
    pages/          # Страницы SPA
    services/       # API-клиент
```

## Лицензия

[MIT](LICENSE)
