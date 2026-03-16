"""Runtime-проверки миграции workspace-only схемы."""

from __future__ import annotations

import asyncio
import datetime as datetime_module
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_REVISION = "a1b2c3d4e5f6"
PREVIOUS_REVISION = "d4e6c9b19f3a"
LEGACY_WORKSPACE_CHAT_ID_OFFSET = 2_000_000_000_000


def _build_async_database_url(
    postgres_container: PostgresContainer,
    database_name: str,
) -> str:
    """Собирает asyncpg URL к указанной базе внутри testcontainer."""
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


def _build_alembic_config(database_url: str) -> Config:
    """Возвращает Alembic Config с целевым DATABASE_URL."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _build_postgres_cli_env(database_url: str) -> dict[str, str]:
    """Готовит окружение для psql/createdb/dropdb из строки подключения."""
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
    """Создаёт временную БД для runtime-проверок миграций."""
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
    """Удаляет временную БД после завершения проверки."""
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


def _column_nullable(database_url: str, table_name: str, column_name: str) -> bool:
    """Возвращает nullable-признак указанной колонки."""
    return asyncio.run(_read_column_nullable(database_url, table_name, column_name))


async def _read_column_nullable(
    database_url: str,
    table_name: str,
    column_name: str,
) -> bool:
    """Читает nullable-метаданные колонки через SQLAlchemy inspector."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.connect() as database_connection:
            return await database_connection.run_sync(
                lambda sync_connection: next(
                    column["nullable"]
                    for column in inspect(sync_connection).get_columns(
                        table_name,
                        schema="public",
                    )
                    if column["name"] == column_name
                )
            )
    finally:
        await database_engine.dispose()


def _family_member_ids(database_url: str) -> list[int]:
    """Читает все ID из восстановленной family_member таблицы."""
    return asyncio.run(_read_family_member_ids(database_url))


