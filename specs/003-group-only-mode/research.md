# Research: Групповой режим работы бота

**Branch**: `003-group-only-mode` | **Date**: 2026-03-12

## 1. Обработка событий добавления/удаления бота из группы (aiogram 3.x)

### Решение

Использовать обработчик `router.my_chat_member` с фильтром `ChatMemberUpdatedFilter` и операторами перехода `>>`.

### Обоснование

- `my_chat_member` — стандартное событие Telegram Bot API для отслеживания изменений статуса бота в чатах
- aiogram 3.x предоставляет декларативные фильтры: `IS_NOT_MEMBER >> IS_MEMBER` (бот добавлен), `IS_MEMBER >> IS_NOT_MEMBER` (бот удалён)
- Событие `my_chat_member` приходит автоматически без настройки `allowed_updates`
- Объект `ChatMemberUpdated` содержит `chat.id`, `chat.type`, `chat.title`, `from_user` — всё необходимое для создания workspace

### Ключевые детали

```python
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER

@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added(event: ChatMemberUpdated): ...

@router.my_chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_removed(event: ChatMemberUpdated): ...
```

Статусы `ChatMember`:
- `IS_MEMBER` = creator + administrator + member + restricted (если is_member=True)
- `IS_NOT_MEMBER` = left + kicked + restricted (если is_member=False)

### Альтернативы рассмотрены

- Обработка через `content_types.NEW_CHAT_MEMBERS` — устаревший подход, не ловит все сценарии (например, добавление через BotFather)

---

## 2. Маршрутизация сообщений: группа vs личный чат (aiogram 3.x)

### Решение

Использовать Magic Filter `F.chat.type` для разделения потоков на уровне роутеров.

### Обоснование

- `ChatTypeFilter` не является встроенным в aiogram 3.x (был в 2.x)
- Magic Filter `F.chat.type` — идиоматический подход в aiogram 3.x
- Фильтрация на уровне роутера позволяет полностью разделить логику private и group

### Ключевые детали

```python
from aiogram import F, Router
from aiogram.enums import ChatType

# Роутер только для приватных чатов
private_router = Router()
private_router.message.filter(F.chat.type == ChatType.PRIVATE)

# Роутер только для групп
group_router = Router()
group_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
```

Enum `aiogram.enums.ChatType`: `PRIVATE`, `GROUP`, `SUPERGROUP`, `CHANNEL`, `SENDER`.

### Альтернативы рассмотрены

- Кастомный `ChatTypeFilter(BaseFilter)` — избыточен, Magic Filter покрывает потребности
- Проверка `message.chat.type` внутри каждого обработчика — дублирование, нарушает SRP

---

## 3. Генерация пригласительных ссылок на группу

### Решение

Использовать `bot.create_chat_invite_link()` для создания дополнительных ссылок (не primary).

### Обоснование

- `create_chat_invite_link` не отзывает существующие ссылки (в отличие от `export_chat_invite_link`)
- Позволяет задать `name`, `expire_date`, `member_limit`
- Возвращает объект `ChatInviteLink` с полем `.invite_link`

### Ключевые детали

```python
from aiogram.types import ChatInviteLink

link: ChatInviteLink = await bot.create_chat_invite_link(
    chat_id=chat_id,
    name="Luna Bot Invite",
)
invite_url = link.invite_link
```

**Требования**:
- Бот ОБЯЗАН быть администратором группы
- Нужно право `can_invite_users`

**Обработка ошибок**:
- При отсутствии прав API возвращает `400 Bad Request`
- Ловить через `aiogram.exceptions.TelegramBadRequest`
- Сообщить пользователю, что нужно назначить бота администратором

### Альтернативы рассмотрены

- `export_chat_invite_link` — отзывает предыдущую primary ссылку при каждом вызове, нежелательно

---

## 4. Отслеживание новых участников группы

### Решение

Использовать обработчик `router.chat_member` с фильтром `ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER)`.

### Обоснование

- `chat_member` (не `my_chat_member`) отслеживает изменения статуса **других пользователей** в чате
- Позволяет зарегистрировать участника в момент вступления, а не при первом сообщении

### Ключевые детали

**КРИТИЧЕСКИ ВАЖНО**: событие `chat_member` НЕ приходит по умолчанию. Необходимо:

1. Явно включить в `allowed_updates`:
```python
await dp.start_polling(
    bot,
    allowed_updates=dp.resolve_used_update_types(),
)
```
Метод `resolve_used_update_types()` автоматически собирает нужные типы из зарегистрированных обработчиков.

2. Бот ДОЛЖЕН быть администратором группы для получения `chat_member` событий.

```python
@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    new_user = event.new_chat_member.user
    chat_id = event.chat.id
    # Зарегистрировать как члена workspace

@router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_user_leave(event: ChatMemberUpdated):
    left_user = event.old_chat_member.user
    # Деактивировать членство
```

