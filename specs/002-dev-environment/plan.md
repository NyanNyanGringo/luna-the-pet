# Implementation Plan: Docker-Only Dev/Prod Orchestration

**Branch**: `002-dev-environment` | **Date**: 2026-03-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/002-dev-environment/spec.md`

## Summary

Перевод запуска приложения на Docker-only модель для обоих режимов:
- dev: polling + hot reload + foreground логи через `docker-compose.dev.yml`
- prod: webhook через `docker-compose.yml`
- миграции: отдельный `migrate` сервис перед стартом `app`
- исправление healthcheck PostgreSQL с явным именем БД
- синхронизация README и всех артефактов `specs/002-dev-environment/*`

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, aiogram 3.x, SQLAlchemy async, Alembic  
**Storage**: PostgreSQL 16  
**Orchestration**: Docker Compose (dev/prod отдельными файлами)  
**Testing/Validation**: `docker compose config`, `pre-commit`, smoke проверки логов сервисов

## Constitution Check

Нарушений нет:
- self-hosted deployment через Docker сохранён;
- dev/prod контуры изолированы по env и поведению;
- UX разработки улучшен за счёт однозначного способа запуска.

## Project Structure

### Documentation

```text
specs/002-dev-environment/
├── plan.md
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── env-files.md
│   └── startup-behavior.md
└── tasks.md
```

### Source Files

```text
docker-compose.dev.yml     # DEV orchestration (postgres + migrate + app)
docker-compose.yml         # PROD orchestration (postgres + migrate + app)
README.md                  # Docker-only команды и сценарии
```

## Execution Plan

1. Обновить compose-файлы:
- добавить `migrate`;
- связать `app` с `migrate` через `service_completed_successfully`;
- исправить healthcheck с `-d`;
- в prod использовать `.env.prod`.

2. Синхронизировать документацию:
- убрать non-Docker запуск из README/quickstart;
- зафиксировать автоматические миграции;
- зафиксировать поведение `WEBHOOK_URL` в dev.

3. Синхронизировать спецификацию:
- обновить acceptance-критерии, требования и задачи под Docker-only.

4. Валидация:
- `docker compose -f docker-compose.dev.yml config`
- `docker compose config`
- `backend/.venv/bin/pre-commit run --all-files`

## Risks & Mitigations

- Риск: несогласованный env-файл для prod.
  Митигация: зафиксировать `env_file: .env.prod` и обновить quickstart.
- Риск: ложный статус healthcheck из-за неверной БД.
  Митигация: явный `-d luna_dev_db`/`-d luna_db`.
- Риск: запуск `app` до миграций.
  Митигация: strict dependency `app -> migrate (service_completed_successfully)`.