async def _read_family_member_ids(database_url: str) -> list[int]:
    """Возвращает family_member.id после downgrade."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            result = await database_connection.execute(
                text("SELECT id FROM family_member ORDER BY id")
            )
            return [int(row[0]) for row in result]
    finally:
        await database_engine.dispose()


def _seed_workspace_activity_rows(database_url: str) -> None:
    """Добавляет данные, требующие family_member при downgrade."""
    asyncio.run(_insert_workspace_activity_rows(database_url))


def _seed_legacy_rows_for_workspace_upgrade(database_url: str) -> None:
    """Добавляет legacy-данные в family/pet перед upgrade до workspace."""
    asyncio.run(_insert_legacy_rows_for_workspace_upgrade(database_url))


def _count_null_values(database_url: str, table_name: str, column_name: str) -> int:
    """Считает строки с NULL в указанной колонке таблицы."""
    return asyncio.run(_read_null_values(database_url, table_name, column_name))


def _seed_legacy_conversation_state_for_upgrade(
    database_url: str,
) -> dict[str, int | datetime_module.datetime]:
    """Создаёт валидные legacy-данные conversation_state для upgrade-теста."""
    return asyncio.run(_insert_legacy_conversation_state_for_upgrade(database_url))


def _seed_legacy_conversation_state_duplicates_for_upgrade(
    database_url: str,
) -> dict[str, int | str | datetime_module.datetime]:
    """Создаёт дубликаты legacy conversation_state для проверки дедупликации."""
    return asyncio.run(
        _insert_legacy_conversation_state_duplicates_for_upgrade(database_url)
    )


def _seed_broken_legacy_conversation_state_for_upgrade(database_url: str) -> None:
    """Создаёт неконсистентную legacy-запись conversation_state без family_member."""
    asyncio.run(_insert_broken_legacy_conversation_state_for_upgrade(database_url))


def _seed_legacy_conversation_state_without_workspace_mapping_for_upgrade(
    database_url: str,
) -> None:
    """Создаёт legacy-запись conversation_state, не маппящуюся в workspace."""
    asyncio.run(
        _insert_legacy_conversation_state_without_workspace_mapping_for_upgrade(
            database_url
        )
    )


def _workspace_conversation_state_rows(
    database_url: str,
    telegram_user_id: int | None = None,
) -> list[dict[str, object]]:
    """Читает строки conversation_state в workspace-схеме."""
    return asyncio.run(
        _read_workspace_conversation_state_rows(database_url, telegram_user_id)
    )


def _legacy_conversation_state_rows(
    database_url: str,
    user_id: int | None = None,
) -> list[dict[str, object]]:
    """Читает строки conversation_state в legacy-схеме."""
    return asyncio.run(_read_legacy_conversation_state_rows(database_url, user_id))


def _workspace_chat_id_by_workspace_id(database_url: str, workspace_id: int) -> int:
    """Возвращает telegram_chat_id workspace по его первичному ключу."""
    return asyncio.run(
        _read_workspace_chat_id_by_workspace_id(database_url, workspace_id)
    )


def _seed_workspace_conversation_state_for_downgrade(
    database_url: str,
) -> dict[str, int | str | datetime_module.datetime]:
    """Создаёт одну workspace-запись conversation_state перед downgrade."""
    return asyncio.run(_insert_workspace_conversation_state_for_downgrade(database_url))


def _seed_workspace_conversation_state_duplicates_for_downgrade(
    database_url: str,
) -> dict[str, int | str | datetime_module.datetime]:
    """Создаёт конкурирующие workspace-записи для downgrade-policy."""
    return asyncio.run(
        _insert_workspace_conversation_state_duplicates_for_downgrade(database_url)
    )


def _conversation_state_trigger_exists(database_url: str) -> bool:
    """Проверяет наличие updated_at trigger у conversation_state."""
    return asyncio.run(_read_conversation_state_trigger_exists(database_url))


async def _insert_workspace_activity_rows(database_url: str) -> None:
    """Записывает тестовые строки в таблицы workspace-схемы."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            workspace_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO workspace (telegram_chat_id, title, is_active) "
                        "VALUES (-100555666777, 'Migration Workspace', true) "
                        "RETURNING id"
                    )
                )
            ).scalar_one()

            pet_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO pet "
                        "(name, species, is_neutered, is_active, "
                        "workspace_id, created_by) "
                        "VALUES ('Луна', 'dog', false, true, :workspace_id, 9003) "
                        "RETURNING id"
                    ),
                    {"workspace_id": workspace_id},
                )
            ).scalar_one()

            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(telegram_user_id, workspace_id, turn_count) "
                    "VALUES (9004, :workspace_id, 0)"
                ),
                {"workspace_id": workspace_id},
            )
            await database_connection.execute(
                text(
                    "INSERT INTO weight_record "
                    "(pet_id, weight_kg, measured_at, recorded_by) "
                    "VALUES (:pet_id, 10.50, CURRENT_DATE, 9002)"
                ),
                {"pet_id": pet_id},
            )
            await database_connection.execute(
                text(
                    "INSERT INTO change_log "
                    "(entity_type, entity_id, action, actor_id, workspace_id) "
                    "VALUES ('pet', :pet_id, 'update', 9001, :workspace_id)"
                ),
                {"pet_id": pet_id, "workspace_id": workspace_id},
            )
    finally:
        await database_engine.dispose()


