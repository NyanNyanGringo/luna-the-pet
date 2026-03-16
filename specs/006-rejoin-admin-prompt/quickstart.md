# Quickstart: 006-rejoin-admin-prompt

## Обзор изменений

Фича затрагивает 3 файла:

| Файл | Тип изменения | Описание |
|------|--------------|----------|
| `backend/app/services/workspace_service.py` | Изменение сигнатуры | `get_or_create_workspace` возвращает `tuple[Workspace, bool]` вместо `Workspace` |
| `backend/app/bot/handlers/constants.py` | Новые константы + обновление существующих | `GROUP_REJOIN_TEXT`, `GROUP_REJOIN_ADMIN_TEXT`; обновление `GROUP_WELCOME_TEXT`, `HELP_GROUP_TEXT` |
| `backend/app/bot/handlers/group_events.py` | Обновление логики | Различение new/rejoin, проверка admin-статуса, выбор приветствия |

## Порядок реализации

1. **workspace_service.py**: изменить `get_or_create_workspace` — вернуть `(workspace, is_new)`. Все три пути (`_create_workspace_with_settings`, `_ensure_workspace_active`, `_adopt_legacy_workspace`) должны корректно выставлять `is_new`.

2. **constants.py**: добавить `GROUP_REJOIN_TEXT` и `GROUP_REJOIN_ADMIN_TEXT`, обновить `GROUP_WELCOME_TEXT` и `HELP_GROUP_TEXT` с упоминанием прав администратора.

3. **group_events.py**: обновить `handle_bot_membership_update` — распаковать `(workspace, is_new)`, проверить admin-статус бота через `bot.get_chat_member`, выбрать соответствующее приветствие.

## Ключевые решения

- `is_new=True` когда workspace **создан впервые** (ни разу не существовал для этого `chat_id`)
- `is_new=False` когда workspace найден (активный или реактивированный) или legacy workspace переназначен
- Admin-статус проверяется через `bot.get_chat_member(chat_id, bot.id)`, а не из события `my_chat_member`

## Тестирование

```bash
# Юнит-тесты
pytest tests/ -v

# Линтинг
backend/.venv/bin/pre-commit run --all-files
```

## Проверка вручную

1. Удалить бота из группы
2. Добавить бота обратно — должно появиться приветствие возвращения с просьбой об админ-правах
3. Добавить бота в новую группу — должно появиться стандартное приветствие с упоминанием админ-прав
4. Вызвать `/help` в группе — должно содержать напоминание о правах администратора
