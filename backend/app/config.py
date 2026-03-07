"""
Конфигурация приложения Luna the Dog через Pydantic Settings.

Загружает обязательные и опциональные переменные окружения из `.env` файла
или системного окружения. Используется всеми модулями для доступа к настройкам.

Обязательные переменные: DATABASE_URL, TELEGRAM_BOT_TOKEN, OPENAI_API_KEY.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT_DIRECTORY = Path(__file__).resolve().parents[2]
ROOT_ENV_FILE_PATH = str(PROJECT_ROOT_DIRECTORY / ".env")
"""Абсолютный путь к единственному .env в корне репозитория."""


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из переменных окружения.

    Обязательные поля:
        DATABASE_URL: строка подключения к PostgreSQL (asyncpg)
        TELEGRAM_BOT_TOKEN: токен Telegram-бота
        OPENAI_API_KEY: ключ API OpenAI

    Опциональные поля:
        OPENAI_OAUTH_CLIENT_ID: OAuth client ID для OpenAI
        OAUTH_ENCRYPTION_KEY: ключ шифрования OAuth-токенов (Fernet)
        JWT_SECRET: секрет для подписи JWT
        WEBHOOK_URL: URL вебхука для Telegram
        WEBHOOK_SECRET: секрет верификации вебхука
        MEDIA_DIR: путь к директории загрузок (по умолчанию /data/uploads)
        DEBUG: режим отладки (по умолчанию False)

    Побочные эффекты:
        Читает .env файл при инициализации (если существует).
    """

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Обязательные переменные ---
    DATABASE_URL: str
    TELEGRAM_BOT_TOKEN: str
    OPENAI_API_KEY: str

    # --- OAuth и безопасность ---
    OPENAI_OAUTH_CLIENT_ID: str | None = None
    OAUTH_ENCRYPTION_KEY: str | None = None
    JWT_SECRET: str | None = None

    # --- Вебхук ---
    WEBHOOK_URL: str | None = None
    WEBHOOK_SECRET: str | None = None

    # --- Приложение ---
    MEDIA_DIR: str = "/data/uploads"
    DEBUG: bool = False
