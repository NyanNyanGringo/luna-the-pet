# Tasks: Удаление функционала OAuth

**Input**: Design documents from `/specs/005-remove-oauth/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Не запрошены в спецификации. Тестовые задачи не включены.

**Organization**: Задачи сгруппированы по пользовательским историям. US1 и US2 — обе P1, но US1 (работоспособность бота) выполняется первой, так как это основная проверка сохранности функциональности.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой пользовательской истории относится задача (US1, US2, US3, US4)
- Точные пути к файлам указаны в описании каждой задачи

---

## Phase 1: Setup

**Purpose**: Предварительная проверка перед началом удаления

- [x] T001 Проверить текущее состояние проекта: убедиться, что `pytest` проходит, `ruff check .` чист, приложение запускается без ошибок. Зафиксировать baseline-состояние

---

## Phase 2: Foundational (Удаление ядра OAuth)

**Purpose**: Удаление центральных OAuth-компонентов, от которых зависят все остальные задачи

**⚠️ КРИТИЧНО**: Эти задачи снимают OAuth-сервис и эндпоинт — основу всего OAuth-потока. После этой фазы приложение должно запускаться, используя только API-ключ.

- [x] T002 Удалить файл `backend/app/services/openai_auth_service.py` целиком (736 строк — PKCE, обмен токенов, шифрование, рефреш, get_openai_client)
- [x] T003 [P] Удалить файл `backend/app/api/auth.py` целиком (OAuth callback эндпоинт `GET /api/auth/openai/callback`)
- [x] T004 Очистить `backend/app/main.py`: удалить импорт `auth_router` (строка 16) и регистрацию `app.include_router(auth_router)` (строка 151). НЕ трогать остальные роутеры и эндпоинты (`/webhook`, `/api/health`)
- [x] T005 Рефакторинг `backend/app/agent/brain.py`: заменить вызов `get_openai_client(session, member_id)` (строка 53) на прямое создание `AsyncOpenAI(api_key=settings.OPENAI_API_KEY)`. Удалить импорт `get_openai_client` (строка 21). Упростить сигнатуру вызывающей функции, если параметры `session`/`member_id` более не нужны для создания клиента

**Checkpoint**: Приложение запускается без ошибок импорта, бот отвечает на сообщения через API-ключ

---

## Phase 3: User Story 1 + User Story 2 — Работоспособность бота и очистка кода (Priority: P1)

**Goal**: Бот работает исключительно через API-ключ. Все OAuth-артефакты удалены из кодовой базы без остаточных ссылок.

**Independent Test (US1)**: Запустить бота с `OPENAI_API_KEY`, отправить сообщение — бот отвечает.
**Independent Test (US2)**: `grep -r "oauth\|connectai\|PKCE\|code_verifier\|OAUTH_ENCRYPTION" backend/app/` возвращает 0 результатов.

### Удаление Telegram-команды

- [x] T006 [US1] Удалить обработчик `handle_connectai()` (строки 31-64) и его регистрацию `router.message.register(handle_connectai, ...)` (строка 170) в `backend/app/bot/handlers/commands.py`. Удалить ставшие ненужными импорты. НЕ трогать `/help` (строка 169) и `/invite` (строка 171)

### Удаление модели данных

- [x] T007 [P] [US2] Удалить класс `OAuthCredential` (строки 28-77) из `backend/app/db/models/family.py`. Оставить класс `ConversationState` (строки 83-140) нетронутым. Убрать импорты, ставшие ненужными после удаления модели
- [x] T008 [US2] Удалить импорт и экспорт `OAuthCredential` из `backend/app/db/models/__init__.py` (строка 10). Убедиться, что `ConversationState` по-прежнему экспортируется

### Очистка конфигурации

- [x] T009 [P] [US2] Удалить поля `OPENAI_OAUTH_CLIENT_ID` (строка 79) и `OAUTH_ENCRYPTION_KEY` (строка 80) из класса `Settings` в `backend/app/config.py`. Удалить связанные комментарии (строки 56-57, 78). НЕ трогать `OPENAI_API_KEY`, `JWT_SECRET` и остальные поля
- [x] T010 [P] [US2] Удалить строки с `OPENAI_OAUTH_CLIENT_ID` (строка 12) и `OAUTH_ENCRYPTION_KEY` (строка 13) из `.env.example`. НЕ трогать `.env.dev.example` и `.env.prod.example` (в них OAuth-переменных нет)

### Очистка зависимостей

- [x] T011 [US2] Удалить `cryptography>=44.0.0` (строка 36) и `httpx>=0.28.0` (строка 31) из `backend/requirements.txt`. Оставить `python-jose[cryptography]>=3.3.0` (строка 34) — используется для JWT-авторизации API

### Очистка тестов

- [x] T012 [P] [US2] Удалить файл `backend/tests/unit/test_openai_auth.py` целиком (тесты исключительно OAuth-функциональности)
- [x] T013 [P] [US2] Удалить `"OPENAI_OAUTH_CLIENT_ID"` и `"OAUTH_ENCRYPTION_KEY"` из списка `_OPTIONAL_ENV_VARIABLES` (строки 32-33) в `backend/tests/unit/conftest.py`
- [x] T014 [US2] Удалить OAuth-специфичные тест-методы из `backend/tests/unit/test_config.py` (тесты полей `OPENAI_OAUTH_CLIENT_ID` и `OAUTH_ENCRYPTION_KEY`). Оставить тесты остальных полей конфигурации

**Checkpoint**: Кодовая база полностью очищена от OAuth. Бот работает через API-ключ. Поиск по OAuth-ключевым словам в `backend/app/` возвращает 0 результатов.

---

## Phase 4: User Story 4 — Миграция базы данных (Priority: P2)

**Goal**: Таблица `oauth_credential` удалена из БД через обратимую Alembic-миграцию.

**Independent Test**: `alembic upgrade head` выполняется без ошибок, таблица `oauth_credential` отсутствует, остальные таблицы на месте.

- [x] T015 [US4] Создать Alembic-миграцию вручную: `alembic revision -m "drop_oauth_credential_table"` в `backend/alembic/versions/`. В `upgrade()`: `op.drop_table('oauth_credential')`. В `downgrade()`: воссоздать таблицу с полной схемой из data-model.md (id, telegram_user_id, provider, access_token_enc, refresh_token_enc, expires_at, status, created_at, updated_at + UniqueConstraint на telegram_user_id+provider). НЕ редактировать существующие миграции

**Checkpoint**: Миграция работает в обоих направлениях (upgrade/downgrade)

---

## Phase 5: User Story 3 + Polish — Верификация и финальная проверка (Priority: P1)

**Purpose**: Подтвердить, что JWT-авторизация API работает, и провести полную верификацию очистки

**Goal (US3)**: JWT Bearer-аутентификация в `deps.py` работает без регрессий.

**Independent Test (US3)**: Запрос к защищённому эндпоинту с валидным JWT — ответ 200; без токена — ответ 401.

- [x] T016 [US3] Верифицировать JWT-авторизацию: убедиться, что `backend/app/api/deps.py` НЕ был изменён в ходе удаления OAuth. Проверить что `get_current_user()` работает — функция использует `jose.jwt.decode()` с `JWT_SECRET` и не зависит от OAuth-компонентов. Если deps.py был случайно затронут — восстановить
- [x] T017 Выполнить полный поиск по ключевым словам OAuth в рабочем коде (исключая `specs/`, `alembic/versions/`, `.git/`): `oauth`, `connectai`, `PKCE`, `code_verifier`, `authorization_code`, `OPENAI_OAUTH_CLIENT_ID`, `OAUTH_ENCRYPTION_KEY`, `openai_auth_service`, `OAuthCredential`, `auth_router`. При нахождении — очистить оставшиеся ссылки
- [x] T018 Запустить `pytest` — все оставшиеся тесты должны пройти (0 падений). Запустить `ruff check .` — 0 ошибок линтера. Исправить любые проблемы, найденные на этом шаге

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Нет зависимостей — начинается немедленно
- **Foundational (Phase 2)**: Зависит от Phase 1. T002 и T003 параллельны. T004 зависит от T003 (удаление auth.py). T005 зависит от T002 (удаление openai_auth_service.py)
- **US1+US2 (Phase 3)**: Зависит от Phase 2. Многие задачи параллельны (T007, T009, T010, T012, T013 — разные файлы)
- **US4 (Phase 4)**: Зависит от T007 (удаление модели OAuthCredential из кода)
- **US3+Polish (Phase 5)**: Зависит от всех предыдущих фаз

### User Story Dependencies

- **US1 (P1)**: Основная зависимость — T002 (удаление OAuth-сервиса) и T005 (рефакторинг brain.py)
- **US2 (P1)**: Зависит от US1 (сначала удалить ядро, потом чистить хвосты). Задачи внутри US2 во многом параллельны
- **US3 (P1)**: Верификационная история — выполняется после всех изменений, чтобы подтвердить отсутствие регрессий
- **US4 (P2)**: Независима от US3, но зависит от T007 (удаление модели из кода до создания миграции)

### Parallel Opportunities

**В Phase 2**:
```
Параллельно: T002 (openai_auth_service.py) + T003 (auth.py)
Затем: T004 (main.py) + T005 (brain.py)
```

**В Phase 3**:
```
Параллельно: T007 (family.py) + T009 (config.py) + T010 (.env.example) + T012 (test_openai_auth.py) + T013 (conftest.py)
Затем: T008 (__init__.py, после T007) + T011 (requirements.txt) + T014 (test_config.py)
```

---

## Implementation Strategy

### MVP First (US1 — Бот работает через API-ключ)

1. Завершить Phase 1: Setup (T001)
2. Завершить Phase 2: Foundational (T002-T005)
3. **СТОП и ВАЛИДАЦИЯ**: Бот отвечает на сообщения через API-ключ
4. Продолжить если всё работает

### Incremental Delivery

1. Phase 1 + Phase 2 → Бот работает через API-ключ (MVP!)
2. Phase 3 → Кодовая база полностью очищена
3. Phase 4 → БД очищена
4. Phase 5 → Финальная верификация, готово к мёржу

---

## Notes

- Это задача на удаление кода — порядок критически важен, чтобы не сломать зависимости
- **НЕ ТРОГАТЬ**: `backend/app/api/deps.py` (JWT-авторизация), `python-jose` (зависимость для JWT), `OPENAI_API_KEY`, `JWT_SECRET`
- Старые миграции в `alembic/versions/` НЕ редактировать — только создать новую
- Задачи [P] можно выполнять параллельно только в рамках одной фазы
- После каждого checkpoint — коммит
