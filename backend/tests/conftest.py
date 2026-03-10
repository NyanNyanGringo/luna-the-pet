"""
Корневые фикстуры тестового окружения Luna the Dog.

Предоставляет:
- async_engine (session): PostgreSQL (testcontainers или TEST_DATABASE_URL)
- tables (session): создание всех таблиц через metadata.create_all
- db_session (function): AsyncSession с откатом после каждого теста

Режимы работы:
- TEST_DATABASE_URL задан → используется внешний PostgreSQL (без Docker)
- TEST_DATABASE_URL не задан → testcontainers поднимает PostgreSQL в Docker
"""

import os
from collections.abc import AsyncGenerator

import pytest
from backend.app.db.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer


def _get_async_container_url(
    postgres_container: PostgresContainer | None,
) -> str:
    """Возвращает asyncpg URL testcontainer или поднимает понятную ошибку."""
    if postgres_container is None:
        raise RuntimeError(
            "postgres_container недоступен без Docker. "
            "Укажите TEST_DATABASE_URL или запустите testcontainers."
        )

    sync_url = postgres_container.get_connection_url()
    return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer | None:
    """Запускает PostgreSQL 16 контейнер на время всей тестовой сессии.

    Если задана TEST_DATABASE_URL — контейнер не создаётся (возвращает None).

    Возвращает:
        PostgresContainer | None: экземпляр контейнера или None

    Побочные эффекты:
        Контейнер останавливается автоматически по завершении сессии.
    """
    if os.environ.get("TEST_DATABASE_URL"):
        yield None
        return

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
    postgres_container: PostgresContainer | None,
) -> AsyncEngine:
    """Создаёт async engine для тестовой БД.

    Если TEST_DATABASE_URL задан — используется напрямую.
    Иначе — берёт URL из testcontainers.

    Аргументы:
        postgres_container: запущенный контейнер или None

    Возвращает:
        AsyncEngine: SQLAlchemy async engine, подключённый к тестовому PostgreSQL
    """
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        return create_async_engine(test_url, echo=False)

    async_url = _get_async_container_url(postgres_container)
    return create_async_engine(async_url, echo=False)


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
        if transaction.is_active:
            await transaction.rollback()
