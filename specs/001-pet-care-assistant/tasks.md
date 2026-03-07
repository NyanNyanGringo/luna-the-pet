# Tasks: Ассистент по уходу за питомцами

**Input**: Design documents from `/specs/001-pet-care-assistant/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: В спецификации есть независимые тесты и измеримые SC-критерии — тестовые задачи покрывают все пользовательские истории и полный набор SC-001..SC-013.

**Organization**: Задачи сгруппированы по пользовательским историям (11 штук) для независимой реализации и тестирования каждой истории.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой пользовательской истории относится задача (US1, US2, ... US11)
- Все пути указаны относительно корня репозитория

## Path Conventions

- **Backend**: `backend/app/` (Python/FastAPI/aiogram)
- **Frontend**: `frontend/src/` (Vue 3/Vite)
- **Migrations**: `backend/alembic/`
- **CI/CD**: `.github/workflows/`

---

## Phase 1: Setup (Инициализация проекта)

**Purpose**: Создание структуры проекта, зависимости, инструменты разработки

- [x] T001 Create project directory structure per plan.md (backend/app/, frontend/src/, backend/tests/, backend/alembic/)
- [x] T002 [P] Initialize Python backend: pyproject.toml, requirements.txt, requirements-dev.txt in backend/
- [x] T003 [P] Initialize Vue 3 frontend with Vite, Tailwind CSS, DaisyUI in frontend/ (package.json, vite.config.js, tailwind.config.js, postcss.config.js)
- [x] T004 [P] Configure Ruff, mypy, pre-commit hooks in pyproject.toml and .pre-commit-config.yaml
- [x] T005 [P] Create multi-stage Dockerfile (node:slim + python:3.11-slim) and docker-compose.yml in project root
- [x] T006 [P] Create .env.example with all environment variables per quickstart.md in project root

---

## Phase 2: Foundational (Базовая инфраструктура)

**Purpose**: Ядро, которое ДОЛЖНО быть завершено до начала любой пользовательской истории

**CRITICAL**: Работа над US1-US11 невозможна до завершения этой фазы

- [ ] T007 Create Pydantic Settings config (DATABASE_URL, TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, OPENAI_OAUTH_CLIENT_ID, OAUTH_ENCRYPTION_KEY, JWT_SECRET, WEBHOOK_URL, WEBHOOK_SECRET, MEDIA_DIR, DEBUG) in backend/app/config.py
- [ ] T008 [P] Create SQLAlchemy DeclarativeBase with MetaData naming conventions in backend/app/db/base.py
- [ ] T009 [P] Create async engine (asyncpg) and async_session_maker (expire_on_commit=False) in backend/app/db/session.py
- [ ] T010 Initialize Alembic with async template (alembic init -t async) and configure env.py in backend/alembic/
- [ ] T011 [P] Create Family model (singleton-per-deploy), FamilyMember model (Telegram user ID as PK, is_authorized, family role, family_id FK) in backend/app/db/models/family.py
- [ ] T012 [P] Create Pet model with family_id FK ownership (soft-delete via is_active per FR-007a) in backend/app/db/models/pet.py
- [ ] T013 Create models __init__.py re-exporting all models for Alembic autodiscovery in backend/app/db/models/__init__.py
- [ ] T014 Generate initial Alembic migration for Family, FamilyMember, Pet tables and core FK/indexes
- [ ] T129 Implement singleton family bootstrap and guard (auto-create default Family on first /start, reject creation of second active Family) in backend/app/services/family_service.py and backend/app/bot/handlers/start.py
- [ ] T015 [P] Create FastAPI application with lifespan context manager (bot start/stop, scheduler) in backend/app/main.py
- [ ] T016 [P] Implement FastAPI dependencies (get_db async generator, get_current_user from JWT) in backend/app/api/deps.py
- [ ] T017 [P] Create aiogram Bot and Dispatcher with router registration skeleton in backend/app/bot/create.py
- [ ] T018 Implement DbSessionMiddleware for aiogram (injects session into handler data) in backend/app/bot/middlewares/db.py
- [ ] T019 [P] Implement family auth middleware for aiogram (check is_authorized, validate invite/code state and expiry per FR-016a) in backend/app/bot/middlewares/auth.py
- [ ] T020 Integrate aiogram webhook endpoint (POST /webhook, secret_token verification) into backend/app/main.py
- [ ] T021 Implement /start (family registration, invite/code acceptance) and /help handlers in backend/app/bot/handlers/start.py
- [ ] T101 [P] Create FamilySettings model (family_id, timezone IANA, date_locale defaults) in backend/app/db/models/family.py
- [ ] T102 [P] Create FamilyInvite model (invite_code, created_by, expires_at, revoked_at, used_by, used_at, status) in backend/app/db/models/family.py
- [ ] T103 [P] Create ChangeLog model (entity_type, entity_id, action, actor_id, changed_at, diff_json) in backend/app/db/models/audit.py
- [ ] T104 Generate Alembic migration for FamilySettings, FamilyInvite, ChangeLog and related indexes
- [ ] T105 Implement family_service (set/get timezone, create/revoke/list invites, validate one-time code lifecycle) in backend/app/services/family_service.py
- [ ] T106 Implement /invite command flow (create one-time code, show expiry, revoke active invites) in backend/app/bot/handlers/commands.py
- [ ] T145 [P] Create OAuthCredential model (family_id, provider, access_token_enc, refresh_token_enc, expires_at, status: active/expired/revoked) in backend/app/db/models/family.py
- [ ] T146 Generate Alembic migration for OAuthCredential table
- [ ] T147 Implement openai_auth_service (PKCE flow generation, code exchange, token encrypt/decrypt via Fernet, auto-refresh, fallback to OPENAI_API_KEY, admin notification on expiry per FR-026a) in backend/app/services/openai_auth_service.py
- [ ] T148 Add OpenAI OAuth callback endpoint (GET /api/auth/openai/callback — exchange code for tokens, store encrypted in DB) in backend/app/api/auth.py
- [ ] T149 Implement /connectai command in Telegram (generate PKCE OAuth URL, send link to user, handle success/failure notification) in backend/app/bot/handlers/commands.py
- [ ] T150 Update agent brain to use openai_auth_service for client initialization (OAuth primary, API key fallback, transparent switching) in backend/app/agent/brain.py

**Checkpoint**: Фундамент готов — можно начинать реализацию пользовательских историй

---

## Phase 3: User Story 1 — Запись данных голосом/текстом (Priority: P1) MVP

**Goal**: Член семьи может записать любой факт о питомце (вес, вакцину, корм, заметку) одним голосовым или текстовым сообщением в Telegram, а агент извлекает структурированные данные и сохраняет в БД

**Independent Test**: Отправить голосовое «У Луны день рождения 15 марта 2021» боту. Бот подтверждает сохранение. Проверить запись в БД

### Модели US1

- [ ] T022 [P] [US1] Create health models (WeightRecord, Vaccination, MedicalRecord, Medication, Note) in backend/app/db/models/health.py
- [ ] T023 [P] [US1] Create nutrition models (DietRecord, FeedingEntry) in backend/app/db/models/nutrition.py
- [ ] T024 [P] [US1] Add ConversationState model (last_response_id, turn_count, session_summary) to backend/app/db/models/family.py
- [ ] T107 [P] [US1] Create EmergencyProfile model (allergies, chronic_conditions, vet_contact, blood_type, rabies_vaccination_date, latest_weight_snapshot) in backend/app/db/models/health.py
- [ ] T025 [US1] Update models __init__.py and generate Alembic migration for all US1 entities

### Сервисы US1

- [ ] T026 [US1] Implement pet_service (get_pets, get_pet_by_name, resolve_pet_from_text, create/update pet) in backend/app/services/pet_service.py
- [ ] T027 [P] [US1] Implement health_service (CRUD for weight, vaccination, medical records, medications, notes) in backend/app/services/health_service.py
- [ ] T028 [P] [US1] Implement nutrition_service (CRUD for diet records with historicity, feeding entries) in backend/app/services/nutrition_service.py
- [ ] T108 [US1] Extend health_service with EmergencyProfile CRUD and validation (blood type enum, vet contact format, explicit null/unknown states)
- [ ] T109 [US1] Implement audit_service and integrate write-audit hooks into health/nutrition/pet services (actor_id required)

### Агент US1

- [ ] T029 [US1] Create system prompt builder (pets list, active meds, upcoming reminders, language detection per FR-015a, family timezone context per FR-008a) in backend/app/agent/prompts.py
- [ ] T030 [US1] Define agent tool schemas (function definitions for all CRUD operations, strict mode JSON) in backend/app/agent/tools.py
- [ ] T031 [US1] Implement tool handlers (bridge tool calls to services, return structured results) in backend/app/agent/tool_handlers.py
- [ ] T032 [US1] Implement agent brain (run_agent with OpenAI Responses API, previous_response_id, context trimming at ~8-10 turns) in backend/app/agent/brain.py
- [ ] T033 [P] [US1] Implement voice transcription (download OGG from Telegram, convert to MP3 via pydub, use auto-detect or ru/en selection from family/message context) in backend/app/agent/whisper.py
- [ ] T110 [P] [US1] Add agent tools for EmergencyProfile update/read (including explicit capture of allergies, blood type, vet contact)
- [ ] T111 [US1] Add timezone-aware relative date normalization utility («сегодня/завтра/вчера») before persistence and reminder creation
- [ ] T112 [US1] Localize bot message templates (RU/EN) for confirmations, validation errors and clarification prompts

### Обработчик сообщений US1

- [ ] T034 [US1] Implement message handler (voice -> transcribe -> agent, text -> agent, send response) in backend/app/bot/handlers/message.py
- [ ] T035 [US1] Register US1 handlers (message router) in backend/app/bot/create.py

**Checkpoint**: MVP готов — можно записывать данные о питомце через Telegram голосом и текстом

---

## Phase 4: User Story 2 — Управление питомцами (Priority: P2)

**Goal**: Пользователь может создавать, просматривать и удалять питомцев через естественные фразы в Telegram, а slash-команды работают как shortcut. Агент корректно определяет целевого питомца при неоднозначности

**Independent Test**: Отправить «Добавь питомца Рекса, это собака». Затем отправить «Рекс весит 25 кг». Данные сохраняются под Рексом. Повторить создание через /newpet и убедиться в эквивалентном поведении

### Реализация US2

- [ ] T036 [P] [US2] Create inline keyboards module (pet_select, delete_confirm/cancel, generic confirmation) in backend/app/bot/keyboards/__init__.py
- [ ] T037 [US2] Implement natural-language-first pet creation flow (intent «добавь питомца ...», ask name/species -> create pet) with /newpet shortcut parity, accepting voice and text in backend/app/bot/handlers/pets.py
- [ ] T038 [US2] Implement natural-language list/profile/delete flows (with soft-delete confirmation) plus /pets, /profile, /deletepet shortcuts in backend/app/bot/handlers/pets.py
- [ ] T039 [US2] Implement pet_select callback handler (pet_select:{pet_id} inline button) in backend/app/bot/handlers/pets.py
- [ ] T040 [US2] Register US2 handlers (pets router) in backend/app/bot/create.py

**Checkpoint**: Управление питомцами работает — создание, просмотр, удаление, выбор при неоднозначности

---

## Phase 5: User Story 3 — Напоминания и контроль выполнения (Priority: P3)

**Goal**: Система планирует напоминания о лекарствах, вакцинациях и событиях, отправляет уведомления в Telegram и контролирует выполнение через follow-up сообщения

**Independent Test**: Сказать боту «Луна принимает таблетки от глистов каждые 3 месяца, последний раз — сегодня». Дождаться напоминания (или тестовый вызов). Проверить доставку уведомления и контрольного вопроса

### Реализация US3

- [ ] T041 [US3] Create Reminder model (next_fire_at UTC, frequency_days, follow_up_sent, confirmed_at, source_timezone, links to medication/vaccination) in backend/app/db/models/reminder.py
- [ ] T042 [US3] Update models __init__.py and generate Alembic migration for Reminder table
- [ ] T043 [US3] Implement reminder_service (create, confirm, snooze to next day, reschedule, calculate next fire date with family timezone normalization) in backend/app/services/reminder_service.py
- [ ] T044 [US3] Configure APScheduler 3.x with AsyncIOScheduler and SQLAlchemyJobStore (misfire_grace_time=None, coalesce=True) in backend/app/scheduler/__init__.py
- [ ] T045 [US3] Implement scheduler jobs (fire_pending_reminders, send_follow_ups after 2h, recover_missed on startup, timezone-aware delivery windows) in backend/app/scheduler/jobs.py
- [ ] T046 [US3] Implement reminder callback handlers (reminder_confirm/reminder_snooze inline buttons) in backend/app/bot/handlers/reminders.py
- [ ] T047 [US3] Add reminder tools to agent (create_reminder, list_reminders, confirm_reminder) in backend/app/agent/tools.py
- [ ] T048 [US3] Integrate APScheduler startup/shutdown into FastAPI lifespan in backend/app/main.py
- [ ] T113 [US3] Add timezone settings endpoints/commands usage to reminder flow (new reminders always resolved in FamilySettings.timezone)
- [ ] T127 [US3] Implement /timezone command flow in Telegram (show current timezone, validate IANA input, apply to FamilySettings)

**Checkpoint**: Напоминания работают — планирование, отправка, контрольные сообщения, подтверждение/перенос

---

## Phase 6: User Story 4 — Обработка фотографий (Priority: P4)

**Goal**: Пользователь отправляет фото в Telegram. Агент классифицирует (паспорт/документ/обычное), извлекает данные через Vision API и сохраняет

**Independent Test**: Отправить фото паспорта вакцинации. Бот извлекает вакцинации и предлагает сохранить

### Реализация US4

- [ ] T049 [US4] Create Photo model (file_path, telegram_file_id, caption, ai_description, photo_type) in backend/app/db/models/media.py
- [ ] T050 [US4] Update models __init__.py and generate Alembic migration for Photo table
- [ ] T051 [US4] Implement media_service (FileStorage protocol, LocalFileStorage: save to /data/uploads/{pet_id}/{year}/{month}/, get, delete) in backend/app/services/media_service.py
- [ ] T052 [US4] Implement photo pipeline in agent brain (classify photo type, gpt-4o for passport/document, gpt-4o-mini for regular, structured extraction) in backend/app/agent/brain.py
- [ ] T053 [US4] Add photo handling to message handler (download from Telegram, route to agent photo pipeline) in backend/app/bot/handlers/message.py
- [ ] T054 [US4] Add photo tools to agent (save_photo, extract_passport_data, confirm_passport_data with passport_confirm/cancel callbacks) in backend/app/agent/tools.py

**Checkpoint**: Фотографии обрабатываются — паспорт/документ/обычное, извлечение данных, сохранение в галерею

---

## Phase 7: User Story 5 — Веб-панель (Priority: P5)

**Goal**: Веб-панель с профилями питомцев, календарём, чатом с агентом и редактированием записей. Аутентификация через Telegram Login Widget

**Independent Test**: Открыть веб-панель, войти через Telegram, просмотреть профиль Луны и календарь с напоминаниями

### Backend API для US5

- [ ] T055 [US5] Implement Telegram Login Widget verification (HMAC-SHA-256) and JWT issuing in backend/app/api/auth.py
- [ ] T056 [P] [US5] Create pets API router (GET /api/pets, GET /api/pets/{id}, PUT /api/pets/{id}) in backend/app/api/routers/pets.py
- [ ] T057 [P] [US5] Create health API router (CRUD for weight, vaccinations, medical, medications, diet, notes, photos, SOS-поля per contracts/api.md) in backend/app/api/routers/health.py
- [ ] T058 [P] [US5] Create calendar and dashboard API router (GET /api/calendar with year/month filter) in backend/app/api/routers/dashboard.py
- [ ] T114 [P] [US5] Create settings API router (GET/PUT family timezone, invite generation/revocation endpoints) in backend/app/api/routers/settings.py
- [ ] T115 [P] [US5] Create audit API router (GET /api/pets/{id}/history with actor/time/action filters) in backend/app/api/routers/audit.py
- [ ] T059 [US5] Implement WebSocket chat endpoint (wss://.../ws/chat, JWT auth, stream_start/token/end per contracts/websocket.md) in backend/app/api/routers/chat.py
- [ ] T060 [US5] Register all API routers and configure StaticFiles mount for frontend/dist in backend/app/main.py

### Frontend для US5

- [ ] T061 [P] [US5] Create API service module (fetch wrapper, JWT in Authorization header, error handling) in frontend/src/services/api.js
- [ ] T062 [P] [US5] Create Vue Router configuration (Login, Dashboard, PetProfile, Analytics routes) in frontend/src/router/index.js
- [ ] T063 [US5] Create TelegramLogin component (Telegram Login Widget script tag + callback) in frontend/src/components/TelegramLogin.vue
- [ ] T064 [US5] Create Login page (TelegramLogin widget, redirect on success) in frontend/src/pages/Login.vue
- [ ] T065 [US5] Create App.vue with navigation layout (sidebar/header, router-view) in frontend/src/App.vue
- [ ] T116 [P] [US5] Add frontend i18n base (RU/EN dictionaries, locale switcher, persisted locale by family/user context)
- [ ] T066 [P] [US5] Create PetCard component (name, species, weight, active meds count) in frontend/src/components/PetCard.vue
- [ ] T067 [US5] Create Dashboard page (pet cards grid, upcoming reminders summary) in frontend/src/pages/Dashboard.vue
- [ ] T068 [P] [US5] Create Calendar component (@fullcalendar/vue3 integration, past events + future reminders) in frontend/src/components/Calendar.vue
- [ ] T069 [US5] Create PetProfile page (all records grouped by type, inline edit/delete, emergency profile block, Calendar widget) in frontend/src/pages/PetProfile.vue
- [ ] T070 [US5] Create ChatWidget component (WebSocket connection, streaming tokens, DaisyUI chat bubbles) in frontend/src/components/ChatWidget.vue
- [ ] T117 [US5] Add change history tab in PetProfile (render audit log with actor, timestamp, action and changed fields)
- [ ] T128 [US5] Add family settings UI (timezone selector + invite management) connected to settings API
- [ ] T151 [US5] Add OpenAI OAuth binding UI in family settings (connect/disconnect button, OAuth status indicator, expiry info, re-auth prompt) in frontend/src/pages/ settings section

**Checkpoint**: Веб-панель функциональна — авторизация, профили, календарь, чат, CRUD записей

---

## Phase 8: User Story 6 — Отчёт для ветеринара с переводом (Priority: P6)

**Goal**: Команда /vetreport генерирует полный отчёт о питомце на любом языке мира. Для каждого языка в v1 обязательны текст в чате и TXT-файл (PDF опционально). Система запоминает языковые предпочтения

**Independent Test**: Отправить /vetreport впервые — бот спрашивает язык. Ответить «сербский». Получить отчёт на сербском в виде текста и TXT-файла. Повторно — меню с сербским

### Реализация US6

- [ ] T071 [US6] Add LanguagePreference model (language_name, language_code, last_used_at) to backend/app/db/models/family.py
- [ ] T072 [US6] Generate Alembic migration for LanguagePreference table
- [ ] T073 [US6] Implement report_service (compile full pet report, translate via OpenAI, manage language preferences, multi-language fan-out generation with deterministic output order and per-language artifact manifest) in backend/app/services/report_service.py
- [ ] T139 [US6] Implement report_artifact_service (render mandatory TXT artifact per language, deterministic filename template, optional PDF artifact behind REPORT_PDF_ENABLED) in backend/app/services/report_artifact_service.py
- [ ] T074 [US6] Implement /vetreport handler with language selection FSM (inline menu of saved languages, «Другой язык», explicit multi-language request parsing/dispatch, and delivery of text + TXT artifact per language) in backend/app/bot/handlers/commands.py
- [ ] T075 [US6] Add vet report tool to agent (handle voice requests like «Отчёт на испанском») in backend/app/agent/tools.py

**Checkpoint**: Ветеринарный отчёт работает — генерация, перевод на любой язык, запоминание предпочтений

---

## Phase 9: User Story 7 — Экстренная карточка /sos (Priority: P7)

**Goal**: Команда /sos мгновенно выдаёт критически важную информацию о питомце: аллергии, лекарства, ветеринар, группа крови, вес, бешенство

**Independent Test**: Отправить /sos при наличии данных о Луне. Получить компактную карточку со всей критической информацией

### Реализация US7

- [ ] T076 [US7] Implement /sos handler (compile emergency card from structured SOS fields: allergies, medications, chronic conditions, vet contact, blood type, rabies date, weight; format per contracts/bot-commands.md) in backend/app/bot/handlers/commands.py
- [ ] T077 [P] [US7] Add SOS API endpoint (GET /api/pets/{pet_id}/sos per contracts/api.md) in backend/app/api/routers/health.py
- [ ] T130 [US7] Implement explicit Telegram SOS edit flow (/sosedit FSM for allergies, chronic conditions, vet contact, blood type with validation and confirmation) in backend/app/bot/handlers/commands.py

**Checkpoint**: Экстренная карточка работает — мгновенный ответ, все критические данные, «Не указано» для пустых полей

---

## Phase 10: User Story 8 — Аналитика здоровья (Priority: P8)

**Goal**: Визуальный дашборд (график веса, статус вакцинаций, таймлайн событий) и AI-отчёт с оценкой здоровья питомца в Telegram и веб-панели

**Independent Test**: Открыть аналитику с данными Луны. Увидеть график веса, статус вакцинаций. Нажать «Сформировать AI-отчёт» в вебе и получить секции Факты / AI-наблюдения / AI-рекомендации / vet-escalation (по условию)

### Реализация US8

- [ ] T078 [US8] Implement analytics API endpoint (GET /api/pets/{pet_id}/analytics: weight_trend, vaccination_status, medication_stats, medical_timeline per contracts/api.md) in backend/app/api/routers/dashboard.py
- [ ] T079 [P] [US8] Create WeightChart component (vue3-apexcharts line chart with trend) in frontend/src/components/WeightChart.vue
- [ ] T080 [P] [US8] Create Timeline component (DaisyUI timeline CSS, medical events chronological) in frontend/src/components/Timeline.vue
- [ ] T081 [US8] Create Analytics page (WeightChart, vaccination status with color indicators, Timeline, medication stats, AI-report panel with explicit section rendering) in frontend/src/pages/Analytics.vue
- [ ] T140 [US8] Implement web AI report trigger endpoint (POST /api/pets/{pet_id}/analytics/ai-report returning sections facts/observations/recommendations/vet-escalation) in backend/app/api/routers/dashboard.py
- [ ] T082 [US8] Add AI health analysis tool to agent (analyze trends, overdue vaccinations, missed meds, generate report with fixed sections: facts vs AI observations vs recommendations, include vet-escalation block for red flags; reusable by Telegram and web endpoint) in backend/app/agent/tools.py

**Checkpoint**: Аналитика работает — визуальные графики, AI-отчёт с рекомендациями

---

## Phase 11: User Story 9 — Учёт запасов и напоминание о кормушке (Priority: P9)

**Goal**: Система отслеживает запасы корма и лекарств, рассчитывает расход, а также использует настраиваемое расписание кормления для напоминаний о кормушке

**Independent Test**: Сообщить «Купил 12 кг корма для Луны». Настроить «Кормим Луну в 08:00 и 20:00». Потом «Осталось 2 кг». Получить напоминание о покупке и напоминание о наполнении кормушки по расписанию

### Реализация US9

- [ ] T083 [US9] Add Supply model (supply_type, current_amount, unit, threshold, daily_consumption) to backend/app/db/models/nutrition.py
- [ ] T084 [US9] Generate Alembic migration for Supply table
- [ ] T085 [US9] Extend nutrition_service with supply tracking (add/update stock, calculate days until empty, check threshold) in backend/app/services/nutrition_service.py
- [ ] T141 [US9] Add FeedingSchedule model (pet_id, timezone, weekdays_mask, times_of_day, is_active, updated_by) and migration in backend/app/db/models/nutrition.py and backend/alembic/versions/
- [ ] T142 [US9] Implement feeding schedule flow (/feeding + natural-language intents for create/list/update schedule with timezone validation) in backend/app/bot/handlers/commands.py and backend/app/services/nutrition_service.py
- [ ] T086 [US9] Add supply tools to agent (add_supply, update_stock, list_supplies) in backend/app/agent/tools.py
- [ ] T087 [US9] Add supply low-stock check and feeding reminder scheduler jobs (driven by persisted FeedingSchedule) in backend/app/scheduler/jobs.py

**Checkpoint**: Запасы и расписание кормления отслеживаются — учёт, расход, уведомления о пополнении и напоминания о кормушке

---

## Phase 12: User Story 10 — Экспорт и импорт данных (Priority: P10)

**Goal**: Полный экспорт всех доменных данных в JSON (/export) и восстановление из JSON-файла (/import), включая семейные настройки, инвайты, языковые предпочтения и аудит

**Independent Test**: Отправить /export, получить JSON. На чистом экземпляре /import с файлом. Все данные восстановлены

### Реализация US10

- [ ] T088 [US10] Implement export_service (full JSON export/import for FR-024b entities: Family, FamilySettings, FamilyMember, FamilyInvite, Pet, ConversationState, EmergencyProfile, Weight/Vaccination/Medical/Medication, Diet/FeedingEntry/FeedingSchedule, Note, Photo metadata, Reminder, LanguagePreference, Supply, GiftIdea, ChangeLog; with validation and conflict detection) in backend/app/services/export_service.py
- [ ] T089 [US10] Implement /export (send JSON file) and /import (receive and process JSON attachment) handlers in backend/app/bot/handlers/commands.py
- [ ] T090 [P] [US10] Add export/import API endpoints (GET /api/export, POST /api/import multipart per contracts/api.md) in backend/app/api/routers/dashboard.py
- [ ] T131 [US10] Add versioned export JSON contract artifacts (schema_version field, JSON Schema and example fixture with full FR-024b entity scope) in specs/001-pet-care-assistant/contracts/export.schema.json and backend/tests/fixtures/export_example.json

**Checkpoint**: Экспорт/импорт работает — полный бэкап, валидация, обработка конфликтов

---

## Phase 13: User Story 11 — Идеи подарков для питомца (Priority: P11)

**Goal**: Пользователь сохраняет и просматривает идеи подарков. Бот напоминает о списке перед днём рождения питомца

**Independent Test**: Отправить «Идея подарка для Луны — Kong игрушка». Затем /giftideas. Получить список с сохранённой идеей

### Реализация US11

- [ ] T091 [US11] Create GiftIdea model (description, status: idea/bought/gifted) in backend/app/db/models/gift.py
- [ ] T092 [US11] Generate Alembic migration for GiftIdea table
- [ ] T093 [US11] Implement /giftideas handler (list ideas, show status) in backend/app/bot/handlers/commands.py
- [ ] T094 [US11] Add gift idea tools to agent (save_gift_idea, list_gift_ideas, mark_as_bought) in backend/app/agent/tools.py
- [ ] T095 [US11] Add birthday reminder scheduler job (check birth_date -7 days, include gift ideas if non-empty per spec) in backend/app/scheduler/jobs.py

**Checkpoint**: Подарки работают — сохранение, просмотр, статусы, напоминание перед днём рождения

---

## Phase 14: Polish & Cross-Cutting Concerns

**Purpose**: CI/CD, безопасность, сквозное тестовое покрытие историй и всех SC-001..SC-013, проверка performance/data-minimization критериев

- [ ] T096 [P] Create GitHub Actions CI workflow (ruff check, ruff format --check, mypy, pytest with PostgreSQL service container, coverage >=80%) in .github/workflows/ci.yml
- [ ] T097 [P] Create GitHub Actions deploy workflow (SSH to VDS, docker compose pull && up -d, only on main) in .github/workflows/deploy.yml
- [ ] T098 Add structured logging and error handling across all services and handlers
- [ ] T099 Configure CORS, security headers, and webhook secret validation in backend/app/main.py
- [ ] T100 Run quickstart.md validation (end-to-end smoke test per quickstart.md)
- [ ] T118 [P] Add integration tests for US1 (voice/text ingestion -> structured persistence -> bot confirmation) in backend/tests/integration/test_us1_ingestion.py
- [ ] T119 [P] Add integration tests for US2-US3 critical flow (natural-language pet CRUD + slash parity + pet resolution + reminder scheduling/follow-up in family timezone) in backend/tests/integration/test_us2_us3_flow.py
- [ ] T120 [P] Add integration tests for US4-US5 flow (photo extraction -> API visibility -> web read model) in backend/tests/integration/test_us4_us5_flow.py
- [ ] T121 [P] Add integration tests for US6 flow (/vetreport generation + translation + language preference reuse + multi-language fan-out output order + per-language text/TXT artifacts) in backend/tests/integration/test_us6_vetreport.py
- [ ] T122 [P] Add contract tests for SC-012 and FR-020a/FR-020b (/sos uses structured emergency fields, Telegram /sosedit FSM persists fields, response latency under budget) in backend/tests/contract/test_sos_contract.py
- [ ] T123 [P] Add performance tests for SC-004/SC-006/SC-011/SC-013 with explicit thresholds and CI assertions in backend/tests/integration/test_performance_budgets.py
- [ ] T124 Add external payload minimization checks (OpenAI/Telegram request body redaction + max-field assertions) in backend/tests/unit/test_external_payload_minimization.py
- [ ] T125 Add audit trail integration tests (author/action/timestamp/diff for create/update/delete from bot and web flows) in backend/tests/integration/test_audit_trail.py
- [ ] T126 Add invite lifecycle tests (generate, expire, revoke, one-time use) in backend/tests/integration/test_invite_lifecycle.py
- [ ] T143 [P] Add integration tests for FR-023a (feeding schedule create/update/list via NL + /feeding shortcut and scheduler delivery in family timezone) in backend/tests/integration/test_feeding_schedule_flow.py
- [ ] T144 [P] Add full backup/restore integration tests for FR-024b scope (timezone, invites, language preferences, audit trail and all pet entities survive export/import roundtrip) in backend/tests/integration/test_export_import_roundtrip_full_scope.py
- [ ] T132 [P] Add contract tests for FR-019b translation glossary quality (golden medical terms >=95% exact term match) in backend/tests/contract/test_vetreport_translation_glossary.py
- [ ] T133 [P] Add contract tests for FR-021a/FR-021b and web-trigger contract (AI health report sections explicit, factual/advice separation enforced, vet-escalation appears on red flags, POST analytics/ai-report schema is stable) in backend/tests/contract/test_health_analysis_contract.py
- [ ] T134 [P] Add integration tests for SC-001/SC-002/SC-003 (voice-to-save under 30s, pet resolution >=95% on fixture set, transcription acceptance >=9/10) in backend/tests/integration/test_sc001_sc003_ingestion_quality.py
- [ ] T135 [P] Add scheduler/integration tests for SC-005 (follow-up sent within 2h window when no confirmation) in backend/tests/integration/test_sc005_followup_window.py
- [ ] T136 [P] Add integration tests for SC-007/SC-008/SC-009 (calendar completeness, Telegram web login SSO, cross-interface data visibility <=10s) in backend/tests/integration/test_sc007_sc009_cross_interface.py
- [ ] T137 [P] Add constrained load test for SC-010 budgets (2 CPU/4GB, one-family profile: p95 API <=1.5s, error rate <1%, scheduler lag <=60s, CPU <=85%, RAM <=3.2GB for 15 min) in backend/tests/integration/test_sc010_single_family_capacity.py
- [ ] T138 [P] Add export contract tests for FR-024a/FR-024b (schema_version present, export validates against JSON Schema, fixture/import cover full entity scope) in backend/tests/contract/test_export_schema_contract.py
- [ ] T152 [P] Add OAuth lifecycle integration tests (connect via PKCE, token refresh, session expiry -> fallback to API key, admin notification, reconnect flow) in backend/tests/integration/test_oauth_lifecycle.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Нет зависимостей — начинается сразу
- **Foundational (Phase 2)**: Зависит от Setup — БЛОКИРУЕТ все пользовательские истории
- **US1 (Phase 3)**: Зависит от Foundational — MVP
- **US2 (Phase 4)**: Зависит от Foundational. Использует keyboards в агенте US1, но тестируется независимо
- **US3 (Phase 5)**: Зависит от Foundational. Использует модели из US1 (Medication, Vaccination)
- **US4 (Phase 6)**: Зависит от Foundational. Расширяет обработчик сообщений US1
- **US5 (Phase 7)**: Зависит от Foundational. Использует все сервисы US1-US4 через REST API
- **US6 (Phase 8)**: Зависит от Foundational. Использует сервисы US1 для данных отчёта
- **US7 (Phase 9)**: Зависит от Foundational. Использует сервисы US1 для данных SOS
- **US8 (Phase 10)**: Зависит от US5 (фронтенд-компоненты и API)
- **US9 (Phase 11)**: Зависит от Foundational. Расширяет nutrition models из US1
- **US10 (Phase 12)**: Зависит от Foundational. Экспорт/импорт всех сущностей
- **US11 (Phase 13)**: Зависит от Foundational. Использует scheduler из US3
- **Polish (Phase 14)**: Зависит от завершения всех нужных пользовательских историй

### User Story Dependencies

- **US1 (P1)**: Foundational -> US1 (нет зависимости от других историй)
- **US2 (P2)**: Foundational -> US2 (интегрируется с US1 агентом, но тестируется независимо)
- **US3 (P3)**: Foundational + US1 модели -> US3 (Reminder ссылается на Medication/Vaccination)
- **US4 (P4)**: Foundational + US1 агент -> US4 (расширяет pipeline обработки сообщений)
- **US5 (P5)**: Foundational + US1 сервисы -> US5 (API использует существующие сервисы)
- **US6 (P6)**: Foundational + US1 сервисы -> US6
- **US7 (P7)**: Foundational + US1 сервисы -> US7
- **US8 (P8)**: US5 фронтенд -> US8 (расширяет существующие страницы)
- **US9 (P9)**: Foundational + US1 nutrition модели + US3 scheduler -> US9
- **US10 (P10)**: Foundational + все модели -> US10
- **US11 (P11)**: Foundational + US3 scheduler -> US11

### Within Each User Story

- Модели перед сервисами
- Миграции после моделей
- Сервисы перед эндпоинтами/обработчиками
- Инструменты агента после сервисов
- Регистрация роутеров в конце

### Parallel Opportunities

- **Phase 1**: T002-T006 все [P] — 5 задач параллельно
- **Phase 2**: T008+T009, T011+T012, T015+T016+T017, T018+T019 — группы параллельных задач
- **Phase 3 (US1)**: T022+T023+T024 модели параллельно; T027+T028 сервисы параллельно; T033 параллельно с T029-T032
- **Phase 4 (US2)**: T036 параллельно с другими задачами фазы
- **Phase 7 (US5)**: T056+T057+T058 API роутеры параллельно; T061+T062 фронтенд-утилиты параллельно; T066+T068 компоненты параллельно
- **Phase 10 (US8)**: T079+T080 фронтенд-компоненты параллельно
- После Foundational параллелить только истории без shared hot files; US1/US4/US7 идут последовательно у одного владельца, потому что пересекаются в `backend/app/agent/tools.py`, `backend/app/bot/handlers/message.py`, `backend/app/bot/handlers/commands.py`, `backend/app/main.py`
- Для параллельной работы использовать явные ownership/merge points: `agent/tools.py`, `bot/handlers/commands.py`, `api/routers/dashboard.py`, `main.py`

---

## Parallel Example: User Story 1

```bash
# Запустить все модели US1 параллельно:
Task T022: "Create health models in backend/app/db/models/health.py"
Task T023: "Create nutrition models in backend/app/db/models/nutrition.py"
Task T024: "Add ConversationState to backend/app/db/models/family.py"