async def _insert_legacy_rows_for_workspace_upgrade(database_url: str) -> None:
    """Записывает legacy-строки в schema до миграции workspace."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            family_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO family (singleton_key) VALUES (true) RETURNING id"
                    )
                )
            ).scalar_one()
            await database_connection.execute(
                text(
                    "INSERT INTO family_member "
                    "(id, first_name, username, is_authorized, family_id) "
                    "VALUES (9001, 'Legacy Owner', 'legacy_owner', true, :family_id)"
                ),
                {"family_id": family_id},
            )
            await database_connection.execute(
                text(
                    "INSERT INTO pet "
                    "(name, species, is_neutered, is_active, family_id, created_by) "
                    "VALUES ('Луна legacy', 'dog', false, true, :family_id, 9001)"
                ),
                {"family_id": family_id},
            )
    finally:
        await database_engine.dispose()


async def _insert_legacy_conversation_state_for_upgrade(
    database_url: str,
) -> dict[str, int | datetime_module.datetime]:
    """Создаёт одну legacy-строку conversation_state и связанные family-сущности."""
    updated_at_value = datetime_module.datetime(
        2026,
        3,
        10,
        11,
        30,
        tzinfo=datetime_module.UTC,
    )
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            family_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO family (singleton_key) VALUES (true) RETURNING id"
                    )
                )
            ).scalar_one()
            await database_connection.execute(
                text(
                    "INSERT INTO family_member "
                    "(id, first_name, username, is_authorized, family_id) "
                    "VALUES (9101, 'Legacy User', 'legacy_user', true, :family_id)"
                ),
                {"family_id": family_id},
            )
            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(user_id, last_response_id, turn_count, session_summary, "
                    "updated_at) "
                    "VALUES (9101, 'legacy-response', 4, 'legacy summary', :updated_at)"
                ),
                {"updated_at": updated_at_value},
            )
            return {
                "family_id": int(family_id),
                "telegram_user_id": 9101,
                "updated_at": updated_at_value,
            }
    finally:
        await database_engine.dispose()


async def _insert_legacy_conversation_state_duplicates_for_upgrade(
    database_url: str,
) -> dict[str, int | str | datetime_module.datetime]:
    """Создаёт legacy-дубликаты conversation_state для проверки выбора записи."""
    max_updated_at = datetime_module.datetime(
        2026,
        3,
        11,
        15,
        0,
        tzinfo=datetime_module.UTC,
    )
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            family_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO family (singleton_key) VALUES (true) RETURNING id"
                    )
                )
            ).scalar_one()
            await database_connection.execute(
                text(
                    "INSERT INTO family_member "
                    "(id, first_name, username, is_authorized, family_id) "
                    "VALUES (9201, 'Dup User', 'dup_user', true, :family_id)"
                ),
                {"family_id": family_id},
            )
            await database_connection.execute(
                text(
                    "ALTER TABLE conversation_state "
                    "DROP CONSTRAINT pk_conversation_state"
                )
            )
            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(user_id, last_response_id, turn_count, session_summary, "
                    "updated_at) "
                    "VALUES "
                    "(9201, 'older-response', 1, 'older summary', "
                    "'2026-03-10 10:00:00+00'), "
                    "(9201, '', 2, 'max without response', :max_updated_at), "
                    "(9201, 'chosen-response', 5, 'max with response', :max_updated_at)"
                ),
                {"max_updated_at": max_updated_at},
            )
            return {
                "telegram_user_id": 9201,
                "family_id": int(family_id),
                "updated_at": max_updated_at,
                "last_response_id": "chosen-response",
                "turn_count": 5,
                "session_summary": "max with response",
            }
    finally:
        await database_engine.dispose()


async def _insert_broken_legacy_conversation_state_for_upgrade(
    database_url: str,
) -> None:
    """Создаёт legacy conversation_state c user_id, отсутствующим в family_member."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            await database_connection.execute(
                text("INSERT INTO family (singleton_key) VALUES (true)")
            )
            await database_connection.execute(
                text(
                    "ALTER TABLE conversation_state DROP CONSTRAINT "
                    "fk_conversation_state_user_id_family_member"
                )
            )
            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(user_id, last_response_id, turn_count, session_summary) "
                    "VALUES (999991, 'broken-response', 2, 'broken summary')"
                )
            )
    finally:
        await database_engine.dispose()


async def _insert_legacy_conversation_state_without_workspace_mapping_for_upgrade(
    database_url: str,
) -> None:
    """Создаёт legacy conversation_state с family_id вне таблицы family."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            family_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO family (singleton_key) VALUES (true) RETURNING id"
                    )
                )
            ).scalar_one()
            await database_connection.execute(
                text(
                    "INSERT INTO family_member "
                    "(id, first_name, username, is_authorized, family_id) "
                    "VALUES (999992, 'Broken Workspace', 'broken_ws', true, :family_id)"
                ),
                {"family_id": family_id},
            )
            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(user_id, last_response_id, turn_count, session_summary) "
                    "VALUES (999992, 'broken-workspace', 3, 'broken workspace')"
                )
            )
            await database_connection.execute(
                text(
                    "ALTER TABLE family_member DROP CONSTRAINT "
                    "fk_family_member_family_id_family"
                )
            )
            await database_connection.execute(
                text("UPDATE family_member SET family_id = 123456789 WHERE id = 999992")
            )
    finally:
        await database_engine.dispose()


async def _read_workspace_conversation_state_rows(
    database_url: str,
    telegram_user_id: int | None,
) -> list[dict[str, object]]:
    """Возвращает workspace-строки conversation_state как список словарей."""
    query = (
        "SELECT id, telegram_user_id, workspace_id, last_response_id, "
        "turn_count, session_summary, updated_at "
        "FROM conversation_state"
    )
    params: dict[str, int] = {}
    if telegram_user_id is not None:
        query += " WHERE telegram_user_id = :telegram_user_id"
        params["telegram_user_id"] = telegram_user_id
    query += " ORDER BY id"

    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            result = await database_connection.execute(text(query), params)
            return [dict(row._mapping) for row in result]
    finally:
        await database_engine.dispose()


async def _read_legacy_conversation_state_rows(
    database_url: str,
    user_id: int | None,
) -> list[dict[str, object]]:
    """Возвращает legacy-строки conversation_state как список словарей."""
    query = (
        "SELECT user_id, last_response_id, turn_count, session_summary, updated_at "
        "FROM conversation_state"
    )
    params: dict[str, int] = {}
    if user_id is not None:
        query += " WHERE user_id = :user_id"
        params["user_id"] = user_id
    query += " ORDER BY user_id"

    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            result = await database_connection.execute(text(query), params)
            return [dict(row._mapping) for row in result]
    finally:
        await database_engine.dispose()


async def _read_workspace_chat_id_by_workspace_id(
    database_url: str,
    workspace_id: int,
) -> int:
    """Читает telegram_chat_id для workspace.id."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            result = await database_connection.execute(
                text("SELECT telegram_chat_id FROM workspace WHERE id = :workspace_id"),
                {"workspace_id": workspace_id},
            )
            return int(result.scalar_one())
    finally:
        await database_engine.dispose()


