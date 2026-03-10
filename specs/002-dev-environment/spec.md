# Feature Specification: Docker-Only Dev/Prod Orchestration

**Feature Branch**: `002-dev-environment`  
**Created**: 2026-03-09  
**Updated**: 2026-03-10  
**Status**: Draft  
**Input**: User description: "Перевести dev и prod на обязательный Docker-only запуск, добавить migrate-сервис перед app, исправить postgres healthcheck и убрать ручной шаг миграций."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — DEV запуск только через Docker (Priority: P1)

Разработчик запускает dev-окружение одной командой `docker compose -f docker-compose.dev.yml up` и сразу видит foreground-логи `app` и `postgres`. Бот работает через polling, hot reload включён.

**Why this priority**: Это основной daily-flow разработки; нельзя оставлять разночтения между локальным запуском и Docker-режимом.

**Independent Test**: Выполнить `docker compose -f docker-compose.dev.yml up` и убедиться, что после старта `migrate` поднимается `app`, бот работает через polling, а логи идут в текущий терминал.

**Acceptance Scenarios**:

1. **Given** задан `APP_ENV=dev`, **When** запускается `docker compose -f docker-compose.dev.yml up`, **Then** приложение работает через polling без webhook.
2. **Given** в `.env.dev` случайно указан `WEBHOOK_URL`, **When** стартует dev-режим, **Then** используется polling и `WEBHOOK_URL` игнорируется.
3. **Given** изменён Python-файл в `backend`, **When** dev-контейнер запущен, **Then** `uvicorn --reload` перезапускает приложение.

---

### User Story 2 — PROD запуск через Docker с webhook (Priority: P1)

Оператор запускает production через `docker compose up -d`. Приложение стартует только в webhook-режиме и не использует polling.

**Why this priority**: Production-контур должен быть предсказуемым и не зависеть от ручных шагов.

**Independent Test**: Выполнить `docker compose up -d` с валидным `.env.prod` и убедиться, что `app` стартует после `migrate`, а webhook-конфигурация валидируется.

**Acceptance Scenarios**:

1. **Given** `APP_ENV=prod` и задан `WEBHOOK_URL`, **When** выполняется `docker compose up -d`, **Then** приложение стартует в webhook-режиме.
2. **Given** `APP_ENV=prod` и `WEBHOOK_URL` не задан, **When** запускается контейнер приложения, **Then** старт завершается ошибкой валидации Settings.

---

### User Story 3 — Автоматическая инициализация БД (Priority: P1)

Миграции выполняются отдельным одноразовым контейнером `migrate` после готовности PostgreSQL, а `app` запускается только после успешного завершения миграций.

**Why this priority**: Устраняет ручной шаг инициализации схемы и убирает проблему старта на пустой БД.

**Independent Test**: На пустом volume выполнить `docker compose -f docker-compose.dev.yml up` и проверить порядок запуска: `postgres (healthy)` -> `migrate (exit 0)` -> `app (running)`.

**Acceptance Scenarios**:

1. **Given** пустая база, **When** запускается compose, **Then** `migrate` применяет `alembic upgrade head` до старта `app`.
2. **Given** миграции завершились с ошибкой, **When** `migrate` завершается с ненулевым кодом, **Then** `app` не стартует.

---

### User Story 4 — Корректный healthcheck PostgreSQL (Priority: P1)

Healthcheck должен проверять существующую БД окружения, а не имя пользователя, чтобы исключить ложные `FATAL: database "luna" does not exist`.

**Why this priority**: Неверный healthcheck ломает orchestration и маскирует реальное состояние БД.

**Independent Test**: Проверить `docker compose ... config` и runtime-логи: dev использует `-d luna_dev_db`, prod использует `-d luna_db`.

**Acceptance Scenarios**:

1. **Given** dev compose, **When** выполняется healthcheck, **Then** используется `pg_isready -U luna -d luna_dev_db`.
2. **Given** prod compose, **When** выполняется healthcheck, **Then** используется `pg_isready -U luna -d luna_db`.

---

### Edge Cases

- Если `WEBHOOK_URL` случайно задан в dev, приложение должно остаться в polling-режиме и не переключаться на webhook.
- Если `migrate` падает из-за недоступной БД или ошибки миграции, `app` не должен стартовать.
- Если `.env.prod` отсутствует или неполный, `docker compose up -d` должен завершаться с понятной ошибкой конфигурации.
- Первый запуск на пустом volume PostgreSQL должен проходить без ручного `docker compose exec app alembic upgrade head`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Система MUST использовать только Docker Compose для запуска приложения и в dev, и в prod.
- **FR-002**: Dev запуск MUST выполняться через `docker-compose.dev.yml` в polling-режиме с hot reload.
- **FR-003**: Prod запуск MUST выполняться через `docker-compose.yml` в webhook-режиме.
- **FR-004**: В dev режиме `WEBHOOK_URL` MUST игнорироваться, даже если переменная присутствует.
- **FR-005**: В prod режиме `WEBHOOK_URL` MUST быть обязательным.
- **FR-006**: В обоих compose MUST существовать сервис `migrate`, выполняющий `alembic upgrade head` после `postgres: healthy`.
- **FR-007**: Сервис `app` в обоих compose MUST зависеть от успешного завершения `migrate` (`service_completed_successfully`).
- **FR-008**: `postgres.healthcheck` MUST явно указывать БД окружения: `luna_dev_db` (dev) и `luna_db` (prod).
- **FR-009**: README и quickstart MUST описывать Docker-only happy path без команды ручного запуска приложения через `uvicorn`.
- **FR-010**: README и quickstart MUST исключать ручной шаг миграций из основного сценария.

### Key Entities

- **Compose Dev Stack**: `postgres` + `migrate` + `app` для polling/hot reload запуска.
- **Compose Prod Stack**: `postgres` + `migrate` + `app` для webhook запуска.
- **Migration Orchestrator**: одноразовый сервис `migrate`, который переводит БД в актуальное состояние перед стартом приложения.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `docker compose -f docker-compose.dev.yml up` на чистом окружении поднимает dev-стек без ошибки `database "luna" does not exist`.
- **SC-002**: В dev последовательность запуска соответствует `postgres (healthy)` -> `migrate (exit 0)` -> `app (running)`.
- **SC-003**: `docker compose up -d` в prod поднимает `app` только после успешных миграций.
- **SC-004**: В основном пользовательском пути нет команды `docker compose exec app alembic upgrade head`.
- **SC-005**: Документация `specs/002-dev-environment/*` и `README.md` не содержит требований запуска приложения вне Docker.

## Assumptions

- Сохраняются два отдельных Compose-файла: `docker-compose.dev.yml` и `docker-compose.yml`.
- `main.py` продолжает переключать режим работы по `APP_ENV` (`dev` -> polling, `prod` -> webhook).
- `.env.dev` и `.env.prod` остаются основными env-файлами для соответствующих Compose-режимов.
- `.env.example` сохраняется только как legacy fallback для совместимости Settings, но не как основной сценарий запуска.
