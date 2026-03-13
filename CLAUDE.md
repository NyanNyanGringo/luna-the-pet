# ИНСТРУКЦИИ ОТ ПОЛЬЗОВАТЕЛЯ
- Прочитай файл AGENTS.md и следуй инструкциям из него во время выполнения задач.

# luna_the_dog Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-07

## Active Technologies
- Python 3.11+ + FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, Pydantic Settings >=2.7.0 (002-dev-environment)
- PostgreSQL 16 (asyncpg) (002-dev-environment)
- Python 3.11+ + FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, Pydantic Settings >=2.7.0, OpenAI SDK, APScheduler 3.x (003-group-only-mode)
- PostgreSQL 16 (asyncpg), Alembic для миграций (003-group-only-mode)

- Python 3.11+, FastAPI, aiogram 3.x, SQLAlchemy 2.x async, Alembic (001-pet-care-assistant)
- Vue 3 (Vite), Tailwind CSS, DaisyUI (frontend)
- PostgreSQL 16, APScheduler 3.x, OpenAI API (infrastructure)
- Ruff, mypy, pytest, pre-commit (tooling)

## Project Structure

```text
backend/app/         # FastAPI + aiogram + agent
frontend/src/        # Vue 3 SPA
tests/               # pytest
alembic/             # DB migrations
.github/workflows/   # CI/CD
```

## Commands

```bash
# Dev server
uvicorn backend.app.main:app --reload

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Testing
pytest
pytest --cov=app

# Linting
ruff check . --fix
ruff format .
mypy app/
```

## Code Style

Python: Ruff (line-length=88, target=py311), mypy strict mode
Frontend: Vue 3 Composition API, Tailwind CSS utilities
All non-code text MUST be in Russian (docs, comments, commits)

## Recent Changes
- 003-group-only-mode: Added Python 3.11+ + FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, Pydantic Settings >=2.7.0, OpenAI SDK, APScheduler 3.x
- 002-dev-environment: Added Python 3.11+ + FastAPI >=0.115.0, aiogram >=3.15.0, SQLAlchemy[asyncio] >=2.0.36, Pydantic Settings >=2.7.0

- 001-pet-care-assistant: Plan completed (research, data-model, contracts, quickstart)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
