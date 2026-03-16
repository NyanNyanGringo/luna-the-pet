"""
Конфигурация приложения Luna the Dog через Pydantic Settings.

Загружает обязательные и опциональные переменные окружения из `.env.{APP_ENV}`
файла (fallback: `.env`) или системного окружения. APP_ENV читается из
системного окружения ДО инициализации Settings.

Обязательные переменные: DATABASE_URL, TELEGRAM_BOT_TOKEN, OPENAI_API_KEY.
"""

import os
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

PROJECT_ROOT_DIRECTORY = Path(__file__).resolve().parents[2]


def _resolve_env_file() -> str | None:
    """Определяет путь к .env файлу на основе APP_ENV из системного окружения.

    Правила загрузки (см. contracts/env-files.md):
    1. APP_ENV читается из os.environ ДО загрузки .env файла
    2. Если APP_ENV не задан → по умолчанию "dev"
    3. Ищется файл `.env.{APP_ENV}`
    4. Если не найден → fallback на `.env`
    5. Если ни один не найден → None (только системные переменные)
    """
    app_env = os.environ.get("APP_ENV", "dev")
    env_specific = PROJECT_ROOT_DIRECTORY / f".env.{app_env}"
    if env_specific.is_file():
        return str(env_specific)
    env_fallback = PROJECT_ROOT_DIRECTORY / ".env"
    if env_fallback.is_file():
        return str(env_fallback)
    return None


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из переменных окружения.

    Обязательные поля:
        DATABASE_URL: строка подключения к PostgreSQL (asyncpg)
        TELEGRAM_BOT_TOKEN: токен Telegram-бота
        OPENAI_API_KEY: ключ API OpenAI

    Опциональные поля:
        APP_ENV: режим работы ("dev" или "prod", по умолчанию "dev")
        JWT_SECRET: секрет для подписи JWT
        WEBHOOK_URL: URL вебхука для Telegram
        WEBHOOK_SECRET: секрет верификации вебхука
        MEDIA_DIR: путь к директории загрузок (по умолчанию /data/uploads)
        DEBUG: режим отладки (по умолчанию False)

    Побочные эффекты:
        Читает .env.{APP_ENV} файл при инициализации (fallback: .env).
    """

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    # --- Режим работы ---
    APP_ENV: Literal["dev", "prod"] = "dev"

    # --- Обязательные переменные ---
    DATABASE_URL: str
    TELEGRAM_BOT_TOKEN: str
    OPENAI_API_KEY: str

    # --- Безопасность ---
    JWT_SECRET: str | None = None

    # --- Вебхук ---
    WEBHOOK_URL: str | None = None
    WEBHOOK_SECRET: str | None = None

    # --- Приложение ---
    MEDIA_DIR: str = "/data/uploads"
    DEBUG: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Настраивает динамическую загрузку `.env.{APP_ENV}` для каждого Settings()."""
        resolved_env_file = _resolve_env_file()
        if resolved_env_file is None:
            return init_settings, env_settings, file_secret_settings

        dynamic_dotenv_settings = DotEnvSettingsSource(
            settings_cls,
            env_file=resolved_env_file,
            env_file_encoding=cls.model_config.get("env_file_encoding"),
        )
        return (
            init_settings,
            env_settings,
            dynamic_dotenv_settings,
            file_secret_settings,
        )

    @model_validator(mode="after")
    def _validate_prod_webhook(self) -> "Settings":
        """В prod-режиме WEBHOOK_URL обязателен."""
        if self.APP_ENV == "prod" and not self.WEBHOOK_URL:
            msg = "WEBHOOK_URL обязателен в prod-режиме (APP_ENV=prod)"
            raise ValueError(msg)
        return self
