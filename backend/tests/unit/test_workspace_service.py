"""
Тесты сервиса workspace (workspace_service).

Покрывает мультитенантные операции:
- get_or_create_workspace: создание/реактивация workspace
- deactivate_workspace: деактивация при удалении бота из группы
- reactivate_workspace: реактивация при повторном добавлении бота
- get_workspace_by_chat_id: поиск по Telegram chat ID
- add_or_reactivate_member: добавление/реактивация участника
- deactivate_member: деактивация при выходе из группы
- get_user_workspaces: все активные workspace'ы пользователя
- get_member: поиск участника по паре (workspace_id, telegram_user_id)
- update_chat_id: атомарное обновление chat_id при миграции группы
- get_timezone / set_timezone: чтение и запись таймзоны

Интеграционные тесты с реальной PostgreSQL (testcontainers).
Каждый тест получает чистую транзакцию через фикстуру db_session.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from backend.app.db.models.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)
from backend.app.services import workspace_service as workspace_service_module
from backend.app.services.workspace_service import (
    add_or_reactivate_member,
    deactivate_member,
    deactivate_workspace,
    get_member,
    get_or_create_workspace,
    get_timezone,
    get_user_workspaces,
    get_workspace_by_chat_id,
    is_chat_member_active,
    reactivate_workspace,
    set_timezone,
    update_chat_id,
    verify_user_workspaces,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

LEGACY_WORKSPACE_CHAT_ID_OFFSET = 2_000_000_000_000

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные утилиты
# ═══════════════════════════════════════════════════════════════════════════════


async def _seed_workspace(
    session: AsyncSession,
    telegram_chat_id: int = -1001234567890,
    title: str = "Тестовая группа",
) -> Workspace:
    """Создаёт workspace через сервис для тестов, требующих готовых данных.

    Аргументы:
        session: активная AsyncSession
        telegram_chat_id: ID Telegram-группы
        title: название группы

    Возвращает:
        Workspace: созданный workspace
    """
    workspace, _is_new = await get_or_create_workspace(
        session,
        telegram_chat_id=telegram_chat_id,
        title=title,
    )
    return workspace


async def _seed_workspace_with_member(
    session: AsyncSession,
    telegram_chat_id: int = -1001234567890,
    title: str = "Тестовая группа",
    telegram_user_id: int = 100500,
    username: str | None = "testuser",
    first_name: str | None = "Тестовый",
) -> tuple[Workspace, WorkspaceMember]:
    """Создаёт workspace + участника для тестов.

    Возвращает:
        tuple: (Workspace, WorkspaceMember)
    """
    workspace = await _seed_workspace(
        session,
        telegram_chat_id=telegram_chat_id,
        title=title,
    )
    member = await add_or_reactivate_member(
        session,
        workspace_id=workspace.id,
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
    )
    return workspace, member


async def _create_workspace_in_isolated_session(
    session_factory: async_sessionmaker[AsyncSession],
    telegram_chat_id: int,
    title: str,
) -> int:
    """Запускает get_or_create_workspace в отдельной сессии и фиксирует транзакцию."""
    async with session_factory() as isolated_session:
        workspace, _is_new = await get_or_create_workspace(
            isolated_session,
            telegram_chat_id=telegram_chat_id,
            title=title,
        )
        await isolated_session.commit()
        return workspace.id


async def _add_member_in_isolated_session(
    session_factory: async_sessionmaker[AsyncSession],
    workspace_id: int,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> int:
    """Добавляет участника в отдельной сессии и фиксирует транзакцию."""
    async with session_factory() as isolated_session:
        member = await add_or_reactivate_member(
            isolated_session,
            workspace_id=workspace_id,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )
        await isolated_session.commit()
        return member.id


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты get_or_create_workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetOrCreateWorkspace:
    """Тесты get_or_create_workspace — создание/реактивация workspace."""

    async def test_creates_new_workspace(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Создаёт новый workspace, если не существует."""
        workspace, is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Моя группа",
        )

        assert workspace is not None
        assert workspace.id is not None
        assert workspace.telegram_chat_id == -1001234567890
        assert workspace.title == "Моя группа"
        assert is_new is True

    async def test_creates_settings_automatically(
        self,
        db_session: AsyncSession,
    ) -> None:
        """При создании workspace автоматически создаёт WorkspaceSettings."""
        workspace, _is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Группа с настройками",
        )

        result = await db_session.execute(
            select(WorkspaceSettings).where(
                WorkspaceSettings.workspace_id == workspace.id,
            ),
        )
        settings = result.scalar_one_or_none()

        assert settings is not None
        assert settings.timezone == "Europe/Moscow"
        assert settings.locale == "ru"

    async def test_returns_existing_active_workspace(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если workspace уже существует и активен — возвращает как есть."""
        first, first_is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Первый",
        )
        second, second_is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Второй",
        )

        assert first.id == second.id
        assert first_is_new is True
        assert second_is_new is False

    async def test_reactivates_inactive_workspace(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если workspace неактивен — реактивирует и обновляет title."""
        workspace, _is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Старое название",
        )
        await deactivate_workspace(db_session, telegram_chat_id=-1001234567890)

        reactivated, reactivated_is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Новое название",
        )

        assert reactivated.id == workspace.id
        assert reactivated.is_active is True
        assert reactivated.title == "Новое название"
        assert reactivated_is_new is False

    async def test_does_not_create_duplicate(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Повторный вызов не создаёт дубликат в БД."""
        _workspace_1, _is_new_1 = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Группа",
        )
        _workspace_2, _is_new_2 = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567890,
            title="Группа",
        )

        result = await db_session.execute(select(Workspace))
        all_workspaces = result.scalars().all()

        assert len(all_workspaces) == 1

    async def test_is_idempotent_under_concurrent_creation(
        self,
        async_engine: AsyncEngine,
        tables: None,
    ) -> None:
        """Параллельные вызовы не создают дубль и не падают на unique violation."""
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        telegram_chat_id = -1001231231231

        workspace_ids = await asyncio.gather(
            _create_workspace_in_isolated_session(
                session_factory,
                telegram_chat_id=telegram_chat_id,
                title="Race A",
            ),
            _create_workspace_in_isolated_session(
                session_factory,
                telegram_chat_id=telegram_chat_id,
                title="Race B",
            ),
        )

        assert workspace_ids[0] == workspace_ids[1]
        async with session_factory() as verification_session:
            persisted_workspaces = (
                (
                    await verification_session.execute(
                        select(Workspace).where(
                            Workspace.telegram_chat_id == telegram_chat_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(persisted_workspaces) == 1

    async def test_adopts_single_legacy_workspace_for_first_real_group(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Первый реальный chat_id переназначает единственный legacy workspace."""
        await db_session.execute(delete(Workspace))
        await db_session.flush()

        legacy_workspace = Workspace(
            telegram_chat_id=-LEGACY_WORKSPACE_CHAT_ID_OFFSET - 1,
            title="Migrated family 1",
            is_active=True,
        )
        db_session.add(legacy_workspace)
        await db_session.flush()
        db_session.add(
            WorkspaceSettings(
                workspace_id=legacy_workspace.id,
                timezone="Europe/Moscow",
                locale="ru",
            )
        )
        await db_session.flush()

        adopted_workspace, is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567001,
            title="Реальная группа",
        )

        assert adopted_workspace.id == legacy_workspace.id
        assert adopted_workspace.telegram_chat_id == -1001234567001
        assert adopted_workspace.title == "Реальная группа"
        assert is_new is False  # legacy adoption — не новый workspace

    async def test_does_not_adopt_legacy_workspace_when_real_workspace_exists(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Legacy workspace не переназначается, если уже есть реальный workspace."""
        await db_session.execute(delete(Workspace))
        await db_session.flush()

        legacy_workspace = Workspace(
            telegram_chat_id=-LEGACY_WORKSPACE_CHAT_ID_OFFSET - 2,
            title="Migrated family 2",
            is_active=True,
        )
        real_workspace = Workspace(
            telegram_chat_id=-1001230000001,
            title="Уже реальная группа",
            is_active=True,
        )
        db_session.add_all([legacy_workspace, real_workspace])
        await db_session.flush()
        db_session.add_all(
            [
                WorkspaceSettings(
                    workspace_id=legacy_workspace.id,
                    timezone="Europe/Moscow",
                    locale="ru",
                ),
                WorkspaceSettings(
                    workspace_id=real_workspace.id,
                    timezone="Europe/Moscow",
                    locale="ru",
                ),
            ]
        )
        await db_session.flush()

        created_workspace, is_new = await get_or_create_workspace(
            db_session,
            telegram_chat_id=-1001234567002,
            title="Новая группа",
        )

        assert created_workspace.id not in {legacy_workspace.id, real_workspace.id}
        assert created_workspace.telegram_chat_id == -1001234567002
        assert legacy_workspace.telegram_chat_id == -LEGACY_WORKSPACE_CHAT_ID_OFFSET - 2
        assert is_new is True  # новый workspace, не adoption


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты deactivate_workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeactivateWorkspace:
    """Тесты deactivate_workspace — деактивация workspace."""

    async def test_sets_is_active_false(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Устанавливает is_active=False у workspace."""
        workspace = await _seed_workspace(db_session)

        await deactivate_workspace(
            db_session,
            telegram_chat_id=workspace.telegram_chat_id,
        )

        result = await db_session.execute(
            select(Workspace).where(Workspace.id == workspace.id),
        )
        loaded = result.scalar_one()

        assert loaded.is_active is False

    async def test_does_nothing_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если workspace не найден — не бросает ошибку."""
        # Не должно вызвать исключение
        await deactivate_workspace(
            db_session,
            telegram_chat_id=-9999999999999,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты reactivate_workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestReactivateWorkspace:
    """Тесты reactivate_workspace — реактивация workspace."""

    async def test_sets_is_active_true(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Устанавливает is_active=True и обновляет title."""
        workspace = await _seed_workspace(db_session)
        await deactivate_workspace(
            db_session,
            telegram_chat_id=workspace.telegram_chat_id,
        )

        reactivated = await reactivate_workspace(
            db_session,
            telegram_chat_id=workspace.telegram_chat_id,
            title="Обновлённое название",
        )

        assert reactivated.is_active is True
        assert reactivated.title == "Обновлённое название"

    async def test_raises_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если workspace не найден — ValueError."""
        with pytest.raises(ValueError, match="не найден"):
            await reactivate_workspace(
                db_session,
                telegram_chat_id=-9999999999999,
                title="Несуществующий",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты get_workspace_by_chat_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetWorkspaceByChatId:
    """Тесты get_workspace_by_chat_id — поиск по Telegram chat ID."""

    async def test_returns_existing_workspace(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает workspace, если он существует."""
        workspace = await _seed_workspace(db_session)

        found = await get_workspace_by_chat_id(
            db_session,
            telegram_chat_id=workspace.telegram_chat_id,
        )

        assert found is not None
        assert found.id == workspace.id

    async def test_returns_none_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает None, если workspace не найден."""
        found = await get_workspace_by_chat_id(
            db_session,
            telegram_chat_id=-9999999999999,
        )

        assert found is None


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты add_or_reactivate_member
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddOrReactivateMember:
    """Тесты add_or_reactivate_member — добавление/реактивация участника."""

    async def test_creates_new_member(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Создаёт нового участника, если не существует."""
        workspace = await _seed_workspace(db_session)

        member = await add_or_reactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=111222333,
            username="alice",
            first_name="Алиса",
        )

        assert member is not None
        assert member.telegram_user_id == 111222333
        assert member.telegram_username == "alice"
        assert member.telegram_first_name == "Алиса"
        assert member.is_active is True

    async def test_reactivates_inactive_member(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Реактивирует неактивного участника (is_active=True, left_at=None)."""
        workspace, member = await _seed_workspace_with_member(db_session)

        await deactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=member.telegram_user_id,
        )

        reactivated = await add_or_reactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=member.telegram_user_id,
            username="updated_user",
            first_name="Обновлённое имя",
        )

        assert reactivated.is_active is True
        assert reactivated.left_at is None
        assert reactivated.telegram_username == "updated_user"
        assert reactivated.telegram_first_name == "Обновлённое имя"

    async def test_returns_existing_active_member(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если участник активен — возвращает как есть, обновляя username/first_name."""
        workspace, member = await _seed_workspace_with_member(
            db_session,
            username="old_name",
            first_name="Старое",
        )

        same_member = await add_or_reactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=member.telegram_user_id,
            username="new_name",
            first_name="Новое",
        )

        assert same_member.id == member.id
        assert same_member.telegram_username == "new_name"
        assert same_member.telegram_first_name == "Новое"

    async def test_member_without_username(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Участник может быть создан без username (nullable)."""
        workspace = await _seed_workspace(db_session)

        member = await add_or_reactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=444555666,
            username=None,
            first_name=None,
        )

        assert member.telegram_username is None
        assert member.telegram_first_name is None

    async def test_is_idempotent_under_concurrent_member_creation_race(
        self,
        async_engine: AsyncEngine,
        tables: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Конкурентное добавление одного user_id должно быть идемпотентным."""
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        workspace_id = await _create_workspace_in_isolated_session(
            session_factory,
            telegram_chat_id=-1009876543210,
            title="Member race",
        )
        first_lookup_barrier = asyncio.Event()
        first_lookup_counter = 0
        first_lookup_lock = asyncio.Lock()
        original_find_member = workspace_service_module._find_member

        async def _synchronized_find_member(
            session: AsyncSession,
            current_workspace_id: int,
            current_telegram_user_id: int,
        ) -> WorkspaceMember | None:
            """Синхронизирует первые два SELECT, чтобы стабильно воспроизвести race."""
            nonlocal first_lookup_counter
            async with first_lookup_lock:
                first_lookup_counter += 1
                current_lookup_number = first_lookup_counter
                if first_lookup_counter == 2:
                    first_lookup_barrier.set()

            if current_lookup_number <= 2:
                await first_lookup_barrier.wait()
                return None

            return await original_find_member(
                session,
                current_workspace_id,
                current_telegram_user_id,
            )

        monkeypatch.setattr(
            workspace_service_module,
            "_find_member",
            _synchronized_find_member,
        )

        created_member_ids = await asyncio.gather(
            _add_member_in_isolated_session(
                session_factory,
                workspace_id=workspace_id,
                telegram_user_id=700700700,
                username="race_a",
                first_name="Race A",
            ),
            _add_member_in_isolated_session(
                session_factory,
                workspace_id=workspace_id,
                telegram_user_id=700700700,
                username="race_b",
                first_name="Race B",
            ),
        )

        assert created_member_ids[0] == created_member_ids[1]
        async with session_factory() as verification_session:
            persisted_members = (
                (
                    await verification_session.execute(
                        select(WorkspaceMember).where(
                            WorkspaceMember.workspace_id == workspace_id,
                            WorkspaceMember.telegram_user_id == 700700700,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(persisted_members) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты deactivate_member
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeactivateMember:
    """Тесты deactivate_member — деактивация участника."""

    async def test_sets_inactive_and_left_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Устанавливает is_active=False и left_at=now()."""
        workspace, member = await _seed_workspace_with_member(db_session)

        await deactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=member.telegram_user_id,
        )

        result = await db_session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.id == member.id,
            ),
        )
        loaded = result.scalar_one()

        assert loaded.is_active is False
        assert loaded.left_at is not None

    async def test_does_nothing_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если участник не найден — не бросает ошибку."""
        workspace = await _seed_workspace(db_session)

        # Не должно вызвать исключение
        await deactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=999999999,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты get_user_workspaces
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetUserWorkspaces:
    """Тесты get_user_workspaces — все активные workspace'ы пользователя."""

    async def test_returns_active_workspaces(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает workspace'ы, где пользователь — активный участник."""
        workspace_a, _ = await _seed_workspace_with_member(
            db_session,
            telegram_chat_id=-1001111111111,
            telegram_user_id=100500,
        )
        workspace_b, _ = await _seed_workspace_with_member(
            db_session,
            telegram_chat_id=-1002222222222,
            telegram_user_id=100500,
        )

        workspaces = await get_user_workspaces(
            db_session,
            telegram_user_id=100500,
        )

        workspace_ids = {ws.id for ws in workspaces}
        assert workspace_a.id in workspace_ids
        assert workspace_b.id in workspace_ids

    async def test_excludes_inactive_workspaces(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Не возвращает неактивные workspace'ы."""
        await _seed_workspace_with_member(
            db_session,
            telegram_chat_id=-1001111111111,
            telegram_user_id=100500,
        )
        await deactivate_workspace(
            db_session,
            telegram_chat_id=-1001111111111,
        )

        workspaces = await get_user_workspaces(
            db_session,
            telegram_user_id=100500,
        )

        assert len(workspaces) == 0

    async def test_excludes_inactive_members(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Не возвращает workspace, если пользователь — неактивный участник."""
        workspace, _member = await _seed_workspace_with_member(
            db_session,
            telegram_chat_id=-1003333333333,
            telegram_user_id=100500,
        )
        await deactivate_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=100500,
        )

        workspaces = await get_user_workspaces(
            db_session,
            telegram_user_id=100500,
        )

        assert len(workspaces) == 0

    async def test_returns_empty_list_if_no_workspaces(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает пустой список, если пользователь нигде не состоит."""
        workspaces = await get_user_workspaces(
            db_session,
            telegram_user_id=999999999,
        )

        assert workspaces == []


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты get_member
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetMember:
    """Тесты get_member — поиск участника по паре (workspace_id, telegram_user_id)."""

    async def test_returns_existing_member(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает участника, если он существует."""
        workspace, member = await _seed_workspace_with_member(db_session)

        found = await get_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=member.telegram_user_id,
        )

        assert found is not None
        assert found.id == member.id

    async def test_returns_none_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает None, если участник не найден."""
        workspace = await _seed_workspace(db_session)

        found = await get_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=999999999,
        )

        assert found is None


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты update_chat_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpdateChatId:
    """Тесты update_chat_id — обновление telegram_chat_id при миграции группы."""

    async def test_updates_chat_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Атомарно обновляет telegram_chat_id."""
        workspace = await _seed_workspace(
            db_session,
            telegram_chat_id=-1001111111111,
        )

        await update_chat_id(
            db_session,
            old_chat_id=-1001111111111,
            new_chat_id=-1009999999999,
        )

        result = await db_session.execute(
            select(Workspace).where(Workspace.id == workspace.id),
        )
        loaded = result.scalar_one()

        assert loaded.telegram_chat_id == -1009999999999

    async def test_raises_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если workspace не найден — ValueError."""
        with pytest.raises(ValueError, match="не найден"):
            await update_chat_id(
                db_session,
                old_chat_id=-9999999999999,
                new_chat_id=-8888888888888,
            )

    async def test_replay_is_idempotent_noop(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Повторная миграция (old_chat_id уже обновлён) — безопасный no-op."""
        workspace = await _seed_workspace(
            db_session,
            telegram_chat_id=-1001111111111,
        )
        original_workspace_id = workspace.id

        # Первая миграция — успешно
        await update_chat_id(
            db_session,
            old_chat_id=-1001111111111,
            new_chat_id=-1009999999999,
        )

        # Повторная миграция (replay) — не должна бросать ошибку
        await update_chat_id(
            db_session,
            old_chat_id=-1001111111111,
            new_chat_id=-1009999999999,
        )

        # Workspace не изменился
        result = await db_session.execute(
            select(Workspace).where(Workspace.id == original_workspace_id),
        )
        loaded = result.scalar_one()
        assert loaded.telegram_chat_id == -1009999999999


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты get_timezone / set_timezone
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetTimezone:
    """Тесты get_timezone — получение таймзоны workspace."""

    async def test_returns_default_europe_moscow(
        self,
        db_session: AsyncSession,
    ) -> None:
        """По умолчанию возвращает 'Europe/Moscow'."""
        workspace = await _seed_workspace(db_session)

        timezone_value = await get_timezone(
            db_session,
            workspace_id=workspace.id,
        )

        assert timezone_value == "Europe/Moscow"

    async def test_raises_if_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если workspace/settings не найден — ValueError."""
        with pytest.raises(ValueError, match="не найден"):
            await get_timezone(db_session, workspace_id=999999)


class TestSetTimezone:
    """Тесты set_timezone — установка IANA-таймзоны."""

    async def test_sets_valid_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Устанавливает валидную IANA-таймзону."""
        workspace = await _seed_workspace(db_session)

        await set_timezone(
            db_session,
            workspace_id=workspace.id,
            timezone_str="Asia/Tokyo",
        )

        timezone_value = await get_timezone(
            db_session,
            workspace_id=workspace.id,
        )
        assert timezone_value == "Asia/Tokyo"

    async def test_rejects_invalid_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Невалидная таймзона вызывает ValueError."""
        workspace = await _seed_workspace(db_session)

        with pytest.raises(ValueError, match=r"таймзон|timezone"):
            await set_timezone(
                db_session,
                workspace_id=workspace.id,
                timezone_str="Mars/Olympus",
            )

    async def test_updates_existing_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Повторный вызов перезаписывает таймзону."""
        workspace = await _seed_workspace(db_session)

        await set_timezone(
            db_session,
            workspace_id=workspace.id,
            timezone_str="Europe/London",
        )
        await set_timezone(
            db_session,
            workspace_id=workspace.id,
            timezone_str="America/New_York",
        )

        timezone_value = await get_timezone(
            db_session,
            workspace_id=workspace.id,
        )
        assert timezone_value == "America/New_York"

    async def test_rejects_empty_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Пустая строка таймзоны вызывает ValueError."""
        workspace = await _seed_workspace(db_session)

        with pytest.raises((ValueError, KeyError)):
            await set_timezone(
                db_session,
                workspace_id=workspace.id,
                timezone_str="",
            )


class TestIsChatMemberActive:
    """Тесты is_chat_member_active — трактовка статусов Telegram."""

    def test_returns_true_for_member_status(self) -> None:
        """Статус member считается активным."""
        assert is_chat_member_active(SimpleNamespace(status="member")) is True

    def test_returns_false_for_restricted_without_membership(self) -> None:
        """restricted + is_member=False считается неактивным."""
        chat_member = SimpleNamespace(status="restricted", is_member=False)
        assert is_chat_member_active(chat_member) is False


class TestVerifyUserWorkspaces:
    """Тесты lazy verification workspace'ов через Telegram API."""

    @staticmethod
    def _make_workspace(workspace_id: int, chat_id: int, title: str) -> Workspace:
        """Создаёт in-memory Workspace для unit-тестов верификации."""
        workspace = Workspace(telegram_chat_id=chat_id, title=title, is_active=True)
        workspace.id = workspace_id
        return workspace

    async def test_keeps_workspace_for_active_member(self) -> None:
        """status=member оставляет workspace в выдаче."""
        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(1, -100111, "A")
        bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(status="member"))

        verified = await verify_user_workspaces(bot, session, 42, [workspace])

        assert verified == [workspace]

    async def test_deactivates_member_when_user_left(self) -> None:
        """status=left деактивирует WorkspaceMember и убирает workspace."""
        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(2, -100222, "B")
        bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(status="left"))

        with patch.object(
            workspace_service_module, "deactivate_member", new=AsyncMock()
        ) as deactivate_member_mock:
            verified = await verify_user_workspaces(bot, session, 77, [workspace])

        assert verified == []
        deactivate_member_mock.assert_awaited_once_with(session, 2, 77)

    async def test_deactivates_member_when_user_kicked(self) -> None:
        """status=kicked деактивирует WorkspaceMember."""
        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(3, -100333, "C")
        bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(status="kicked"))

        with patch.object(
            workspace_service_module, "deactivate_member", new=AsyncMock()
        ) as deactivate_member_mock:
            verified = await verify_user_workspaces(bot, session, 88, [workspace])

        assert verified == []
        deactivate_member_mock.assert_awaited_once_with(session, 3, 88)

    async def test_deactivates_member_for_restricted_non_member(self) -> None:
        """restricted + is_member=False деактивирует WorkspaceMember."""
        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(4, -100444, "D")
        restricted = SimpleNamespace(status="restricted", is_member=False)
        bot.get_chat_member = AsyncMock(return_value=restricted)

        with patch.object(
            workspace_service_module, "deactivate_member", new=AsyncMock()
        ) as deactivate_member_mock:
            verified = await verify_user_workspaces(bot, session, 99, [workspace])

        assert verified == []
        deactivate_member_mock.assert_awaited_once_with(session, 4, 99)

    async def test_deactivates_workspace_on_bad_request(self) -> None:
        """TelegramBadRequest деактивирует workspace и убирает его из выдачи."""

        class FakeBadRequestError(Exception):
            """Локальный дубль TelegramBadRequest для unit-теста."""

        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(5, -100555, "E")
        bot.get_chat_member = AsyncMock(side_effect=FakeBadRequestError("bad request"))

        with (
            patch.object(
                workspace_service_module,
                "TelegramBadRequest",
                FakeBadRequestError,
            ),
            patch.object(
                workspace_service_module, "deactivate_workspace", new=AsyncMock()
            ) as deactivate_workspace_mock,
        ):
            verified = await verify_user_workspaces(bot, session, 10, [workspace])

        assert verified == []
        deactivate_workspace_mock.assert_awaited_once_with(session, -100555)

    async def test_deactivates_workspace_on_forbidden(self) -> None:
        """TelegramForbiddenError деактивирует workspace и убирает его."""

        class FakeForbiddenError(Exception):
            """Локальный дубль TelegramForbiddenError для unit-теста."""

        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(6, -100666, "F")
        bot.get_chat_member = AsyncMock(side_effect=FakeForbiddenError("forbidden"))

        with (
            patch.object(
                workspace_service_module,
                "TelegramForbiddenError",
                FakeForbiddenError,
            ),
            patch.object(
                workspace_service_module, "deactivate_workspace", new=AsyncMock()
            ) as deactivate_workspace_mock,
        ):
            verified = await verify_user_workspaces(bot, session, 11, [workspace])

        assert verified == []
        deactivate_workspace_mock.assert_awaited_once_with(session, -100666)

    async def test_keeps_workspace_on_network_error(self) -> None:
        """Любая иная ошибка сохраняет workspace (graceful degradation)."""
        session = AsyncMock()
        bot = AsyncMock()
        workspace = self._make_workspace(7, -100777, "G")
        bot.get_chat_member = AsyncMock(side_effect=RuntimeError("network"))

        verified = await verify_user_workspaces(bot, session, 12, [workspace])

        assert verified == [workspace]

    async def test_returns_empty_without_api_calls(self) -> None:
        """Пустой список workspace не вызывает Telegram API."""
        session = AsyncMock()
        bot = AsyncMock()
        bot.get_chat_member = AsyncMock()

        verified = await verify_user_workspaces(bot, session, 13, [])

        assert verified == []
        bot.get_chat_member.assert_not_awaited()

    async def test_mixed_workspaces_returns_only_valid(self) -> None:
        """Микс валидного и устаревшего workspace возвращает только валидный."""
        session = AsyncMock()
        bot = AsyncMock()
        valid_workspace = self._make_workspace(8, -100888, "H")
        stale_workspace = self._make_workspace(9, -100999, "I")
        bot.get_chat_member = AsyncMock(
            side_effect=[
                SimpleNamespace(status="member"),
                SimpleNamespace(status="left"),
            ]
        )

        with patch.object(
            workspace_service_module, "deactivate_member", new=AsyncMock()
        ) as deactivate_member_mock:
            verified = await verify_user_workspaces(
                bot, session, 14, [valid_workspace, stale_workspace]
            )

        assert verified == [valid_workspace]
        deactivate_member_mock.assert_awaited_once_with(session, 9, 14)