# Запустить сервисы параллельно (после T025):
Task T027: "Implement health_service in backend/app/services/health_service.py"
Task T028: "Implement nutrition_service in backend/app/services/nutrition_service.py"

# Whisper параллельно с основным агентом:
Task T033: "Implement voice transcription in backend/app/agent/whisper.py"
Task T029-T032: "Agent prompts, tools, handlers, brain (sequential)"
```

## Parallel Example: User Story 5

```bash
# Запустить API роутеры параллельно (после T055):
Task T056: "Pets API router in backend/app/api/routers/pets.py"
Task T057: "Health API router in backend/app/api/routers/health.py"
Task T058: "Calendar API router in backend/app/api/routers/dashboard.py"

# Запустить фронтенд-утилиты параллельно:
Task T061: "API service in frontend/src/services/api.js"
Task T062: "Vue Router in frontend/src/router/index.js"

# Запустить независимые компоненты параллельно (после T065):
Task T066: "PetCard component"
Task T068: "Calendar component"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — блокирует всё)
3. Complete Phase 3: User Story 1
4. **STOP и VALIDATE**: Тест US1 — голосовое/текстовое сообщение -> данные в БД
5. Деплой MVP если готов

### Incremental Delivery

1. Setup + Foundational -> Фундамент готов
2. + US1 -> Запись данных голосом/текстом -> Deploy (MVP!)
3. + US2 -> Управление питомцами -> Deploy
4. + US3 -> Напоминания -> Deploy
5. + US4 -> Фотографии -> Deploy
6. + US5 -> Веб-панель -> Deploy
7. + US6-US11 -> Дополнительные функции -> Deploy
8. Polish -> CI/CD, безопасность -> Final Deploy

### Parallel Team Strategy

С несколькими разработчиками (после Foundational):
- **Разработчик A (Backend Core, owner hot files)**: US1 -> US3 -> US4 -> US7 -> US8 (`agent/tools.py`, `agent/brain.py`, `bot/handlers/message.py`, `main.py`)
- **Разработчик B (Backend Features)**: US2 -> US6 -> US9 -> US10 -> US11 (`services/report_service.py`, `services/export_service.py`, `bot/handlers/pets.py`; изменения в `bot/handlers/commands.py` только через согласованный merge point)
- **Разработчик C (Frontend)**: US5 -> US8 (`frontend/src/**`, синхронизация API-контрактов через T060/T078)

---

## Notes

- [P] задачи = разные файлы, нет зависимостей между ними
- [Story] метка связывает задачу с пользовательской историей
- Каждая история может быть завершена и протестирована независимо
- Коммит после каждой задачи или логической группы
- Остановка на любом Checkpoint для валидации истории
- Избегать: размытых задач, конфликтов в hot files без ownership, зависимостей между историями, нарушающих независимость
