# Tasks: Расширение базы данных и инструментов AI-агента

**Input**: Design documents from `/specs/007-extend-agent-tools/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Не запрошены явно в спецификации. Тестирование выполняется в рамках цикла разработки (тесты → код → ревью) согласно AGENTS.md.

**Organization**: Задачи сгруппированы по user stories для независимой реализации и тестирования.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой user story относится задача (US1, US2, US3, US4, US5)
- Пути файлов указаны от корня репозитория

---

## Phase 1: Foundational — Новые модели и миграция

**Purpose**: Создание новых таблиц БД, необходимых для US4. Блокирует только Phase 6 (US4).

- [x] T001 [P] Добавить модели Measurement, VetVisit, MoodLog, HeatCycle в backend/app/db/models/health.py — по схеме из data-model.md (поля, индексы, FK cascade, docstrings)
- [x] T002 [P] Создать модель Document в backend/app/db/models/documents.py — по схеме из data-model.md (document_type, url, issued_date, description, индексы)
- [x] T003 Зарегистрировать Measurement, VetVisit, MoodLog, HeatCycle, Document в backend/app/db/models/__init__.py для Alembic-автогенерации
- [x] T004 Сгенерировать Alembic-миграцию (`alembic revision --autogenerate`) и применить (`alembic upgrade head`) для 5 новых таблиц: measurement, vet_visit, mood_log, document, heat_cycle

**Checkpoint**: 5 новых таблиц существуют в БД, `alembic upgrade head` проходит без ошибок

---

## Phase 2: User Story 1 — Чтение существующих данных о питомце (Priority: P1) 🎯 MVP

**Goal**: Пользователь может спросить бота о записанных данных (вес, прививки, лекарства, заметки, кормления, диета) и получить ответ.

**Independent Test**: Записать данные через существующие write-инструменты, затем спросить бота — ответ содержит ранее записанные данные.

### Implementation for User Story 1

- [x] T005 [US1] Добавить сервисные методы чтения в backend/app/services/health_service.py: get_weight_history(session, pet_id, limit=10), get_vaccinations_list(session, pet_id), get_notes_list(session, pet_id, limit=10) — возвращают списки записей, сортировка по дате DESC
- [x] T006 [US1] Добавить 6 определений read-инструментов в backend/app/agent/tools.py: get_weight_history, get_vaccinations, get_medications, get_notes, get_feeding_history, get_current_diet — с параметрами по контракту из contracts/read-tools.md
- [x] T007 [US1] Добавить 6 обработчиков read-инструментов в backend/app/agent/tool_handlers.py: каждый резолвит pet_name → pet, вызывает сервисный метод, форматирует текстовый ответ. Для get_medications — использовать существующий get_medications(active_only). Для get_feeding_history / get_current_diet — использовать существующие методы nutrition_service.
- [x] T008 [US1] Добавить i18n-сообщения для read-инструментов в backend/app/agent/i18n.py: шаблоны ответов и сообщения «нет записей» для каждого типа данных (ru/en)

**Checkpoint**: 6 read-инструментов работают — агент может отвечать на вопросы о весе, прививках, лекарствах, заметках, кормлениях и диете

---

## Phase 3: User Story 2 — Расширение полей записи (Priority: P1)

**Goal**: Существующие write-инструменты принимают все поля, которые поддерживает БД.

**Independent Test**: Передать боту полную информацию о прививке/лекарстве/диете/кормлении/профиле — все поля сохраняются в БД.

### Implementation for User Story 2

- [x] T009 [US2] Расширить 5 определений существующих write-инструментов в backend/app/agent/tools.py: add_vaccination (+next_date, vet_name, batch_number, notes), add_medication (+frequency, end_date, last_given_date, notes), add_diet (+food_type, end_date, notes), add_feeding (+portion_size), update_pet (+origin_story, blood_type, chip_number, vet_contact) — все новые параметры опциональные
- [x] T010 [US2] Расширить обработчики в backend/app/agent/tool_handlers.py: передать новые параметры из tool call args в сервисные методы; расширить _PET_UPDATE_FIELD_WHITELIST добавив origin_story, blood_type, chip_number, vet_contact; добавить парсинг дат для next_date, end_date, last_given_date через parse_runtime_date()

**Checkpoint**: При записи прививки/лекарства/диеты/кормления с полным набором полей — все данные сохраняются. update_pet принимает origin_story, blood_type, chip_number, vet_contact.

---

## Phase 4: User Story 5 — Обновление system prompt (Priority: P1)

**Goal**: Агент понимает, что может как записывать, так и читать данные — отвечать на вопросы, показывать историю, выводить сводки.

**Independent Test**: Задать боту вопрос «покажи историю веса» — агент использует read-инструмент, а не пытается записать данные.

### Implementation for User Story 5

- [x] T011 [US5] Обновить system prompt в backend/app/agent/prompts.py: заменить «используй инструменты для записи данных» на «используй инструменты для записи и чтения данных о питомцах — записывай новую информацию, отвечай на вопросы, показывай историю, выводи сводки» (ru и en версии)

**Checkpoint**: System prompt содержит инструкции по чтению данных. Агент при вопросах о данных использует read-инструменты.

---

## Phase 5: User Story 3 — Запись и чтение медицинских записей (Priority: P2)

**Goal**: Пользователь может записать болезнь/осмотр/операцию и позже запросить медицинскую историю.

**Independent Test**: Попросить бота записать болезнь, затем спросить «какие болезни были?» — бот возвращает записи.

### Implementation for User Story 3

- [x] T012 [US3] Добавить сервисный метод get_medical_records(session, pet_id, record_type=None) в backend/app/services/health_service.py — возвращает записи с опциональной фильтрацией по типу, сортировка по дате DESC
- [x] T013 [US3] Добавить определения инструментов add_medical_record и get_medical_records в backend/app/agent/tools.py: add_medical_record (pet_name, record_type, title, date обязательные; description, resolved_date, vet_name опциональные), get_medical_records (pet_name обязательный; record_type опциональный)
- [x] T014 [US3] Добавить обработчики add_medical_record и get_medical_records в backend/app/agent/tool_handlers.py: add — вызывает существующий health_service.add_medical_record(); get — вызывает новый get_medical_records(), форматирует текстовый ответ
- [x] T015 [US3] Добавить i18n-сообщения для медицинских записей в backend/app/agent/i18n.py: подтверждение записи, шаблон списка, «нет записей» (ru/en)

**Checkpoint**: Агент записывает медицинские записи (illness/checkup/surgery) и отвечает на вопросы о медицинской истории

---

## Phase 6: User Story 4 — Новые таблицы и инструменты (Priority: P2)

**Goal**: Пользователь может записывать и запрашивать данные по 5 новым категориям: измерения, визиты к ветеринару, самочувствие, документы, течка.

**Independent Test**: Для каждой из 5 категорий — записать данные, затем запросить — бот возвращает корректные записи.

**Зависимость**: Phase 1 (модели и миграция) ДОЛЖНА быть завершена.

### Implementation for User Story 4

- [x] T016 [P] [US4] Добавить сервисные методы в backend/app/services/health_service.py: add_measurement() / get_measurements(), add_vet_visit() / get_vet_visits(), add_mood_log() / get_mood_logs(), add_heat_cycle() / get_heat_cycles() — по 2 метода на сущность (запись + чтение), с валидацией enum-значений и аудит-логированием
- [x] T017 [P] [US4] Реализовать сервисные методы add_document() и get_documents() в backend/app/services/document_service.py — с валидацией URL, фильтрацией по document_type, аудит-логированием
- [x] T018 [US4] Добавить 10 определений инструментов для новых сущностей в backend/app/agent/tools.py: add_measurement, get_measurements, add_vet_visit, get_vet_visits, add_mood_log, get_mood_logs, add_document, get_documents, add_heat_cycle, get_heat_cycles — параметры по контрактам из contracts/write-tools.md и contracts/read-tools.md
- [x] T019 [US4] Добавить 10 обработчиков инструментов для новых сущностей в backend/app/agent/tool_handlers.py: каждый резолвит pet_name → pet, парсит даты, вызывает сервисный метод, форматирует ответ. add_measurement автоматически определяет единицу измерения по типу.
- [x] T020 [US4] Добавить i18n-сообщения для 5 новых сущностей в backend/app/agent/i18n.py: подтверждения записи, шаблоны списков, «нет записей» (ru/en)

**Checkpoint**: Все 10 новых инструментов работают. Пользователь может записать и прочитать данные по всем 5 категориям.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Валидация целостности, линтинг, тесты

- [x] T021 Запустить `backend/.venv/bin/pre-commit run --all-files` и исправить все замечания ruff/mypy
- [x] T022 Запустить полный набор тестов `pytest` и убедиться, что нет регрессий
- [x] T023 Проверить, что все новые инструменты отображаются в списке tools при вызове агента (tools.py TOOL_DEFINITIONS содержит все 23+ инструмента)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: Нет зависимостей — можно начинать сразу
- **Phase 2 (US1)**: Нет зависимости от Phase 1 — работает с существующими моделями
- **Phase 3 (US2)**: Нет зависимости от Phase 1 — модифицирует существующие инструменты
- **Phase 4 (US5)**: Рекомендуется после Phase 2 (US1) — промпт описывает read-возможности
- **Phase 5 (US3)**: Нет зависимости от Phase 1 — MedicalRecord уже существует
- **Phase 6 (US4)**: **ЗАВИСИТ от Phase 1** — требует новых моделей и миграции
- **Phase 7 (Polish)**: Зависит от завершения всех предыдущих фаз

### User Story Dependencies

- **US1 (P1)**: Независима — добавляет read-инструменты для существующих данных
- **US2 (P1)**: Независима — расширяет существующие write-инструменты
- **US5 (P1)**: Рекомендуется после US1 — system prompt описывает read-возможности
- **US3 (P2)**: Независима — MedicalRecord модель уже существует в БД
- **US4 (P2)**: Зависит от Phase 1 (новые модели + миграция)

### Within Each User Story

- Сервисные методы → определения инструментов → обработчики → i18n
- Модели (если нужны) → миграция → сервисы → инструменты

### Parallel Opportunities

- T001 и T002 — параллельно (разные файлы моделей)
- T016 и T017 — параллельно (разные сервисные файлы)
- US1 и US2 работают с разными частями одних файлов (tools.py, tool_handlers.py) — последовательно
- US1/US2/US5 и Phase 1 — можно параллельно (разные слои)
- US3 можно начать параллельно с US1/US2 (работает с существующей моделью)

---

## Parallel Example: User Story 4

```bash
# После завершения Phase 1 (модели + миграция):

