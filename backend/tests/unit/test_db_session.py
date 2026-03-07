"""
Тесты модуля сессии базы данных (backend.app.db.session).

Проверяет:
- Создание async engine с asyncpg-драйвером
- Создание async_session_maker с expire_on_commit=False
- Корректную конфигурацию фабрики сессий
"""

from backend.app.db.session import async_engine, async_session_maker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class TestAsyncEngine:
    """Тесты создания и конфигурации async engine."""

    def test_async_engine_is_created(self) -> None:
        """async_engine существует и является экземпляром AsyncEngine."""
        assert async_engine is not None
        assert isinstance(async_engine, AsyncEngine)

    def test_async_engine_uses_asyncpg_driver(self) -> None:
        """async_engine использует asyncpg как драйвер."""
        driver_name = async_engine.dialect.name
        assert driver_name == "postgresql", (
            f"Ожидался драйвер postgresql (asyncpg), получен: {driver_name}"
        )


class TestAsyncSessionMaker:
    """Тесты фабрики async сессий."""

    def test_async_session_maker_is_created(self) -> None:
        """async_session_maker существует и является async_sessionmaker."""
        assert async_session_maker is not None
        assert isinstance(async_session_maker, async_sessionmaker)

    def test_session_maker_produces_async_session(self) -> None:
        """async_session_maker создаёт экземпляр AsyncSession."""
        session = async_session_maker()
        assert isinstance(session, AsyncSession)

    def test_session_has_expire_on_commit_false(self) -> None:
        """Сессия создаётся с expire_on_commit=False.

        Это необходимо для корректной работы с async — без этого
        доступ к атрибутам после commit вызовет ошибку lazy-load.
        """
        session = async_session_maker()
        assert session.expire_on_commit is False
