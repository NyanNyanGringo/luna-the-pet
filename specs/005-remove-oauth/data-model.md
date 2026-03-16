# Изменения модели данных: Удаление OAuth

**Дата**: 2026-03-14

## Удаляемые сущности

### OAuthCredential (DROP TABLE)

Таблица `oauth_credential` удаляется полностью. Хранила зашифрованные OAuth-токены пользователей для доступа к OpenAI через авторизацию.

**Текущая схема (для миграции downgrade)**:

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | Первичный ключ |
| telegram_user_id | BIGINT NOT NULL | ID пользователя Telegram |
| provider | VARCHAR(50) DEFAULT 'openai' | Провайдер OAuth |
| access_token_enc | TEXT NOT NULL | Зашифрованный access token |
| refresh_token_enc | TEXT NOT NULL | Зашифрованный refresh token |
| expires_at | TIMESTAMP WITH TZ NOT NULL | Время истечения токена |
| status | VARCHAR(20) DEFAULT 'active' | Статус (active/revoked) |
| created_at | TIMESTAMP WITH TZ NOT NULL | Время создания |
| updated_at | TIMESTAMP WITH TZ NULL | Время обновления |

**Ограничения**: `UNIQUE (telegram_user_id, provider)`

**Связи**: Нет внешних ключей к/от этой таблицы. Изолирована от остальных моделей.

## Сохраняемые сущности

Все остальные модели и таблицы остаются без изменений:

- **ConversationState** (в том же файле `family.py`) — состояние диалога, не связан с OAuth
- **Workspace**, **WorkspaceMember** — workspace-модели, не затронуты
- Все таблицы питомцев, напоминаний и пр. — не затронуты

## Миграция

**Тип**: Alembic revision (autogenerate не подходит для DROP TABLE, создать вручную)

**Upgrade**: `DROP TABLE oauth_credential`
**Downgrade**: `CREATE TABLE oauth_credential` с полной схемой выше (пустая таблица)

**Важно**: Миграция необратимо удаляет данные из таблицы. Это приемлемо, так как OAuth-токены более не используются и не могут быть дешифрованы без `OAUTH_ENCRYPTION_KEY`.
