"""
Корневые фикстуры тестового окружения Luna the Dog.

Предоставляет:
- async_engine (session): PostgreSQL контейнер, возвращает AsyncEngine
- tables (session): создание всех таблиц через metadata.create_all
- db_session (function): AsyncSession с откатом после каждого теста

Требования:
- Docker должен быть запущен для testcontainers
- Все модели должны быть импортированы в backend.app.db.models.__init__
"""

from collections.abc import AsyncGenerator

import pytest
from backend.app.db.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Запускает PostgreSQL 16 контейнер на время всей тестовой сессии.

    Возвращает:
        PostgresContainer: экземпляр запущенного контейнера

    Побочные эффекты:
        Контейнер останавливается автоматически по завершении сессии.
    """
    container = PostgresContainer(
        image="postgres:16",
        username="test_user",
        password="test_password",
        dbname="test_luna",
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def async_engine(
    postgres_container: PostgresContainer,
) -> AsyncEngine:
    """Создаёт async engine (asyncpg) для тестовой БД.

    Аргументы:
        postgres_container: запущенный PostgreSQL контейнер

    Возвращает:
        AsyncEngine: SQLAlchemy async engine, подключённый к тестовому PostgreSQL

    Побочные эффекты:
        Engine закрывается вместе с контейнером по завершении сессии.
    """
    # testcontainers отдаёт psycopg2-формат URL, заменяем на asyncpg
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    engine = create_async_engine(async_url, echo=False)
    return engine


@pytest.fixture(scope="session")
async def tables(async_engine: AsyncEngine) -> None:
    """Создаёт все таблицы из Base.metadata в тестовой БД.

    Аргументы:
        async_engine: async engine, подключённый к тестовому PostgreSQL

    Побочные эффекты:
        Таблицы создаются при старте, удаляются по завершении сессии.
        Импортирует все модели для регистрации в metadata.
    """
    # Импортируем все модели, чтобы они были зарегистрированы в Base.metadata
    import backend.app.db.models  # noqa: F401

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield  # type: ignore[misc]

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(
    async_engine: AsyncEngine,
    tables: None,
) -> AsyncGenerator[AsyncSession, None]:
    """Создаёт AsyncSession для одного теста с откатом по завершении.

    Каждый тест получает собственную транзакцию, которая откатывается
    после выполнения — данные между тестами не пересекаются.

    Аргументы:
        async_engine: async engine из фикстуры async_engine
        tables: зависимость на создание таблиц

    Возвращает:
        AsyncSession: сессия с expire_on_commit=False

    Побочные эффекты:
        Транзакция откатывается после каждого теста.
    """
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
        )

        yield session

        await session.close()
        await transaction.rollback()