async def _insert_workspace_conversation_state_for_downgrade(
    database_url: str,
) -> dict[str, int | str | datetime_module.datetime]:
    """Создаёт одну workspace-строку conversation_state для downgrade-переноса."""
    updated_at_value = datetime_module.datetime(
        2026,
        3,
        12,
        8,
        45,
        tzinfo=datetime_module.UTC,
    )
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            workspace_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO workspace (telegram_chat_id, title, is_active) "
                        "VALUES (-100777888999, 'Downgrade Workspace', true) "
                        "RETURNING id"
                    )
                )
            ).scalar_one()
            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(telegram_user_id, workspace_id, last_response_id, "
                    "turn_count, session_summary, updated_at) "
                    "VALUES (9301, :workspace_id, 'workspace-response', "
                    "9, 'workspace summary', :updated_at)"
                ),
                {"workspace_id": workspace_id, "updated_at": updated_at_value},
            )
            return {
                "user_id": 9301,
                "last_response_id": "workspace-response",
                "turn_count": 9,
                "session_summary": "workspace summary",
                "updated_at": updated_at_value,
            }
    finally:
        await database_engine.dispose()


async def _insert_workspace_conversation_state_duplicates_for_downgrade(
    database_url: str,
) -> dict[str, int | str | datetime_module.datetime]:
    """Создаёт несколько workspace-строк одного пользователя для downgrade-policy."""
    max_updated_at = datetime_module.datetime(
        2026,
        3,
        12,
        12,
        0,
        tzinfo=datetime_module.UTC,
    )
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            first_workspace_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO workspace (telegram_chat_id, title, is_active) "
                        "VALUES (-100444111000, 'First WS', true) RETURNING id"
                    )
                )
            ).scalar_one()
            second_workspace_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO workspace (telegram_chat_id, title, is_active) "
                        "VALUES (-100444111001, 'Second WS', true) RETURNING id"
                    )
                )
            ).scalar_one()
            third_workspace_id = (
                await database_connection.execute(
                    text(
                        "INSERT INTO workspace (telegram_chat_id, title, is_active) "
                        "VALUES (-100444111002, 'Third WS', true) RETURNING id"
                    )
                )
            ).scalar_one()
            await database_connection.execute(
                text(
                    "INSERT INTO conversation_state "
                    "(telegram_user_id, workspace_id, last_response_id, "
                    "turn_count, session_summary, updated_at) VALUES "
                    "(9401, :first_workspace_id, 'older-choice', 3, 'older', "
                    "'2026-03-11 12:00:00+00'), "
                    "(9401, :second_workspace_id, 'same-time-lower-turns', 4, "
                    "'same time lower', :max_updated_at), "
                    "(9401, :third_workspace_id, 'chosen-downgrade-row', 8, "
                    "'same time higher', :max_updated_at)"
                ),
                {
                    "first_workspace_id": first_workspace_id,
                    "second_workspace_id": second_workspace_id,
                    "third_workspace_id": third_workspace_id,
                    "max_updated_at": max_updated_at,
                },
            )
            return {
                "user_id": 9401,
                "last_response_id": "chosen-downgrade-row",
                "turn_count": 8,
                "session_summary": "same time higher",
                "updated_at": max_updated_at,
            }
    finally:
        await database_engine.dispose()


