"""Точечные тесты миграций Wave 1 Alembic для US1."""

from __future__ import annotations

import ast
import asyncio
import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"
PHASE2_MIGRATION_PATH = (
    VERSIONS_DIR / "2026-03-07_9d200e74902b_initial_phase2_models.py"
)
US1_MIGRATION_PATH = (
    VERSIONS_DIR / "2026-03-07_7f0ce16e469b_add_us1_models_health_nutrition_.py"
)


def _read_python_source(file_path: Path) -> str:
    """Возвращает исходный код Python-файла в UTF-8."""
    return file_path.read_text(encoding="utf-8")


def _extract_function_source(file_path: Path, function_name: str) -> str:
    """Возвращает исходник функции по имени из заданного файла миграции."""
    module_source = _read_python_source(file_path)
    module_tree = ast.parse(module_source)
    function_node = next(
        node
        for node in module_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    return ast.get_source_segment(module_source, function_node) or ""


def _extract_module_constant(file_path: Path, constant_name: str) -> object:
    """Возвращает значение module-level константы из Assign/AnnAssign."""
    module_tree = ast.parse(_read_python_source(file_path))
    for node in module_tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == constant_name
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == constant_name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Не найдена константа {constant_name} в {file_path}")


def _build_async_database_url(
    postgres_container: PostgresContainer,
    database_name: str,
) -> str:
    """Возвращает asyncpg URL к указанной БД внутри testcontainer."""
    connection_url = postgres_container.get_connection_url()
    asyncpg_url = connection_url.replace(
        "postgresql+psycopg2://",
        "postgresql+asyncpg://",
    )
    return (
        make_url(asyncpg_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def _build_postgres_cli_env(database_url: str) -> dict[str, str]:
    """Собирает окружение для psql/createdb/dropdb из URL подключения."""
    parsed_url = make_url(database_url)
    return {
        **os.environ,
        "PGHOST": parsed_url.host or "localhost",
        "PGPORT": str(parsed_url.port or 5432),
        "PGUSER": parsed_url.username or "",
        "PGPASSWORD": parsed_url.password or "",
    }


def _run_postgres_cli(command_parts: list[str], database_url: str) -> str:
    """Запускает PostgreSQL CLI-команду и возвращает stdout."""
    result = subprocess.run(
        command_parts,
        check=True,
        capture_output=True,
        text=True,
        env=_build_postgres_cli_env(database_url),
    )
    return result.stdout.strip()


def _create_database(admin_database_url: str, database_name: str) -> None:
    """Создаёт временную БД для runtime-проверки миграций."""
    admin_database_name = make_url(admin_database_url).database or "postgres"
    _run_postgres_cli(
        [
            "createdb",
            "--maintenance-db",
            admin_database_name,
            database_name,
        ],
        admin_database_url,
    )


def _drop_database(admin_database_url: str, database_name: str) -> None:
    """Удаляет временную БД после runtime-проверки миграций."""
    admin_database_name = make_url(admin_database_url).database or "postgres"
    _run_postgres_cli(
        [
            "dropdb",
            "--if-exists",
            "--force",
            "--maintenance-db",
            admin_database_name,
            database_name,
        ],
        admin_database_url,
    )


def _table_exists(database_url: str, table_name: str) -> bool:
    """Проверяет наличие таблицы в public-схеме целевой БД."""
    return asyncio.run(_read_table_exists(database_url, table_name))


async def _read_table_exists(database_url: str, table_name: str) -> bool:
    """Проверяет наличие таблицы через async engine и SQLAlchemy inspector."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.connect() as database_connection:
            return await database_connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table(
                    table_name,
                    schema="public",
                )
            )
    finally:
        await database_engine.dispose()


def _get_alembic_version(database_url: str) -> str:
    """Возвращает текущую revision из alembic_version."""
    database_name = make_url(database_url).database or "postgres"
    return _run_postgres_cli(
        [
            "psql",
            "-d",
            database_name,
            "-tAc",
            "SELECT version_num FROM alembic_version",
        ],
        database_url,
    )


def _build_alembic_config(database_url: str) -> Config:
    """Собирает Alembic Config с абсолютным путём к alembic.ini."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


class TestUS1MigrationNoFamilySingletonDuplication:
    """Проверяет отсутствие повторного изменения family.singleton_key в US1."""

    def test_upgrade_has_no_family_singleton_add_ops(self) -> None:
        """В upgrade() не должно быть add_column/create_unique_constraint."""
        upgrade_source = _extract_function_source(US1_MIGRATION_PATH, "upgrade")
        assert (
            re.search(
                r"op\.add_column\(\s*['\"]family['\"]\s*,\s*sa\.Column\(\s*['\"]singleton_key['\"]",
                upgrade_source,
            )
            is None
        )
        assert (
            re.search(
                r"op\.create_unique_constraint\(\s*['\"]uq_family_singleton['\"]\s*,\s*['\"]family['\"]",
                upgrade_source,
            )
            is None
        )

    def test_downgrade_has_no_family_singleton_drop_ops(self) -> None:
        """В downgrade() не должно быть drop_constraint/drop_column."""
        downgrade_source = _extract_function_source(US1_MIGRATION_PATH, "downgrade")
        assert (
            re.search(
                r"op\.drop_constraint\(\s*['\"]uq_family_singleton['\"]\s*,\s*['\"]family['\"]",
                downgrade_source,
            )
            is None
        )
        assert (
            re.search(
                r"op\.drop_column\(\s*['\"]family['\"]\s*,\s*['\"]singleton_key['\"]",
                downgrade_source,
            )
            is None
        )


class TestUS1MigrationRevisionChain:
    """Проверяет линейность цепочки revision/down_revision для двух миграций."""

    def test_us1_revision_points_to_phase2(self) -> None:
        """US1-миграция обязана ссылаться на 9d200e74902b без ветвления."""
        phase2_revision = _extract_module_constant(PHASE2_MIGRATION_PATH, "revision")
        phase2_down_revision = _extract_module_constant(
            PHASE2_MIGRATION_PATH, "down_revision"
        )
        us1_down_revision = _extract_module_constant(
            US1_MIGRATION_PATH, "down_revision"
        )
        assert phase2_revision == "9d200e74902b"
        assert phase2_down_revision is None
        assert us1_down_revision == phase2_revision


class TestUS1MigrationRuntimeRoundtrip:
    """Проверяет runtime roundtrip для линейной цепочки US1-миграций."""

    def test_upgrade_downgrade_upgrade_roundtrip(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch,
    ) -> None:
        """Проверяет воспроизводимую цепочку base->phase2->us1->phase2->us1."""
        if postgres_container is None:
            pytest.skip(
                "Runtime roundtrip миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"us1_roundtrip_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container, database_name
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, "9d200e74902b")
            assert _get_alembic_version(target_database_url) == "9d200e74902b"
            assert _table_exists(target_database_url, "change_log") is True
            assert _table_exists(target_database_url, "feeding_entry") is False

            command.upgrade(alembic_config, "7f0ce16e469b")
            assert _get_alembic_version(target_database_url) == "7f0ce16e469b"
            assert _table_exists(target_database_url, "feeding_entry") is True

            command.downgrade(alembic_config, "9d200e74902b")
            assert _get_alembic_version(target_database_url) == "9d200e74902b"
            assert _table_exists(target_database_url, "change_log") is True
            assert _table_exists(target_database_url, "feeding_entry") is False

            command.upgrade(alembic_config, "7f0ce16e469b")
            assert _get_alembic_version(target_database_url) == "7f0ce16e469b"
            assert _table_exists(target_database_url, "feeding_entry") is True
        finally:
            _drop_database(admin_database_url, database_name)