# Параллельно — сервисные методы (разные файлы):
Task T016: "Добавить методы для Measurement/VetVisit/MoodLog/HeatCycle в health_service.py"
Task T017: "Реализовать методы для Document в document_service.py"

# Затем последовательно — инструменты (один файл):
Task T018: "Определения 10 инструментов в tools.py"
Task T019: "Обработчики 10 инструментов в tool_handlers.py"
Task T020: "i18n-сообщения в i18n.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 + 5)

1. Phase 1: Foundational (модели + миграция) — можно параллельно с MVP
2. Phase 2: US1 — Read-инструменты для существующих данных
3. Phase 3: US2 — Расширение write-инструментов
4. Phase 4: US5 — System prompt update
5. **STOP и VALIDATE**: Бот умеет читать и полноценно записывать все существующие данные

### Incremental Delivery

1. MVP (US1 + US2 + US5) → бот читает и полноценно записывает
2. + US3 → медицинские записи (болезни, осмотры, операции)
3. + US4 → 5 новых категорий данных (измерения, визиты, самочувствие, документы, течка)
4. Polish → линтинг, тесты, финальная валидация

---

## Notes

- [P] задачи = разные файлы, нет зависимостей
- [Story] метка привязывает задачу к user story для трассировки
- Существующие сервисные методы (get_medications, get_feeding_entries, get_current_diet) переиспользуются в US1 без модификации
- health_service.add_medical_record() уже существует — US3 добавляет только инструмент агента и метод чтения
- Все новые обработчики следуют паттерну: resolve pet → parse dates → call service → format text → return
- Все write-обработчики логируют в ChangeLog через audit_service
