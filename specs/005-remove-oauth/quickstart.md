# Quickstart: Удаление функционала OAuth

**Дата**: 2026-03-14
**Ветка**: `005-remove-oauth`

## Порядок реализации

Задачи выполняются в строгой последовательности — каждый шаг зависит от предыдущего.

### Шаг 1: Удалить OAuth-сервис и эндпоинт

1. Удалить файл `backend/app/services/openai_auth_service.py`
2. Удалить файл `backend/app/api/auth.py`
3. В `backend/app/main.py`:
   - Удалить импорт `auth_router`
   - Удалить `app.include_router(auth_router)`

**Проверка**: приложение запускается без ошибок импорта.

### Шаг 2: Упростить OpenAI-клиент в brain.py

1. В `backend/app/agent/brain.py`:
   - Заменить вызов `get_openai_client(session, member_id)` на прямое создание `AsyncOpenAI(api_key=settings.OPENAI_API_KEY)`
   - Удалить импорт `get_openai_client`
   - Если `session` или `member_id` больше не нужны в контексте вызова — упростить сигнатуру

**Проверка**: бот отвечает на сообщения через API-ключ.

### Шаг 3: Удалить Telegram-команду /connectai

1. В `backend/app/bot/handlers/commands.py`:
   - Удалить функцию `handle_connectai()`
   - Удалить регистрацию `router.message.register(handle_connectai, ...)`
   - Удалить связанные импорты (если больше не используются)

**Проверка**: бот запускается, команды `/help` и `/invite` работают.

### Шаг 4: Удалить модель OAuthCredential

1. В `backend/app/db/models/family.py`:
   - Удалить класс `OAuthCredential`
   - Оставить класс `ConversationState`
2. В `backend/app/db/models/__init__.py`:
   - Удалить импорт и экспорт `OAuthCredential`

**Проверка**: импорт моделей работает, `ConversationState` доступен.

### Шаг 5: Создать миграцию для удаления таблицы

1. Создать Alembic-миграцию вручную:
   - `alembic revision -m "drop_oauth_credential_table"`
   - В `upgrade()`: `op.drop_table('oauth_credential')`
   - В `downgrade()`: воссоздать таблицу с полной схемой

**Проверка**: `alembic upgrade head` и `alembic downgrade -1` выполняются без ошибок.

### Шаг 6: Очистить конфигурацию

1. В `backend/app/config.py`:
   - Удалить поля `OPENAI_OAUTH_CLIENT_ID` и `OAUTH_ENCRYPTION_KEY`
   - Удалить связанные комментарии
2. В `.env.example`:
   - Удалить строки с `OPENAI_OAUTH_CLIENT_ID` и `OAUTH_ENCRYPTION_KEY`

**Проверка**: приложение запускается без OAuth-переменных.

### Шаг 7: Очистить зависимости

1. В `backend/requirements.txt`:
   - Удалить `cryptography>=44.0.0`
   - Удалить `httpx>=0.28.0`
   - Оставить `python-jose[cryptography]>=3.3.0` (используется для JWT)

**Проверка**: `pip install -r requirements.txt` успешно, приложение запускается.

### Шаг 8: Очистить тесты

1. Удалить файл `backend/tests/unit/test_openai_auth.py`
2. В `backend/tests/unit/conftest.py`:
   - Удалить `OPENAI_OAUTH_CLIENT_ID` и `OAUTH_ENCRYPTION_KEY` из `_OPTIONAL_ENV_VARIABLES`
3. В `backend/tests/unit/test_config.py`:
   - Удалить тесты OAuth-специфичных полей

**Проверка**: `pytest` проходит — все оставшиеся тесты зелёные.

### Шаг 9: Финальная верификация

1. Поиск по кодовой базе: `grep -r "oauth\|connectai\|PKCE\|code_verifier\|OAUTH_ENCRYPTION" backend/app/` — 0 результатов
2. Запуск всех тестов: `pytest` — все зелёные
3. Запуск линтера: `ruff check .` — без ошибок
4. Запуск type-checker: `mypy app/` — без ошибок

## Критические предостережения

- **НЕ трогать** `backend/app/api/deps.py` — это JWT-авторизация для API
- **НЕ удалять** `python-jose` — используется для JWT
- **НЕ удалять** `OPENAI_API_KEY` из конфигурации — это единственный оставшийся способ подключения
- **НЕ удалять** `JWT_SECRET` из конфигурации — нужен для API-авторизации
- Миграции в `alembic/versions/` НЕ редактировать (старые) — только создать новую
