"""
Тесты ORM-моделей мультитенантного workspace.

Покрывает новые модели, заменяющие singleton Family:
- Workspace (привязка к Telegram-группе через telegram_chat_id)
- WorkspaceMember (участник workspace с soft-delete)
- WorkspaceSettings (таймзона, локаль)

Для каждой модели проверяется:
1. Создание с обязательными полями
2. Значения по умолчанию (is_active, timezone, locale)
3. Сохранение и чтение из БД
4. Связи (relationships)
5. Unique constraints (telegram_chat_id, workspace_id+telegram_user_id)
6. Nullable поля
"""

import pytest
from backend.app.db.models.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные фабрики для создания тестовых экземпляров
# ═══════════════════════════════════════════════════════════════════════════════


def _make_workspace(
    telegram_chat_id: int = -1001234567890,
    title: str = "Тестовая группа",
) -> Workspace:
    """Создаёт экземпляр Workspace для тестов.

    Аргументы:
        telegram_chat_id: ID Telegram-группы (отрицательное число)
        title: название группы
    """
    return Workspace(
        telegram_chat_id=telegram_chat_id,
        title=title,
    )


async def _persist_workspace(
    session: AsyncSession,
    telegram_chat_id: int = -1001234567890,
    title: str = "Тестовая группа",
) -> Workspace:
    """Сохраняет Workspace в БД и возвращает его.

    Аргументы:
        session: активная AsyncSession
        telegram_chat_id: ID Telegram-группы
        title: название группы

    Возвращает:
        Workspace: сохранённый экземпляр с заполненным id
    """
    workspace = _make_workspace(
        telegram_chat_id=telegram_chat_id,
        title=title,
    )
    session.add(workspace)
    await session.flush()
    return workspace


def _make_member(
    workspace_id: int | None = None,
    telegram_user_id: int = 100500,
    telegram_username: str | None = "testuser",
    telegram_first_name: str | None = "Алиса",
) -> WorkspaceMember:
    """Создаёт экземпляр WorkspaceMember для тестов.

    Аргументы:
        workspace_id: FK на Workspace
        telegram_user_id: Telegram user ID
        telegram_username: Telegram username (nullable)
        telegram_first_name: имя в Telegram (nullable)
    """
    member = WorkspaceMember(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        telegram_first_name=telegram_first_name,
    )
    if workspace_id is not None:
        member.workspace_id = workspace_id
    return member


