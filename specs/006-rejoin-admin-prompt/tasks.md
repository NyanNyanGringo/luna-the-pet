# Tasks: Приветствие при возвращении бота и напоминание о правах администратора

**Input**: Design documents from `/specs/006-rejoin-admin-prompt/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Включены — проект требует цикл «тесты → код → ревью» (AGENTS.md).

**Organization**: Задачи сгруппированы по user story для независимой реализации и тестирования.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно запускать параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой user story относится задача (US1, US2)
- Указаны точные пути файлов

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Изменение сигнатуры `get_or_create_workspace` для возврата флага `is_new` — блокирует US1.

- [x] T001 Изменить `get_or_create_workspace` в `backend/app/services/workspace_service.py`: возвращать `tuple[Workspace, bool]` вместо `Workspace`. Все три пути (`_create_workspace_with_settings` → `is_new=True`, `_ensure_workspace_active` → `is_new=False`, `_adopt_legacy_workspace` → `is_new=False`) должны корректно выставлять флаг. Обновить `_get_workspace_after_integrity_error` аналогично.
- [x] T002 Обновить вызов `get_or_create_workspace` в `backend/app/bot/handlers/group_events.py`: распаковать `(workspace, is_new)` в `handle_bot_membership_update` (строка 46-48). Пока использовать только `workspace` — поведение не меняется.
- [x] T003 Обновить существующие тесты (если есть) для `get_or_create_workspace`, чтобы они проверяли новый возвращаемый тип `tuple[Workspace, bool]`. Найти тесты через `tests/` и убедиться, что `is_new=True` для нового workspace и `is_new=False` для реактивированного.

**Checkpoint**: Код компилируется и работает как прежде, `get_or_create_workspace` возвращает tuple.

---

## Phase 2: User Story 1 — Возвращение бота в группу (Priority: P1) 🎯 MVP

**Goal**: При повторном добавлении бота в группу отправляется специальное приветствие возвращения с просьбой о правах администратора. Если бот уже админ — приветствие адаптируется.

**Independent Test**: Удалить бота из группы и добавить обратно — должно появиться приветствие возвращения с просьбой об админ-правах.

### Tests for User Story 1

- [x] T004 [P] [US1] Написать тесты для выбора приветственного сообщения в `tests/unit/test_group_events.py`: (1) `is_new=True` → `GROUP_WELCOME_TEXT`, (2) `is_new=False` + не админ → `GROUP_REJOIN_TEXT`, (3) `is_new=False` + админ → `GROUP_REJOIN_ADMIN_TEXT`. Замокать `bot.get_chat_member` и `workspace_service.get_or_create_workspace`.
- [x] T005 [P] [US1] Написать тесты для проверки содержимого констант в `tests/unit/test_constants.py`: `GROUP_REJOIN_TEXT` содержит слово «админ» (или «администратор»), `GROUP_REJOIN_ADMIN_TEXT` не содержит просьбу о правах, оба сообщения укладываются в 2-3 предложения.

### Implementation for User Story 1

- [x] T006 [P] [US1] Добавить константы `GROUP_REJOIN_TEXT` и `GROUP_REJOIN_ADMIN_TEXT` в `backend/app/bot/handlers/constants.py`. `GROUP_REJOIN_TEXT`: компактное тёплое сообщение от Луны с просьбой о правах админа (2-3 предложения, тон: «рада вернуться», объяснение зачем нужны права — доступ к истории). `GROUP_REJOIN_ADMIN_TEXT`: аналогично, но без просьбы о правах (подтверждение что всё в порядке).
- [x] T007 [US1] Добавить асинхронную функцию проверки admin-статуса бота в `backend/app/bot/handlers/group_events.py`: вызов `bot.get_chat_member(chat_id=chat_id, user_id=bot.id)`, проверка `status in ("administrator", "creator")`, обработка исключений (при ошибке считать что не админ).
- [x] T008 [US1] Обновить логику `handle_bot_membership_update` в `backend/app/bot/handlers/group_events.py`: использовать `is_new` для выбора между первичным и rejoin приветствием. Для rejoin — вызвать проверку admin-статуса и выбрать `GROUP_REJOIN_TEXT` или `GROUP_REJOIN_ADMIN_TEXT`. Добавить `Bot` в параметры хендлера (aiogram инжектит автоматически). Обновить импорты из `constants.py`.
- [x] T009 [US1] Запустить тесты `pytest tests/unit/test_group_events.py tests/unit/test_constants.py -v` и убедиться что все проходят.

**Checkpoint**: При повторном добавлении бота отправляется приветствие возвращения. При первом — стандартное. Admin-статус влияет на текст.

---

## Phase 3: User Story 2 — Просьба о правах администратора в инструкциях (Priority: P2)

**Goal**: Все инструкционные и справочные сообщения в группе содержат напоминание о необходимости прав администратора.

**Independent Test**: Вызвать `/help` в группе — сообщение содержит упоминание прав администратора. Добавить бота в новую группу — первичное приветствие содержит просьбу о правах.

### Tests for User Story 2

- [x] T010 [P] [US2] Дополнить тесты в `tests/unit/test_constants.py`: `GROUP_WELCOME_TEXT` содержит упоминание необходимости прав администратора, `HELP_GROUP_TEXT` содержит упоминание необходимости прав администратора.

### Implementation for User Story 2

- [x] T011 [P] [US2] Обновить `GROUP_WELCOME_TEXT` в `backend/app/bot/handlers/constants.py`: добавить строку о необходимости назначить бота администратором (объяснить зачем — для полноценной работы). Сохранить текущую структуру и тон сообщения.
- [x] T012 [P] [US2] Обновить `HELP_GROUP_TEXT` в `backend/app/bot/handlers/constants.py`: добавить строку-напоминание о необходимости прав администратора. Сохранить текущий формат списка команд.
- [x] T013 [US2] Запустить тесты `pytest tests/unit/test_constants.py -v` и убедиться что все проходят.

**Checkpoint**: Первичное приветствие и справка в группе содержат упоминание прав администратора.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Финальная проверка и валидация

- [x] T014 Запустить `backend/.venv/bin/pre-commit run --all-files` и исправить все замечания
- [x] T015 Запустить полный набор тестов `pytest tests/ -v` и убедиться что ничего не сломано
- [x] T016 Валидация по quickstart.md: проверить что все 3 затронутых файла изменены корректно

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: Нет зависимостей — начинается сразу
- **User Story 1 (Phase 2)**: Зависит от Phase 1 (T001-T003) — нужен `is_new` флаг
- **User Story 2 (Phase 3)**: Зависит от Phase 1 — НЕ зависит от US1 (только обновление текстов)
- **Polish (Phase 4)**: Зависит от завершения US1 и US2

### User Story Dependencies

- **User Story 1 (P1)**: Зависит от Foundational. Независимая от US2.
- **User Story 2 (P2)**: Зависит от Foundational (минимально). Независимая от US1. **Может выполняться параллельно с US1.**

### Within Each User Story

- Тесты пишутся ПЕРВЫМИ и должны ПАДАТЬ до реализации
- Константы до логики хендлеров
- Реализация до финальной проверки тестами

### Parallel Opportunities

- T004 и T005 (тесты US1) — параллельно
- T006 и T007 (константы и admin-check) — параллельно (разные части файлов)
- T010, T011, T012 (вся Phase 3) — T010 параллельно с T011+T012
- **US1 и US2 целиком — параллельно** (разные аспекты: хендлер vs тексты)

---

## Parallel Example: User Story 1

```bash
# Параллельно: тесты для US1
Task: T004 "Тесты выбора приветствия в tests/unit/test_group_events.py"
Task: T005 "Тесты констант rejoin в tests/unit/test_constants.py"