async def _read_conversation_state_trigger_exists(database_url: str) -> bool:
    """Проверяет наличие пользовательского trigger у conversation_state."""
    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            result = await database_connection.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_trigger AS trigger_definition "
                    "JOIN pg_class AS table_definition "
                    "ON table_definition.oid = trigger_definition.tgrelid "
                    "WHERE table_definition.relname = 'conversation_state' "
                    "AND trigger_definition.tgname = "
                    "'trg_conversation_state_set_updated_at' "
                    "AND trigger_definition.tgisinternal = false"
                    ")"
                )
            )
            return bool(result.scalar_one())
    finally:
        await database_engine.dispose()


async def _read_null_values(
    database_url: str,
    table_name: str,
    column_name: str,
) -> int:
    """Возвращает число строк с NULL в таблице/колонке."""
    allowed_queries = {
        ("pet", "workspace_id"): text(
            "SELECT COUNT(*) FROM pet WHERE workspace_id IS NULL"
        ),
        ("pet", "family_id"): text("SELECT COUNT(*) FROM pet WHERE family_id IS NULL"),
    }
    query = allowed_queries.get((table_name, column_name))
    if query is None:
        raise ValueError(f"Unsupported NULL check for {table_name}.{column_name}")

    database_engine = create_async_engine(database_url)
    try:
        async with database_engine.begin() as database_connection:
            result = await database_connection.execute(query)
            return int(result.scalar_one())
    finally:
        await database_engine.dispose()