async def _persist_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int = 100500,
    telegram_username: str | None = "testuser",
    telegram_first_name: str | None = "Алиса",
) -> WorkspaceMember:
    """Сохраняет WorkspaceMember в БД.

    Аргументы:
        session: активная AsyncSession
        workspace_id: ID workspace (FK)
        telegram_user_id: Telegram user ID
        telegram_username: Telegram username
        telegram_first_name: имя в Telegram
    """
    member = _make_member(
        workspace_id=workspace_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        telegram_first_name=telegram_first_name,
    )
    session.add(member)
    await session.flush()
    return member


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели Workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkspaceModel:
    """Тесты модели Workspace (мультитенантная замена Family)."""

    def test_create_with_required_fields(self) -> None:
        """Workspace создаётся с telegram_chat_id и title."""
        workspace = _make_workspace()

        assert workspace.telegram_chat_id == -1001234567890
        assert workspace.title == "Тестовая группа"

    def test_is_active_defaults_to_true(self) -> None:
        """is_active по умолчанию True."""
        workspace = _make_workspace()
        assert workspace.is_active is True

    async def test_persists_and_gets_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Workspace сохраняется в БД и получает автоинкрементный id."""
        workspace = await _persist_workspace(db_session)

        assert workspace.id is not None
        assert isinstance(workspace.id, int)

    async def test_has_created_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Workspace получает created_at при сохранении."""
        workspace = await _persist_workspace(db_session)
        assert workspace.created_at is not None

    async def test_read_back_from_database(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Workspace читается обратно из БД с корректными данными."""
        workspace = await _persist_workspace(db_session)
        workspace_id = workspace.id

        result = await db_session.execute(
            select(Workspace).where(Workspace.id == workspace_id),
        )
        loaded = result.scalar_one()

        assert loaded.telegram_chat_id == -1001234567890
        assert loaded.title == "Тестовая группа"

    async def test_telegram_chat_id_unique_constraint(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Два workspace с одинаковым telegram_chat_id вызывают IntegrityError."""
        await _persist_workspace(db_session, telegram_chat_id=-1001111111111)

        with pytest.raises(IntegrityError):
            await _persist_workspace(
                db_session,
                telegram_chat_id=-1001111111111,
            )

    async def test_has_members_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Workspace имеет связь members с WorkspaceMember."""
        workspace = await _persist_workspace(db_session)
        await _persist_member(db_session, workspace_id=workspace.id)

        await db_session.refresh(workspace, attribute_names=["members"])
        assert len(workspace.members) == 1

    async def test_has_settings_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Workspace имеет связь settings с WorkspaceSettings (one-to-one)."""
        workspace = await _persist_workspace(db_session)

        settings = WorkspaceSettings(workspace_id=workspace.id)
        db_session.add(settings)
        await db_session.flush()

        await db_session.refresh(workspace, attribute_names=["settings"])
        assert workspace.settings is not None
        assert workspace.settings.workspace_id == workspace.id


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели WorkspaceMember
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkspaceMemberModel:
    """Тесты модели WorkspaceMember (участник workspace)."""

    def test_create_with_required_fields(self) -> None:
        """WorkspaceMember создаётся с telegram_user_id."""
        member = _make_member(telegram_user_id=12345)
        assert member.telegram_user_id == 12345

    def test_is_active_defaults_to_true(self) -> None:
        """is_active по умолчанию True."""
        member = _make_member()
        assert member.is_active is True

    def test_username_is_nullable(self) -> None:
        """telegram_username может быть None."""
        member = _make_member(telegram_username=None)
        assert member.telegram_username is None

    def test_first_name_is_nullable(self) -> None:
        """telegram_first_name может быть None."""
        member = _make_member(telegram_first_name=None)
        assert member.telegram_first_name is None

    def test_left_at_defaults_to_none(self) -> None:
        """left_at по умолчанию None (участник активен)."""
        member = _make_member()
        assert member.left_at is None

    async def test_persists_and_gets_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """WorkspaceMember сохраняется в БД с автоинкрементным id."""
        workspace = await _persist_workspace(db_session)
        member = await _persist_member(
            db_session,
            workspace_id=workspace.id,
        )

        assert member.id is not None
        assert isinstance(member.id, int)

    async def test_has_joined_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """WorkspaceMember получает joined_at при сохранении."""
        workspace = await _persist_workspace(db_session)
        member = await _persist_member(
            db_session,
            workspace_id=workspace.id,
        )

        assert member.joined_at is not None

    async def test_read_back_from_database(
        self,
        db_session: AsyncSession,
    ) -> None:
        """WorkspaceMember читается обратно из БД."""
        workspace = await _persist_workspace(db_session)
        member = await _persist_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=999888,
            telegram_username="boris",
            telegram_first_name="Борис",
        )

        result = await db_session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.id == member.id,
            ),
        )
        loaded = result.scalar_one()

        assert loaded.telegram_user_id == 999888
        assert loaded.telegram_username == "boris"
        assert loaded.telegram_first_name == "Борис"

    async def test_unique_workspace_user_constraint(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Дубликат (workspace_id, telegram_user_id) вызывает IntegrityError."""
        workspace = await _persist_workspace(db_session)

        await _persist_member(
            db_session,
            workspace_id=workspace.id,
            telegram_user_id=111222,
        )

        with pytest.raises(IntegrityError):
            await _persist_member(
                db_session,
                workspace_id=workspace.id,
                telegram_user_id=111222,
            )

    async def test_same_user_in_different_workspaces(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Один пользователь может быть в разных workspace'ах."""
        workspace_a = await _persist_workspace(
            db_session,
            telegram_chat_id=-1001111111111,
        )
        workspace_b = await _persist_workspace(
            db_session,
            telegram_chat_id=-1002222222222,
        )

        member_a = await _persist_member(
            db_session,
            workspace_id=workspace_a.id,
            telegram_user_id=555666,
        )
        member_b = await _persist_member(
            db_session,
            workspace_id=workspace_b.id,
            telegram_user_id=555666,
        )

        assert member_a.id != member_b.id


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели WorkspaceSettings
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkspaceSettingsModel:
    """Тесты модели WorkspaceSettings (таймзона и локаль workspace)."""

    async def test_timezone_defaults_to_europe_moscow(
        self,
        db_session: AsyncSession,
    ) -> None:
        """timezone по умолчанию 'Europe/Moscow'."""
        workspace = await _persist_workspace(db_session)

        settings = WorkspaceSettings(workspace_id=workspace.id)
        db_session.add(settings)
        await db_session.flush()

        assert settings.timezone == "Europe/Moscow"

    async def test_locale_defaults_to_ru(
        self,
        db_session: AsyncSession,
    ) -> None:
        """locale по умолчанию 'ru'."""
        workspace = await _persist_workspace(db_session)

        settings = WorkspaceSettings(workspace_id=workspace.id)
        db_session.add(settings)
        await db_session.flush()

        assert settings.locale == "ru"

    async def test_persists_and_reads_back(
        self,
        db_session: AsyncSession,
    ) -> None:
        """WorkspaceSettings сохраняется и читается из БД."""
        workspace = await _persist_workspace(db_session)

        settings = WorkspaceSettings(
            workspace_id=workspace.id,
            timezone="Asia/Tokyo",
            locale="ja",
        )
        db_session.add(settings)
        await db_session.flush()

        result = await db_session.execute(
            select(WorkspaceSettings).where(
                WorkspaceSettings.workspace_id == workspace.id,
            ),
        )
        loaded = result.scalar_one()

        assert loaded.timezone == "Asia/Tokyo"
        assert loaded.locale == "ja"

    async def test_workspace_id_unique_constraint(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Два WorkspaceSettings для одного workspace вызывают IntegrityError."""
        workspace = await _persist_workspace(db_session)

        first_settings = WorkspaceSettings(workspace_id=workspace.id)
        db_session.add(first_settings)
        await db_session.flush()

        db_session.add(WorkspaceSettings(workspace_id=workspace.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()
