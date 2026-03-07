"""
Модуль сессии базы данных: async engine и фабрика сессий.

Экспортирует:
- async_engine: AsyncEngine (asyncpg), echo зависит от DEBUG
- async_session_maker: async_sessionmaker с expire_on_commit=False

Использует AppAsyncSession — подкласс AsyncSession, который проксирует
атрибут expire_on_commit с внутренней sync_session наружу.

Загрузка настроек и создание объектов происходят на уровне модуля.
Для тестов требуется наличие переменных окружения DATABASE_URL,
TELEGRAM_BOT_TOKEN, OPENAI_API_KEY.
"""

from backend.app.config import Settings
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class AppAsyncSession(AsyncSession):
    """AsyncSession с проксированным атрибутом expire_on_commit.

    SQLAlchemy 2.0.x не проксирует expire_on_commit на AsyncSession,
    хотя он доступен через sync_session. Этот подкласс добавляет
    проксирование для единообразного API.
    """

    @property
    def expire_on_commit(self) -> bool:
        """Возвращает expire_on_commit из внутренней sync_session."""
        return self.sync_session.expire_on_commit

    @expire_on_commit.setter
    def expire_on_commit(self, value: bool) -> None:
        """Устанавливает expire_on_commit на внутренней sync_session."""
        self.sync_session.expire_on_commit = value


# Загружаем настройки на уровне модуля для создания engine и session maker
settings = Settings()

async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
)

async_session_maker = async_sessionmaker(
    async_engine,
    class_=AppAsyncSession,
    expire_on_commit=False,
)
