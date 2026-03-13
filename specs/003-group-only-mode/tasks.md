# Tasks: Групповой режим работы бота

**Input**: Design documents from `/specs/003-group-only-mode/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Не включены в список задач (не запрошены явно в спецификации). TDD-цикл из AGENTS.md применяется на этапе имплементации каждой задачи.

**Organization**: Задачи сгруппированы по пользовательским историям из spec.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Может выполняться параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой пользовательской истории относится задача (US1, US2, US3, US4)
- Все пути относительно корня репозитория

## Path Conventions

- **Backend**: `backend/app/` — основной код приложения
- **Tests**: `backend/tests/` — тесты
- **Migrations**: `backend/alembic/versions/` — миграции БД

---

## Phase 1: Setup

**Purpose**: Подготовка инфраструктуры для мультитенантной модели

- [X] T001 Удалить ORM-модель `FamilyInvite` и связанную логику генерации инвайт-кодов из `backend/app/db/models/family.py`
- [X] T002 Удалить функции `create_invite`, `use_invite`, `revoke_invite` из `backend/app/services/family_service.py`
- [X] T003 Удалить обработку deep link инвайт-кодов из `backend/app/bot/handlers/start.py` (ветка `/start <invite_code>`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Новые модели данных, сервисный слой и реструктуризация роутеров — блокирует ВСЕ пользовательские истории

**⚠️ CRITICAL**: Никакая работа по US1–US4 не может начаться до завершения этой фазы

- [X] T004 [P] Создать ORM-модель `Workspace` (id, telegram_chat_id, title, is_active, created_at, updated_at) в `backend/app/db/models/workspace.py` согласно data-model.md
- [X] T005 [P] Создать ORM-модель `WorkspaceMember` (id, workspace_id FK, telegram_user_id, telegram_username, telegram_first_name, is_active, joined_at, left_at) с UNIQUE(workspace_id, telegram_user_id) в `backend/app/db/models/workspace.py`
- [X] T006 [P] Создать ORM-модель `WorkspaceSettings` (id, workspace_id FK UNIQUE, timezone, locale) в `backend/app/db/models/workspace.py`
- [X] T007 Обновить FK в модели `Pet`: заменить `family_id → Family.id` на `workspace_id → Workspace.id` в `backend/app/db/models/pet.py`
- [X] T008 Обновить модель `ConversationState`: добавить `workspace_id` FK на `Workspace.id`, сделать UNIQUE(telegram_user_id, workspace_id) в `backend/app/db/models/family.py` (или новый файл)
- [X] T009 Добавить `workspace_id` FK (nullable) в модель `ChangeLog` в `backend/app/db/models/audit.py`
- [X] T010 Удалить ORM-модели `Family`, `FamilyMember`, `FamilySettings` и ассоциативную таблицу `family_pet` из `backend/app/db/models/family.py`
- [X] T011 Обновить `backend/app/db/models/__init__.py` — экспортировать новые модели (Workspace, WorkspaceMember, WorkspaceSettings), убрать старые (Family, FamilyMember, FamilySettings, FamilyInvite)
- [X] T012 Создать Alembic-миграцию: новые таблицы workspace, workspace_member, workspace_settings; обновлённые FK в pet, conversation_state, change_log; удаление таблиц family_invite, family_pet, family_settings, family в `backend/alembic/versions/`
- [X] T013 Создать `backend/app/services/workspace_service.py` с функциями: `get_or_create_workspace(session, telegram_chat_id, title)`, `deactivate_workspace(session, telegram_chat_id)`, `reactivate_workspace(session, telegram_chat_id, title)`, `get_workspace_by_chat_id(session, telegram_chat_id)`
- [X] T014 Добавить функции работы с участниками в `backend/app/services/workspace_service.py`: `add_or_reactivate_member(session, workspace_id, telegram_user_id, username, first_name)`, `deactivate_member(session, workspace_id, telegram_user_id)`, `get_user_workspaces(session, telegram_user_id)`, `get_member(session, workspace_id, telegram_user_id)`
- [X] T015 Добавить функцию миграции chat_id в `backend/app/services/workspace_service.py`: `update_chat_id(session, old_chat_id, new_chat_id)`
- [X] T016 Разделить роутеры в `backend/app/bot/create.py`: создать `private_router` с фильтром `F.chat.type == ChatType.PRIVATE` и `group_router` с фильтром `F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})`. Зарегистрировать оба в диспетчере
- [X] T017 Обновить `backend/app/main.py`: передать `allowed_updates=dp.resolve_used_update_types()` в `_start_polling()` и `_setup_webhook()` для получения событий `chat_member` и `my_chat_member`
- [X] T018 Удалить или рефакторить `backend/app/services/family_service.py` — убрать всю логику связанную с Family/FamilyMember (регистрация через `/start`, создание семьи), оставить только то, что не покрывает workspace_service

**Checkpoint**: Фундамент готов — можно начинать реализацию пользовательских историй

---

## Phase 3: User Story 1 — Бот отклоняет личные сообщения (Priority: P1) 🎯 MVP

**Goal**: Любое сообщение в личный чат бота получает ответ с инструкцией по созданию группы. Бот НЕ обрабатывает содержимое сообщений в private chat.

**Independent Test**: Написать боту в личный чат текст / голос / команду. Получить инструкцию. Убедиться, что бот не транскрибировал голос и не передал сообщение агенту.

### Implementation for User Story 1

- [X] T019 [US1] Вынести тексты ответов в конфигурацию: создать константы для инструкции по созданию группы, сообщения «работаю только в группе», шаблона списка групп в `backend/app/bot/handlers/constants.py` (или в config) согласно contracts/telegram-bot-commands.md
- [X] T020 [US1] Реализовать обработчик `/start` для private chat в `backend/app/bot/handlers/start.py`: отвечает приветствием + инструкцией по созданию группы (сценарий приёмки 3). Зарегистрировать в `private_router`
- [X] T021 [US1] Реализовать обработчик `/help` для private chat в `backend/app/bot/handlers/start.py`: стандартная справка + инструкция по группе. Зарегистрировать в `private_router`
- [X] T022 [US1] Реализовать catch-all обработчик для private chat в `backend/app/bot/handlers/message.py`: на любое сообщение (текст, голос, фото, стикер, команды кроме /start и /help) — определить количество workspace'ов пользователя через `get_user_workspaces()` и ответить соответствующим сообщением (0 групп → инструкция; 1 группа → ссылка; N групп → список). Зарегистрировать в `private_router`

**Checkpoint**: US1 полностью функционален. Личные сообщения отклоняются с корректной инструкцией.

---

## Phase 4: User Story 2 — Бот привязывается к группе при добавлении (Priority: P2)

**Goal**: При добавлении бота в группу автоматически создаётся workspace. Бот обрабатывает сообщения в группе, данные изолированы по workspace'ам. При удалении бота — workspace деактивируется.

**Independent Test**: Создать группу, добавить бота → приветствие. Отправить сообщение → обработка. Создать вторую группу → независимая работа. Удалить бота из группы → остановка. Добавить обратно → данные на месте.

### Implementation for User Story 2

- [X] T023 [US2] Создать `backend/app/bot/handlers/group_events.py` с обработчиком `on_bot_added`: при событии `my_chat_member` (IS_NOT_MEMBER >> IS_MEMBER) для групп — вызвать `get_or_create_workspace()`, добавить пользователя-инициатора через `add_or_reactivate_member()`, отправить приветственное сообщение согласно контракту
- [X] T024 [US2] Добавить обработчик `on_bot_removed` в `backend/app/bot/handlers/group_events.py`: при событии `my_chat_member` (IS_MEMBER >> IS_NOT_MEMBER) — вызвать `deactivate_workspace()`
- [X] T025 [US2] Обновить `AuthMiddleware` в `backend/app/bot/middlewares/auth.py`: для групповых сообщений — определить workspace по `chat_id`, проверить `workspace.is_active`, выполнить ленивую регистрацию участника (add_or_reactivate_member если не существует). Передать `workspace` и `member` в data handler'а
- [X] T026 [US2] Обновить обработчик текстовых сообщений в `backend/app/bot/handlers/message.py` для group_router: извлечь `workspace` из data (переданного middleware), передать `workspace.id` в `run_agent()` вместо `family_id`
- [X] T027 [US2] Обновить обработчик голосовых сообщений в `backend/app/bot/handlers/message.py` для group_router: аналогично T026, передать `workspace.id` в агент
- [X] T028 [US2] Обновить `run_agent()` в `backend/app/agent/brain.py`: заменить параметр `family_id` на `workspace_id`. Обновить `build_system_prompt()` для загрузки данных питомцев по workspace_id. Обновить `ConversationState` lookup по `(user_id, workspace_id)`
- [X] T029 [US2] Зарегистрировать роутер group_events в диспетчере в `backend/app/bot/create.py`. Убедиться, что обработчики `my_chat_member` корректно зарегистрированы
- [X] T030 [US2] Добавить обработчик миграции группы в супергруппу в `backend/app/bot/handlers/group_events.py`: при получении сообщения с `migrate_to_chat_id` — вызвать `update_chat_id(old_chat_id, new_chat_id)` для атомарного обновления workspace

**Checkpoint**: US2 полностью функционален. Бот создаёт workspace при добавлении в группу, обрабатывает сообщения через агент с workspace-контекстом, деактивируется при удалении.

---

## Phase 5: User Story 3 — Команда /invite выдаёт ссылку на группу (Priority: P3)

**Goal**: Команда `/invite` в группе генерирует пригласительную ссылку через Telegram API. При отсутствии прав админа — информативное сообщение.

**Independent Test**: Отправить `/invite` в группе (бот — админ) → получить ссылку. Отправить `/invite` (бот — не админ) → сообщение о необходимости прав. Отправить `/invite` в личный чат → перенаправление в группу.

### Implementation for User Story 3

- [X] T031 [US3] Переделать обработчик `/invite` в `backend/app/bot/handlers/commands.py`: для group_router — вызвать `bot.create_chat_invite_link(chat_id, name="Luna Bot Invite")`, вернуть ссылку. Обернуть в try/except `TelegramBadRequest` — при ошибке прав отправить сообщение согласно контракту
- [X] T032 [US3] Убрать импорты и использование `FamilyInvite`, `create_invite` из `backend/app/bot/handlers/commands.py`

**Checkpoint**: US3 полностью функционален. `/invite` генерирует ссылку на группу или сообщает о необходимости прав.

---

## Phase 6: User Story 4 — Автоматическая регистрация новых участников (Priority: P4)

**Goal**: При вступлении нового пользователя в группу бот автоматически регистрирует его как члена workspace. При выходе — деактивирует. Ленивая регистрация как fallback.

**Independent Test**: Добавить нового пользователя в группу → автоматическая регистрация (без сообщения). Пользователь отправляет сообщение → обработка. Пользователь покидает группу → доступ прекращён.

### Implementation for User Story 4

- [X] T033 [US4] Добавить обработчик `on_user_joined` в `backend/app/bot/handlers/group_events.py`: при событии `chat_member` (IS_NOT_MEMBER >> IS_MEMBER) — определить workspace по `chat_id`, вызвать `add_or_reactivate_member()`. Молчаливая регистрация (без сообщения в чат)
- [X] T034 [US4] Добавить обработчик `on_user_left` в `backend/app/bot/handlers/group_events.py`: при событии `chat_member` (IS_MEMBER >> IS_NOT_MEMBER) — вызвать `deactivate_member(workspace_id, telegram_user_id)`

**Checkpoint**: US4 полностью функционален. Новые участники автоматически регистрируются, выходящие — деактивируются.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Очистка, обновление тестов, валидация

- [X] T035 [P] Обновить существующие тесты: `backend/tests/test_family_service.py` → адаптировать или удалить (заменён workspace_service), `backend/tests/test_handlers_start.py` → обновить для нового поведения /start
- [X] T036 [P] Обновить существующие тесты: `backend/tests/test_models.py` и `backend/tests/test_us1_models.py` → обновить для новых моделей Workspace/WorkspaceMember, убрать Family/FamilyInvite
- [X] T037 [P] Обновить `backend/tests/test_us1_agent.py` → заменить `family_id` на `workspace_id` в вызовах `run_agent()`
- [X] T038 Удалить файл `backend/app/services/family_service.py` если вся логика перенесена в workspace_service и не осталось зависимостей
- [X] T039 Запустить `backend/.venv/bin/pre-commit run --all-files` и исправить все ошибки ruff/mypy
- [ ] T040 Выполнить smoke test по quickstart.md: dev-окружение → личный чат → группа → /invite → новый участник

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Нет зависимостей — удаление устаревшего кода
- **Foundational (Phase 2)**: Зависит от Phase 1 — БЛОКИРУЕТ все user stories
- **US1 (Phase 3)**: Зависит от Phase 2 (нужны модели Workspace, workspace_service, private_router)
- **US2 (Phase 4)**: Зависит от Phase 2 (нужны модели, сервисы, group_router, allowed_updates)
- **US3 (Phase 5)**: Зависит от Phase 2 (нужен group_router). Рекомендуется после US2 (workspace должен существовать)
- **US4 (Phase 6)**: Зависит от Phase 2 (нужны модели, сервисы). Рекомендуется после US2 (workspace должен существовать)
- **Polish (Phase 7)**: Зависит от завершения всех user stories

### User Story Dependencies

- **US1 (P1)**: Может начинаться сразу после Phase 2. Независим от других US
- **US2 (P2)**: Может начинаться сразу после Phase 2. Независим от US1, но рекомендуется для контекста
- **US3 (P3)**: Может начинаться после Phase 2, но логически завязан на US2 (workspace уже должен быть создан для группы)
- **US4 (P4)**: Может начинаться после Phase 2, но логически завязан на US2 (workspace уже должен быть создан для группы)

### Within Each User Story

- Модели → сервисы → обработчики → middleware → интеграция
- Каждая история завершается checkpoint'ом и может быть протестирована независимо

### Parallel Opportunities

**Phase 1** (все задачи T001–T003 могут выполняться параллельно — разные файлы):
```
T001 (models/family.py) || T002 (services/family_service.py) || T003 (handlers/start.py)
```

**Phase 2** (модели параллельно, затем сервисы):
```
T004 (Workspace) || T005 (WorkspaceMember) || T006 (WorkspaceSettings) — параллельно
T007 (Pet FK) || T008 (ConversationState) || T009 (ChangeLog) — параллельно после T004
T013 + T014 + T015 — последовательно (один файл workspace_service.py)
T016 (create.py) || T017 (main.py) — параллельно
```

**US1 + US2** (после Phase 2 — можно параллельно):
```
US1 (T019–T022, private_router) || US2 (T023–T030, group_router + middleware)
```

**US3 + US4** (после US2 — можно параллельно):
```
US3 (T031–T032, commands.py) || US4 (T033–T034, group_events.py)
```

---

## Parallel Example: Phase 2 Foundation

```bash
# Параллельно: создание моделей (разные файлы/секции)
Task T004: "Создать ORM-модель Workspace в backend/app/db/models/workspace.py"
Task T005: "Создать ORM-модель WorkspaceMember в backend/app/db/models/workspace.py"
Task T006: "Создать ORM-модель WorkspaceSettings в backend/app/db/models/workspace.py"

