"""
Тесты конфигурации приложения (Pydantic Settings).

Проверяет:
- Загрузку обязательных переменных окружения
- Значения по умолчанию (DEBUG, MEDIA_DIR)
- Опциональные поля (OAuth, JWT, Webhook)
- Валидацию формата DATABASE_URL и токенов

Все тесты используют monkeypatch для изоляции от реального окружения.
"""

import pytest
from backend.app.config import Settings

# ── Минимальный набор обязательных переменных для создания Settings ──────────

REQUIRED_ENV_VARIABLES = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/luna",
    "TELEGRAM_BOT_TOKEN": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
    "OPENAI_API_KEY": "sk-test-key-1234567890abcdef",
}


@pytest.fixture
def minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Устанавливает минимальный набор обязательных переменных окружения.

    Аргументы:
        monkeypatch: фикстура pytest для безопасной подмены env-переменных

    Побочные эффекты:
        Устанавливает DATABASE_URL, TELEGRAM_BOT_TOKEN, OPENAI_API_KEY.
    """
    for variable_name, variable_value in REQUIRED_ENV_VARIABLES.items():
        monkeypatch.setenv(variable_name, variable_value)


# ── Тесты загрузки обязательных переменных ──────────────────────────────────


class TestRequiredVariables:
    """Тесты загрузки и валидации обязательных переменных окружения."""

    def test_settings_loads_with_all_required_variables(
        self,
        minimal_env: None,
    ) -> None:
        """Settings создаётся без ошибок при наличии всех обязательных переменных."""
        settings = Settings()
        assert settings is not None

    def test_database_url_loaded_correctly(
        self,
        minimal_env: None,
    ) -> None:
        """DATABASE_URL корректно загружается из окружения."""
        settings = Settings()
        assert REQUIRED_ENV_VARIABLES["DATABASE_URL"] == settings.DATABASE_URL

    def test_telegram_bot_token_loaded_correctly(
        self,
        minimal_env: None,
    ) -> None:
        """TELEGRAM_BOT_TOKEN корректно загружается из окружения."""
        settings = Settings()
        expected_token = REQUIRED_ENV_VARIABLES["TELEGRAM_BOT_TOKEN"]
        assert expected_token == settings.TELEGRAM_BOT_TOKEN

    def test_openai_api_key_loaded_correctly(
        self,
        minimal_env: None,
    ) -> None:
        """OPENAI_API_KEY корректно загружается из окружения."""
        settings = Settings()
        assert REQUIRED_ENV_VARIABLES["OPENAI_API_KEY"] == settings.OPENAI_API_KEY

    def test_missing_database_url_raises_error(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Отсутствие DATABASE_URL вызывает ошибку валидации."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(Exception):  # noqa: B017, PT011
            Settings()

    def test_missing_telegram_bot_token_raises_error(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Отсутствие TELEGRAM_BOT_TOKEN вызывает ошибку валидации."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(Exception):  # noqa: B017, PT011
            Settings()

    def test_missing_openai_api_key_raises_error(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Отсутствие OPENAI_API_KEY вызывает ошибку валидации."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(Exception):  # noqa: B017, PT011
            Settings()


# ── Тесты значений по умолчанию ─────────────────────────────────────────────


class TestDefaultValues:
    """Тесты значений по умолчанию для необязательных переменных."""

    def test_debug_defaults_to_false(
        self,
        minimal_env: None,
    ) -> None:
        """DEBUG по умолчанию равен False."""
        settings = Settings()
        assert settings.DEBUG is False

    def test_media_dir_defaults_to_data_uploads(
        self,
        minimal_env: None,
    ) -> None:
        """MEDIA_DIR по умолчанию указывает на /data/uploads."""
        settings = Settings()
        assert settings.MEDIA_DIR == "/data/uploads"

    def test_debug_can_be_overridden_to_true(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """DEBUG можно переключить в True через переменную окружения."""
        monkeypatch.setenv("DEBUG", "true")
        settings = Settings()
        assert settings.DEBUG is True

    def test_media_dir_can_be_overridden(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MEDIA_DIR можно переопределить через переменную окружения."""
        custom_path = "/custom/media/path"
        monkeypatch.setenv("MEDIA_DIR", custom_path)
        settings = Settings()
        assert custom_path == settings.MEDIA_DIR