# Параллельно: реализация US1 (после тестов)
Task: T006 "Добавить GROUP_REJOIN_TEXT и GROUP_REJOIN_ADMIN_TEXT в constants.py"
Task: T007 "Добавить функцию проверки admin-статуса в group_events.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Завершить Phase 1: Foundational (T001-T003)
2. Завершить Phase 2: User Story 1 (T004-T009)
3. **STOP и VALIDATE**: Протестировать rejoin-приветствие независимо
4. Деплой/демо если готово

### Incremental Delivery

1. Foundational → Сигнатура `get_or_create_workspace` готова
2. User Story 1 → Rejoin-приветствие работает → Демо (MVP!)
3. User Story 2 → Все инструкции обновлены → Демо
4. Polish → Финальная проверка

### Parallel Strategy

US1 и US2 можно выполнять параллельно после Phase 1:
- Поток A: US1 (T004-T009) — хендлер + rejoin-константы
- Поток B: US2 (T010-T013) — обновление существующих текстов

---

## Notes

- [P] задачи = разные файлы, нет зависимостей
- [Story] label привязывает задачу к user story
- Каждая user story независимо завершаема и тестируема
- Тесты пишутся первыми и должны падать до реализации
- После каждой задачи или логической группы — коммит
- Остановка на любом checkpoint для независимой валидации