class TestWorkspacePhase2MigrationRuntime:
    """Runtime-валидация upgrade/downgrade для workspace миграции."""

    def test_upgrade_handles_non_empty_legacy_pet_table(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade должен мигрировать непустые legacy pet-записи без падения."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_legacy_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            _seed_legacy_rows_for_workspace_upgrade(target_database_url)

            command.upgrade(alembic_config, WORKSPACE_REVISION)
            assert _get_alembic_version(target_database_url) == WORKSPACE_REVISION
            assert _count_null_values(target_database_url, "pet", "workspace_id") == 0
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_enforces_non_nullable_runtime_contracts(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade обязан создавать non-null связи, ожидаемые runtime-слоем."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            assert _get_alembic_version(target_database_url) == WORKSPACE_REVISION
            assert _column_nullable(target_database_url, "pet", "workspace_id") is False
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_preserves_legacy_conversation_state_data(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade переносит legacy conversation_state в workspace без потерь."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_state_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            seed_payload = _seed_legacy_conversation_state_for_upgrade(
                target_database_url
            )

            command.upgrade(alembic_config, WORKSPACE_REVISION)
            assert _get_alembic_version(target_database_url) == WORKSPACE_REVISION

            rows = _workspace_conversation_state_rows(
                target_database_url,
                int(seed_payload["telegram_user_id"]),
            )
            assert len(rows) == 1
            migrated_row = rows[0]

            expected_chat_id = -LEGACY_WORKSPACE_CHAT_ID_OFFSET - int(
                seed_payload["family_id"]
            )
            workspace_chat_id = _workspace_chat_id_by_workspace_id(
                target_database_url,
                int(migrated_row["workspace_id"]),
            )
            assert workspace_chat_id == expected_chat_id
            assert migrated_row["telegram_user_id"] == seed_payload["telegram_user_id"]
            assert migrated_row["last_response_id"] == "legacy-response"
            assert migrated_row["turn_count"] == 4
            assert migrated_row["session_summary"] == "legacy summary"
            assert migrated_row["updated_at"] == seed_payload["updated_at"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_deduplicates_legacy_conversation_state_conflicts(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade оставляет детерминированно одну запись при legacy-дубликатах."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_state_dedup_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            seed_payload = _seed_legacy_conversation_state_duplicates_for_upgrade(
                target_database_url
            )

            command.upgrade(alembic_config, WORKSPACE_REVISION)
            assert _get_alembic_version(target_database_url) == WORKSPACE_REVISION

            rows = _workspace_conversation_state_rows(
                target_database_url,
                int(seed_payload["telegram_user_id"]),
            )
            assert len(rows) == 1
            migrated_row = rows[0]
            assert migrated_row["updated_at"] == seed_payload["updated_at"]
            assert migrated_row["last_response_id"] == seed_payload["last_response_id"]
            assert migrated_row["turn_count"] == seed_payload["turn_count"]
            assert migrated_row["session_summary"] == seed_payload["session_summary"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_fails_on_broken_legacy_conversation_state_links(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade должен падать с понятной ошибкой при разрыве legacy-связей."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_state_invalid_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            _seed_broken_legacy_conversation_state_for_upgrade(target_database_url)

            with pytest.raises(Exception, match="conversation_state.*family_member"):
                command.upgrade(alembic_config, WORKSPACE_REVISION)
        finally:
            _drop_database(admin_database_url, database_name)

    def test_downgrade_restores_conversation_state_rows_from_workspace_model(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Downgrade переносит workspace conversation_state обратно в legacy-формат."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_downgrade_state_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            seed_payload = _seed_workspace_conversation_state_for_downgrade(
                target_database_url
            )

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            assert _get_alembic_version(target_database_url) == PREVIOUS_REVISION
            rows = _legacy_conversation_state_rows(
                target_database_url,
                int(seed_payload["user_id"]),
            )
            assert len(rows) == 1
            restored_row = rows[0]
            assert restored_row["user_id"] == seed_payload["user_id"]
            assert restored_row["last_response_id"] == seed_payload["last_response_id"]
            assert restored_row["turn_count"] == seed_payload["turn_count"]
            assert restored_row["session_summary"] == seed_payload["session_summary"]
            assert restored_row["updated_at"] == seed_payload["updated_at"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_downgrade_deduplicates_workspace_conversation_state_by_policy(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Downgrade выбирает одну запись на user_id по updated_at и turn_count."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_downgrade_state_dedup_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            seed_payload = _seed_workspace_conversation_state_duplicates_for_downgrade(
                target_database_url
            )

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            assert _get_alembic_version(target_database_url) == PREVIOUS_REVISION
            rows = _legacy_conversation_state_rows(
                target_database_url,
                int(seed_payload["user_id"]),
            )
            assert len(rows) == 1
            restored_row = rows[0]
            assert restored_row["last_response_id"] == seed_payload["last_response_id"]
            assert restored_row["turn_count"] == seed_payload["turn_count"]
            assert restored_row["session_summary"] == seed_payload["session_summary"]
            assert restored_row["updated_at"] == seed_payload["updated_at"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_downgrade_restores_family_members_for_existing_activity(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Downgrade не должен падать на FK при наличии health/audit данных."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_downgrade_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            _seed_workspace_activity_rows(target_database_url)

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            assert _get_alembic_version(target_database_url) == PREVIOUS_REVISION
            assert _family_member_ids(target_database_url) == [
                9001,
                9002,
                9003,
                9004,
            ]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_downgrade_backfills_and_restores_non_nullable_family_links(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Downgrade должен вернуть non-null family_id и заполнить его в pet."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_downgrade_backfill_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            _seed_workspace_activity_rows(target_database_url)

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            assert _get_alembic_version(target_database_url) == PREVIOUS_REVISION
            assert _column_nullable(target_database_url, "pet", "family_id") is False
            assert _count_null_values(target_database_url, "pet", "family_id") == 0
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_migrates_conversation_state_data_and_preserves_updated_at(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade переносит legacy conversation_state в workspace-схему без потерь."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_state_data_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            seed = _seed_legacy_conversation_state_for_upgrade(target_database_url)

            command.upgrade(alembic_config, WORKSPACE_REVISION)
            rows = _workspace_conversation_state_rows(
                target_database_url,
                telegram_user_id=int(seed["telegram_user_id"]),
            )
            assert len(rows) == 1
            migrated_row = rows[0]
            assert migrated_row["telegram_user_id"] == seed["telegram_user_id"]
            assert migrated_row["last_response_id"] == "legacy-response"
            assert migrated_row["turn_count"] == 4
            assert migrated_row["session_summary"] == "legacy summary"
            assert migrated_row["updated_at"] == seed["updated_at"]

            migrated_workspace_chat_id = _workspace_chat_id_by_workspace_id(
                target_database_url,
                workspace_id=int(migrated_row["workspace_id"]),
            )
            assert migrated_workspace_chat_id == (
                -LEGACY_WORKSPACE_CHAT_ID_OFFSET - int(seed["family_id"])
            )
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_deduplicates_conversation_state_with_deterministic_policy(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade дедуплицирует конфликтующие legacy-строки по заданному правилу."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_state_dedup_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            seed = _seed_legacy_conversation_state_duplicates_for_upgrade(
                target_database_url
            )

            command.upgrade(alembic_config, WORKSPACE_REVISION)
            rows = _workspace_conversation_state_rows(
                target_database_url,
                telegram_user_id=int(seed["telegram_user_id"]),
            )
            assert len(rows) == 1
            deduplicated_row = rows[0]
            assert deduplicated_row["last_response_id"] == seed["last_response_id"]
            assert deduplicated_row["turn_count"] == seed["turn_count"]
            assert deduplicated_row["session_summary"] == seed["session_summary"]
            assert deduplicated_row["updated_at"] == seed["updated_at"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_fails_for_conversation_state_without_family_member(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade падает с понятной ошибкой при user_id без family_member."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_upgrade_state_missing_member_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            _seed_broken_legacy_conversation_state_for_upgrade(target_database_url)

            with pytest.raises(RuntimeError, match="Missing family_member"):
                command.upgrade(alembic_config, WORKSPACE_REVISION)
        finally:
            _drop_database(admin_database_url, database_name)

    def test_upgrade_fails_for_conversation_state_without_workspace_mapping(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade падает с понятной ошибкой при отсутствии workspace-mapping."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = (
            f"workspace_upgrade_state_missing_workspace_{uuid.uuid4().hex[:8]}"
        )
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, PREVIOUS_REVISION)
            _seed_legacy_conversation_state_without_workspace_mapping_for_upgrade(
                target_database_url
            )

            with pytest.raises(RuntimeError, match="Missing workspace mapping"):
                command.upgrade(alembic_config, WORKSPACE_REVISION)
        finally:
            _drop_database(admin_database_url, database_name)

    def test_downgrade_restores_conversation_state_data(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Downgrade возвращает legacy conversation_state и переносит данные назад."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_downgrade_state_data_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            seed = _seed_workspace_conversation_state_for_downgrade(target_database_url)

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            rows = _legacy_conversation_state_rows(
                target_database_url,
                user_id=int(seed["user_id"]),
            )
            assert len(rows) == 1
            restored_row = rows[0]
            assert restored_row["user_id"] == seed["user_id"]
            assert restored_row["last_response_id"] == seed["last_response_id"]
            assert restored_row["turn_count"] == seed["turn_count"]
            assert restored_row["session_summary"] == seed["session_summary"]
            assert restored_row["updated_at"] == seed["updated_at"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_downgrade_conversation_state_policy_for_multi_workspace_user(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Downgrade оставляет одну строку на user_id по детерминированному правилу."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_downgrade_state_policy_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            seed = _seed_workspace_conversation_state_duplicates_for_downgrade(
                target_database_url
            )

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            rows = _legacy_conversation_state_rows(
                target_database_url,
                user_id=int(seed["user_id"]),
            )
            assert len(rows) == 1
            kept_row = rows[0]
            assert kept_row["last_response_id"] == seed["last_response_id"]
            assert kept_row["turn_count"] == seed["turn_count"]
            assert kept_row["session_summary"] == seed["session_summary"]
            assert kept_row["updated_at"] == seed["updated_at"]
        finally:
            _drop_database(admin_database_url, database_name)

    def test_conversation_state_trigger_exists_after_upgrade_and_downgrade(
        self,
        postgres_container: PostgresContainer | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Проверяет, что триггер updated_at сохраняется после upgrade/downgrade."""
        if postgres_container is None:
            pytest.skip(
                "Runtime-тест миграций требует testcontainer URL и пропускается "
                "в режиме TEST_DATABASE_URL."
            )

        container_database_name = make_url(
            postgres_container.get_connection_url()
        ).database
        database_name = f"workspace_state_trigger_{uuid.uuid4().hex[:8]}"
        admin_database_url = _build_async_database_url(
            postgres_container,
            container_database_name,
        )
        target_database_url = _build_async_database_url(
            postgres_container,
            database_name,
        )
        alembic_config = _build_alembic_config(target_database_url)
        monkeypatch.setenv("DATABASE_URL", target_database_url)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        _create_database(admin_database_url, database_name)
        try:
            command.upgrade(alembic_config, WORKSPACE_REVISION)
            assert _conversation_state_trigger_exists(target_database_url) is True

            command.downgrade(alembic_config, PREVIOUS_REVISION)
            assert _conversation_state_trigger_exists(target_database_url) is True
        finally:
            _drop_database(admin_database_url, database_name)