**Fallback**: если бот не админ и не получает `chat_member`, регистрировать пользователей при первом сообщении в группе (ленивая регистрация).

### Альтернативы рассмотрены

- Только ленивая регистрация (при первом сообщении) — пользователь не будет зарегистрирован до отправки сообщения, но это приемлемый fallback
- `content_types.NEW_CHAT_MEMBERS` в сообщениях — в новых версиях Telegram не всегда приходит, ненадёжно

---

## 5. Миграция группы в супергруппу (смена chat_id)

### Решение

Обрабатывать служебное сообщение `migrate_to_chat_id` и обновлять `chat_id` в базе данных.

### Обоснование

- Telegram автоматически конвертирует обычные группы в супергруппы при определённых действиях (назначение админов, включение истории, >200 участников)
- При миграции `chat_id` МЕНЯЕТСЯ: обычная группа `-XXXXXXXXX` → супергруппа `-100XXXXXXXXXX`
- Бот получает два служебных сообщения:
  - В старом чате: сообщение с `migrate_to_chat_id` (новый ID)
  - В новом чате: сообщение с `migrate_from_chat_id` (старый ID)

### Ключевые детали

```python
@router.message(F.migrate_to_chat_id)
async def on_group_migrated(message: Message):
    old_chat_id = message.chat.id
    new_chat_id = message.migrate_to_chat_id
    # UPDATE workspace SET telegram_chat_id = new_chat_id WHERE telegram_chat_id = old_chat_id
```

**Дополнительно**: при попытке отправить сообщение по старому ID, API вернёт ошибку `400` с `response.parameters.migrate_to_chat_id` — нужно обрабатывать и этот случай.

### Альтернативы рассмотрены

- Игнорировать миграцию — приведёт к потере связи с workspace, неприемлемо

---

## 6. Модель данных: Workspace вместо Family

### Решение

Создать модель `Workspace` (замена `Family`), связанную с `telegram_chat_id`. Модель `FamilyMember` переименовать в `WorkspaceMember` (или расширить связью M2M с workspace). Сущности `FamilyInvite` — удалить.

### Обоснование

- Текущая модель `Family` — singleton (одна семья на deploy)
- Спецификация требует: одна группа = один workspace, один deploy = много workspace'ов
- Один пользователь может быть в нескольких workspace'ах (группах)
- `telegram_chat_id` (BigInteger) — уникальный ключ привязки workspace к группе

### Ключевые детали

- `Workspace`: id, telegram_chat_id (unique), title, is_active, created_at, updated_at
- `WorkspaceMember`: workspace_id (FK) + telegram_user_id (FK) → composite unique
- `Pet`, `Vaccination`, и прочие health-модели → FK на `workspace_id` вместо `family_id`
- `ConversationState` → scope по `(user_id, workspace_id)` вместо просто `user_id`
- `FamilyInvite` → удалить модель и миграцию
- `FamilySettings` → `WorkspaceSettings` с FK на workspace_id

### Альтернативы рассмотрены

- Добавить `workspace_id` в `Family` и оставить как есть — семантически неверно, `Family` подразумевает singleton
- Мягкое переключение (feature flag) — усложняет код без пользы, спецификация однозначна

---

## 7. Webhook vs Polling: поддержка allowed_updates

### Решение

Для webhook — передать `allowed_updates` в `bot.set_webhook()`. Для polling — в `dp.start_polling()`.

### Обоснование

- Событие `chat_member` требует явного включения в `allowed_updates`
- Метод `dp.resolve_used_update_types()` автоматически определяет нужные типы
- В текущем коде `_setup_webhook()` вызывает `bot.set_webhook(url, secret_token)` — нужно добавить `allowed_updates`

### Ключевые детали

```python
# Dev (polling)
await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

# Prod (webhook)
await bot.set_webhook(
    url=webhook_url,
    secret_token=secret,
    allowed_updates=dp.resolve_used_update_types(),
)
```

### Альтернативы рассмотрены

- Захардкодить список `allowed_updates` — хрупко, будет рассинхронизироваться с обработчиками

---

## 8. Стратегия миграции существующих данных

### Решение

Миграция существующих данных **не входит в scope** этой фичи (явно указано в спецификации). Новая схема создаётся как дополнение, старые таблицы остаются до следующей итерации.

### Обоснование

- Спецификация: «Миграция существующих данных (если есть) на новую модель не входит в scope этой фичи»
- На текущем этапе нет production-данных, требующих миграции
- Alembic-миграция создаёт новые таблицы (`workspace`, `workspace_member`) и добавляет FK в существующие

### Альтернативы рассмотрены

- Автоматическая миграция Family → Workspace — за scope, нет production-данных