# После моделей: обновление FK (разные файлы)
Task T007: "Обновить FK в Pet — backend/app/db/models/pet.py"
Task T008: "Обновить ConversationState — backend/app/db/models/family.py"
Task T009: "Добавить workspace_id в ChangeLog — backend/app/db/models/audit.py"

# Затем: инфраструктура (разные файлы)
Task T016: "Разделить роутеры в backend/app/bot/create.py"
Task T017: "Обновить allowed_updates в backend/app/main.py"
```

## Parallel Example: US1 + US2

```bash
# US1 (private_router — только start.py и message.py для private):
Task T020: "Обработчик /start для private в backend/app/bot/handlers/start.py"
Task T022: "Catch-all для private в backend/app/bot/handlers/message.py"

# US2 (group_router — group_events.py, auth.py, brain.py):
Task T023: "on_bot_added в backend/app/bot/handlers/group_events.py"
Task T025: "AuthMiddleware для групп в backend/app/bot/middlewares/auth.py"
Task T028: "workspace_id в run_agent() — backend/app/agent/brain.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (удаление устаревшего кода)
2. Complete Phase 2: Foundational (модели, сервисы, роутеры)
3. Complete Phase 3: US1 (private chat rejection)
4. **STOP and VALIDATE**: Бот отклоняет все личные сообщения с инструкцией
5. Deploy если готов — бот уже полезен как gate для группового режима

### Incremental Delivery

1. Phase 1 + Phase 2 → Фундамент готов
2. +US1 → Личные сообщения отклоняются → Deploy (MVP!)
3. +US2 → Бот работает в группах, создаёт workspace'ы → Deploy
4. +US3 → `/invite` выдаёт ссылку → Deploy
5. +US4 → Авто-регистрация при вступлении → Deploy
6. Phase 7 → Polish → Final Deploy

### Single Developer Strategy

1. Phase 1 → Phase 2 → Phase 3 (US1) → Phase 4 (US2) → Phase 5 (US3) → Phase 6 (US4) → Phase 7
2. Каждая фаза завершается checkpoint'ом и валидацией

---

## Notes

- [P] задачи = разные файлы, нет зависимостей
- [Story] метка привязывает задачу к пользовательской истории
- Каждая US может быть протестирована независимо после завершения
- Commit после каждой задачи или логической группы
- Старые таблицы (family, family_member и т.д.) удаляются через Alembic-миграцию — обратного пути нет
- Миграция существующих данных НЕ входит в scope (указано в spec.md)
