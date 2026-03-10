"""
Фикстуры для юнит-тестов: установка и очистка переменных окружения.

Автоматически устанавливает минимальные env-переменные для корректного
импорта модуля session.py (Settings загружается на уровне модуля),
а затем очищает их, чтобы тесты конфигурации корректно проверяли
отсутствие обязательных переменных.

Также блокирует чтение .env файла во время тестов через патч model_config
и _resolve_env_file, чтобы реальный .env проекта не влиял на результаты тестов.
"""

import os

import pytest
from backend.app import config as config_module
from backend.app.config import Settings
from pydantic_settings import SettingsConfigDict

# Минимальные значения для импорта session.py (Settings на уровне модуля)
_SESSION_ENV_VARIABLES = {
    "APP_ENV": "dev",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "TELEGRAM_BOT_TOKEN": "000000000:test-token-for-session-import",
    "OPENAI_API_KEY": "sk-test-session-import-key",
}

# Опциональные переменные, которые должны быть очищены в каждом тесте —
# предотвращает утечку значений из .env или системного окружения
_OPTIONAL_ENV_VARIABLES = [
    "APP_ENV",
    "OPENAI_OAUTH_CLIENT_ID",
    "OAUTH_ENCRYPTION_KEY",
    "JWT_SECRET",
    "WEBHOOK_URL",
    "WEBHOOK_SECRET",
    "MEDIA_DIR",
    "DEBUG",
]


@pytest.fixture(autouse=True)
def _isolate_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Изолирует Settings от .env файла и очищает опциональные переменные.

    Блокирует чтение .env файла, устанавливает обязательные переменные
    (для модулей с module-level Settings()) и очищает опциональные.

    Побочные эффекты:
        - Патчит Settings.model_config.env_file на None (отключает .env)
        - Устанавливает обязательные переменные (DATABASE_URL и др.)
        - Удаляет опциональные переменные из os.environ
    """
    # Блокируем чтение .env файла — тесты должны быть изолированы
    monkeypatch.setattr(
        Settings,
        "model_config",
        SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore"),
    )
    monkeypatch.setattr(config_module, "_resolve_env_file", lambda: None)

    # Очищаем опциональные переменные — они не должны утекать из .env
    for variable_name in _OPTIONAL_ENV_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)

    # Устанавливаем обязательные переменные — они нужны всем модулям
    for variable_name, variable_value in _SESSION_ENV_VARIABLES.items():
        monkeypatch.setenv(variable_name, variable_value)


def _ensure_session_env_and_preimport() -> None:
    """Устанавливает env-переменные и заранее импортирует session.py.

    Вызывается до сбора тестов, чтобы Settings() на уровне модуля
    session.py не вызвал ValidationError при import.
    Принудительный импорт гарантирует, что module-level Settings()
    выполнится ДО того, как autouse-фикстура очистит окружение.

    Побочные эффекты:
        Устанавливает DATABASE_URL, TELEGRAM_BOT_TOKEN, OPENAI_API_KEY
        в os.environ и импортирует session.py, deps.py, create.py.
    """
    for variable_name in _OPTIONAL_ENV_VARIABLES:
        os.environ.pop(variable_name, None)

    for variable_name, variable_value in _SESSION_ENV_VARIABLES.items():
        os.environ[variable_name] = variable_value

    # Принудительно импортируем модули с module-level Settings(),
    # чтобы они инициализировались до очистки окружения фикстурой
    import backend.app.api.deps
    import backend.app.bot.create
    import backend.app.db.session
    import backend.app.main  # noqa: F401


# Устанавливаем env-переменные и импортируем модули ДО сбора тестов
_ensure_session_env_and_preimport()
