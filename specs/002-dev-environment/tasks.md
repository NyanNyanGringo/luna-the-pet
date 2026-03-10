# Tasks: Docker-Only Dev/Prod Orchestration

**Input**: `/specs/002-dev-environment/*`  
**Prerequisites**: `spec.md`, `plan.md`, `contracts/*`

## Phase 1: Compose orchestration

- [x] T001 Обновить `docker-compose.dev.yml`: добавить `migrate`, исправить `postgres.healthcheck` на `pg_isready -U luna -d luna_dev_db`.
- [x] T002 Обновить `docker-compose.dev.yml`: изменить `app.depends_on` на `migrate` с `condition: service_completed_successfully`.
- [x] T003 Обновить `docker-compose.yml`: добавить `migrate`, исправить `postgres.healthcheck` на `pg_isready -U luna -d luna_db`.
- [x] T004 Обновить `docker-compose.yml`: изменить `app.depends_on` на `migrate` с `condition: service_completed_successfully`.
- [x] T005 Обновить `docker-compose.yml`: перевести `app`/`migrate` на `env_file: .env.prod`.

## Phase 2: Документация Docker-only

- [x] T006 Обновить `README.md`: убрать happy path запуска приложения вне Docker.
- [x] T007 Обновить `README.md`: убрать ручную миграцию из основного сценария.
- [x] T008 Обновить `README.md`: зафиксировать команды dev/prod и просмотр логов для detached запуска.
- [x] T009 Обновить `README.md`: явно указать, что в dev `WEBHOOK_URL` игнорируется.

## Phase 3: Синхронизация `specs/002-dev-environment/*`

- [x] T010 Обновить `spec.md` под Docker-only user stories и acceptance criteria.
- [x] T011 Обновить `quickstart.md` на Docker-only шаги для dev/prod.
- [x] T012 Обновить `contracts/env-files.md` и `contracts/startup-behavior.md`.
- [x] T013 Обновить `research.md`, `data-model.md`, `plan.md`.
- [x] T014 Обновить `checklists/requirements.md` под новую модель.

## Phase 4: Валидация

- [ ] T015 DEV smoke: `docker compose -f docker-compose.dev.yml up` на реальном `.env.dev`.
- [ ] T016 PROD smoke: `docker compose up -d` на реальном `.env.prod`.
- [ ] T017 Проверить runtime-порядок: `postgres -> migrate -> app` в обоих режимах.
- [x] T018 Проверка конфигурации: `docker compose -f docker-compose.dev.yml config` и `docker compose config`.
- [x] T019 Обязательная финальная проверка: `backend/.venv/bin/pre-commit run --all-files`.
