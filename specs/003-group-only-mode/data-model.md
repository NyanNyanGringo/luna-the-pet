# Data Model: Групповой режим работы бота

**Branch**: `003-group-only-mode` | **Date**: 2026-03-12

## Обзор изменений

Переход от singleton-модели `Family` к мультитенантной модели `Workspace`.
Каждый workspace привязан к одной Telegram-группе через `telegram_chat_id`.

---

## Новые сущности

### Workspace (замена Family)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | Внутренний ID |
| telegram_chat_id | BigInteger | UNIQUE, NOT NULL, INDEX | ID Telegram-группы (отрицательное число) |
| title | String(255) | NOT NULL | Название группы (из Telegram) |
| is_active | Boolean | NOT NULL, DEFAULT True | Активен ли workspace (False при удалении бота из группы) |
| created_at | DateTime(tz) | NOT NULL, server_default=now() | Дата создания |
| updated_at | DateTime(tz) | NOT NULL, onupdate=now() | Дата обновления |

**Индексы**: `ix_workspace_telegram_chat_id` (unique) на `telegram_chat_id`

**Связи**:
- `members` → WorkspaceMember (one-to-many)
- `pets` → Pet (one-to-many)
- `settings` → WorkspaceSettings (one-to-one)

**Поведение при удалении бота из группы**: `is_active = False`. При повторном добавлении — `is_active = True`, данные восстанавливаются.

---

### WorkspaceMember (замена FamilyMember)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | Внутренний ID |
| workspace_id | Integer | FK(workspace.id), NOT NULL | Ссылка на workspace |
| telegram_user_id | BigInteger | NOT NULL, INDEX | Telegram user ID |
| telegram_username | String(255) | NULL | Telegram username (для отображения) |
| telegram_first_name | String(255) | NULL | Имя пользователя в Telegram |
| is_active | Boolean | NOT NULL, DEFAULT True | Активен ли участник (False при выходе из группы) |
| joined_at | DateTime(tz) | NOT NULL, server_default=now() | Дата вступления |
| left_at | DateTime(tz) | NULL | Дата выхода (если покинул группу) |

**Ограничения**: `uq_workspace_member` — UNIQUE(`workspace_id`, `telegram_user_id`)

**Индексы**:
- `ix_workspace_member_telegram_user_id` на `telegram_user_id` (для поиска всех workspace'ов пользователя)
- `ix_workspace_member_workspace_id` на `workspace_id`

**Поведение**:
- Вступление в группу → `is_active = True`, `left_at = NULL`
- Выход из группы → `is_active = False`, `left_at = now()`
- Повторное вступление → `is_active = True`, `left_at = NULL` (обновление существующей записи)

---

### WorkspaceSettings (замена FamilySettings)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | Внутренний ID |
| workspace_id | Integer | FK(workspace.id), UNIQUE, NOT NULL | Ссылка на workspace |
| timezone | String(50) | NOT NULL, DEFAULT 'Europe/Moscow' | Часовой пояс |
| locale | String(10) | NOT NULL, DEFAULT 'ru' | Локаль |

---

## Изменения в существующих сущностях

### Pet

| Изменение | Было | Стало |
|-----------|------|-------|
| FK | `family_id → Family.id` | `workspace_id → Workspace.id` |

Все health-сущности (`Vaccination`, `MedicalRecord`, `Medication`, `Note`, `WeightRecord`, `DietRecord`, `FeedingEntry`, `EmergencyProfile`) остаются привязанными к `Pet`, который теперь принадлежит `Workspace`. Дополнительных FK не требуется.

### ConversationState

| Изменение | Было | Стало |
|-----------|------|-------|
| PK | `user_id` (BigInteger) | Composite: `(telegram_user_id, workspace_id)` или отдельный PK с unique constraint |
| Новое поле | — | `workspace_id → Workspace.id` (FK, NOT NULL) |

**Обоснование**: один пользователь может быть в нескольких workspace'ах — история диалога должна быть раздельной.

### ChangeLog (Audit)

| Изменение | Было | Стало |
|-----------|------|-------|
| Новое поле | — | `workspace_id → Workspace.id` (FK, NULL) |

**Обоснование**: аудит должен быть привязан к workspace для изоляции. NULL допускается для системных записей.

### OAuthCredential

Без изменений — OAuth-токены привязаны к Telegram user_id и не зависят от workspace.

---

## Удаляемые сущности

### Family

Заменяется на `Workspace`. Таблица сохраняется в базе до следующей миграции, но ORM-модель удаляется.

### FamilyInvite

Полностью удаляется — групповая модель авторизации делает инвайт-коды ненужными.

### FamilySettings

Заменяется на `WorkspaceSettings`.

### Ассоциативная таблица family_pet

Заменяется прямым FK `Pet.workspace_id → Workspace.id` (один workspace владеет многими питомцами).

---

## Диаграмма связей

```text
Workspace (1) ──── (N) WorkspaceMember
    │                        │
    │                        └── telegram_user_id
    │
    ├── (1) WorkspaceSettings
    │
    ├── (N) Pet
    │        ├── (N) Vaccination
    │        ├── (N) MedicalRecord
    │        ├── (N) Medication
    │        ├── (N) WeightRecord
    │        ├── (N) DietRecord
    │        ├── (N) FeedingEntry
    │        ├── (N) Note
    │        └── (1) EmergencyProfile
    │
    ├── (N) ConversationState
    │        └── (telegram_user_id, workspace_id) UNIQUE
    │
    └── (N) ChangeLog
```

---

## Переходы состояний

### Workspace lifecycle

```text
[Бот добавлен в группу]
    │
    ▼
ACTIVE (is_active=True)
    │
    ├── [Бот удалён из группы] → INACTIVE (is_active=False)
    │                                │
    │                                └── [Бот повторно добавлен] → ACTIVE
    │
    └── [Группа мигрирована в супергруппу]
         → UPDATE telegram_chat_id (новый ID), остаётся ACTIVE
```

### WorkspaceMember lifecycle

```text
[Пользователь вступил в группу / chat_member event]
    │
    ▼
ACTIVE (is_active=True, left_at=NULL)
    │
    ├── [Пользователь покинул группу] → INACTIVE (is_active=False, left_at=now())
    │                                       │
    │                                       └── [Вернулся в группу] → ACTIVE (left_at=NULL)
    │
    └── [Ленивая регистрация: первое сообщение в группе]
         → Создание записи если не существует
```

---

## Правила валидации

1. `telegram_chat_id` — уникален, один workspace на группу
2. `(workspace_id, telegram_user_id)` — уникальная пара, один пользователь = одна запись в workspace
3. При запросе данных: `WHERE workspace.is_active = True` и `WHERE workspace_member.is_active = True`
4. Health-данные доступны через `Pet.workspace_id` — workspace_id обязательно передаётся в запросы агента
5. При миграции группы (смена chat_id): атомарный UPDATE workspace, никаких каскадных изменений (FK ссылаются на workspace.id, не на chat_id)