# ── Тесты опциональных полей ────────────────────────────────────────────────


class TestOptionalFields:
    """Тесты опциональных полей конфигурации."""

    def test_openai_oauth_client_id_is_optional(
        self,
        minimal_env: None,
    ) -> None:
        """OPENAI_OAUTH_CLIENT_ID может отсутствовать (None по умолчанию)."""
        settings = Settings()
        assert settings.OPENAI_OAUTH_CLIENT_ID is None

    def test_openai_oauth_client_id_loads_when_set(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPENAI_OAUTH_CLIENT_ID загружается при наличии в окружении."""
        client_id = "test-oauth-client-id"
        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", client_id)
        settings = Settings()
        assert client_id == settings.OPENAI_OAUTH_CLIENT_ID

    def test_oauth_encryption_key_is_optional(
        self,
        minimal_env: None,
    ) -> None:
        """OAUTH_ENCRYPTION_KEY может отсутствовать (None по умолчанию)."""
        settings = Settings()
        assert settings.OAUTH_ENCRYPTION_KEY is None

    def test_oauth_encryption_key_loads_when_set(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OAUTH_ENCRYPTION_KEY загружается при наличии в окружении."""
        encryption_key = "test-fernet-key-base64"
        monkeypatch.setenv("OAUTH_ENCRYPTION_KEY", encryption_key)
        settings = Settings()
        assert encryption_key == settings.OAUTH_ENCRYPTION_KEY

    def test_jwt_secret_is_optional(
        self,
        minimal_env: None,
    ) -> None:
        """JWT_SECRET может отсутствовать (None по умолчанию)."""
        settings = Settings()
        assert settings.JWT_SECRET is None

    def test_jwt_secret_loads_when_set(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JWT_SECRET загружается при наличии в окружении."""
        jwt_secret = "super-secret-jwt-key"
        monkeypatch.setenv("JWT_SECRET", jwt_secret)
        settings = Settings()
        assert jwt_secret == settings.JWT_SECRET

    def test_webhook_url_is_optional(
        self,
        minimal_env: None,
    ) -> None:
        """WEBHOOK_URL может отсутствовать (None по умолчанию)."""
        settings = Settings()
        assert settings.WEBHOOK_URL is None

    def test_webhook_url_loads_when_set(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """WEBHOOK_URL загружается при наличии в окружении."""
        webhook_url = "https://example.com/webhook"
        monkeypatch.setenv("WEBHOOK_URL", webhook_url)
        settings = Settings()
        assert webhook_url == settings.WEBHOOK_URL

    def test_webhook_secret_is_optional(
        self,
        minimal_env: None,
    ) -> None:
        """WEBHOOK_SECRET может отсутствовать (None по умолчанию)."""
        settings = Settings()
        assert settings.WEBHOOK_SECRET is None

    def test_webhook_secret_loads_when_set(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """WEBHOOK_SECRET загружается при наличии в окружении."""
        webhook_secret = "webhook-verification-secret"
        monkeypatch.setenv("WEBHOOK_SECRET", webhook_secret)
        settings = Settings()
        assert webhook_secret == settings.WEBHOOK_SECRET


# ── Тесты валидации формата ──────────────────────────────────────────────────


class TestFormatValidation:
    """Тесты валидации формата значений конфигурации."""

    def test_database_url_contains_asyncpg_driver(
        self,
        minimal_env: None,
    ) -> None:
        """DATABASE_URL должен содержать asyncpg-драйвер для async engine."""
        settings = Settings()
        assert "asyncpg" in settings.DATABASE_URL

    def test_telegram_bot_token_is_nonempty_string(
        self,
        minimal_env: None,
    ) -> None:
        """TELEGRAM_BOT_TOKEN не может быть пустой строкой."""
        settings = Settings()
        assert len(settings.TELEGRAM_BOT_TOKEN) > 0

    def test_openai_api_key_is_nonempty_string(
        self,
        minimal_env: None,
    ) -> None:
        """OPENAI_API_KEY не может быть пустой строкой."""
        settings = Settings()
        assert len(settings.OPENAI_API_KEY) > 0
