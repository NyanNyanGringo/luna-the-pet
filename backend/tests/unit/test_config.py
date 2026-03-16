"""
Тесты конфигурации приложения (Pydantic Settings).

Проверяет:
- Загрузку обязательных переменных окружения
- Значения по умолчанию (DEBUG, MEDIA_DIR)
- Опциональные поля (JWT, Webhook)
- Валидацию формата DATABASE_URL и токенов

Все тесты используют monkeypatch для изоляции от реального окружения.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import backend.app.config as config_module
import pytest
from backend.app.config import Settings
from pydantic import ValidationError

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


def _write_env_file(file_path: Path, values: dict[str, str]) -> None:
    """Записывает .env файл из словаря ключ=значение."""
    env_file_content = "\n".join(f"{name}={value}" for name, value in values.items())
    file_path.write_text(env_file_content, encoding="utf-8")


def _load_isolated_config_module(source_file_path: Path) -> ModuleType:
    """Загружает backend.app.config как отдельный модуль с чистым кэшем."""
    module_name = f"isolated_backend_app_config_{uuid4().hex}"
    module_spec = importlib.util.spec_from_file_location(module_name, source_file_path)
    if module_spec is None or module_spec.loader is None:
        msg = "Не удалось создать module spec для backend.app.config"
        raise RuntimeError(msg)

    isolated_module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = isolated_module
    module_spec.loader.exec_module(isolated_module)
    return isolated_module


class TestEnvironmentContracts:
    """Контракты окружений dev/prod для Settings."""

    def test_prod_without_webhook_url_raises_validation_error(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """В APP_ENV=prod поле WEBHOOK_URL обязательно."""
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.delenv("WEBHOOK_URL", raising=False)

        with pytest.raises(ValidationError, match="WEBHOOK_URL обязателен"):
            Settings()

    def test_dev_allows_missing_webhook_url(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """В APP_ENV=dev отсутствие WEBHOOK_URL допустимо."""
        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.delenv("WEBHOOK_URL", raising=False)

        settings = Settings()
        assert settings.APP_ENV == "dev"
        assert settings.WEBHOOK_URL is None

    def test_prod_accepts_webhook_url_when_present(
        self,
        minimal_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """В APP_ENV=prod экземпляр Settings создаётся при заданном WEBHOOK_URL."""
        webhook_url = "https://prod.example.com/webhook"
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("WEBHOOK_URL", webhook_url)

        settings = Settings()
        assert settings.APP_ENV == "prod"
        assert webhook_url == settings.WEBHOOK_URL


class TestEnvFileResolution:
    """Тесты выбора env-файлов на основе APP_ENV."""

    def test_settings_reloads_env_file_when_app_env_changes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Settings должен выбирать .env файл заново при каждом создании."""
        for variable_name in (*REQUIRED_ENV_VARIABLES, "WEBHOOK_URL", "APP_ENV"):
            monkeypatch.delenv(variable_name, raising=False)

        isolated_root = tmp_path / "isolated_project"
        isolated_config_path = isolated_root / "backend" / "app" / "config.py"
        isolated_config_path.parent.mkdir(parents=True)
        source_file_path = Path(config_module.__file__)
        isolated_config_path.write_text(
            source_file_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        _write_env_file(
            isolated_root / ".env.dev",
            {
                "DATABASE_URL": "postgresql+asyncpg://dev_user:dev_pass@localhost:5432/dev_db",
                "TELEGRAM_BOT_TOKEN": "111111111:dev-token",
                "OPENAI_API_KEY": "sk-dev-key",
                "WEBHOOK_URL": "https://dev.example.com/webhook",
            },
        )
        _write_env_file(
            isolated_root / ".env.prod",
            {
                "DATABASE_URL": "postgresql+asyncpg://prod_user:prod_pass@localhost:5432/prod_db",
                "TELEGRAM_BOT_TOKEN": "222222222:prod-token",
                "OPENAI_API_KEY": "sk-prod-key",
                "WEBHOOK_URL": "https://prod.example.com/webhook",
            },
        )

        monkeypatch.setenv("APP_ENV", "dev")
        isolated_module = _load_isolated_config_module(isolated_config_path)
        dev_settings = isolated_module.Settings()
        assert dev_settings.DATABASE_URL.endswith("/dev_db")

        monkeypatch.setenv("APP_ENV", "prod")
        prod_settings = isolated_module.Settings()
        assert prod_settings.DATABASE_URL.endswith("/prod_db")

    def test_settings_uses_dotenv_fallback_when_env_specific_file_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """При отсутствии .env.{APP_ENV} используется fallback файл .env."""
        for variable_name in (*REQUIRED_ENV_VARIABLES, "WEBHOOK_URL", "APP_ENV"):
            monkeypatch.delenv(variable_name, raising=False)

        isolated_root = tmp_path / "isolated_project"
        isolated_config_path = isolated_root / "backend" / "app" / "config.py"
        isolated_config_path.parent.mkdir(parents=True)
        source_file_path = Path(config_module.__file__)
        isolated_config_path.write_text(
            source_file_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        _write_env_file(
            isolated_root / ".env",
            {
                "DATABASE_URL": "postgresql+asyncpg://fallback:fallback@localhost:5432/fallback_db",
                "TELEGRAM_BOT_TOKEN": "333333333:fallback-token",
                "OPENAI_API_KEY": "sk-fallback-key",
            },
        )

        monkeypatch.setenv("APP_ENV", "dev")
        isolated_module = _load_isolated_config_module(isolated_config_path)
        fallback_settings = isolated_module.Settings()
        assert fallback_settings.DATABASE_URL.endswith("/fallback_db")
