"""Тесты audit_service: запись ChangeLog с tenant-контекстом workspace."""

from __future__ import annotations

from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.workspace import Workspace
from backend.app.services.audit_service import log_change
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_workspace(session: AsyncSession) -> Workspace:
    """Создаёт workspace для проверки audit workspace_id."""
    workspace = Workspace(
        telegram_chat_id=-100900000001,
        title="Audit Workspace",
    )
    session.add(workspace)
    await session.flush()
    return workspace


class TestAuditService:
    """Проверки записи ChangeLog через audit_service.log_change."""

    async def test_log_change_persists_workspace_context(
        self,
        db_session: AsyncSession,
    ) -> None:
        """При передаче workspace_id запись аудита хранит tenant-контекст."""
        workspace = await _create_workspace(db_session)

        created_entry = await log_change(
            session=db_session,
            entity_type="pet",
            entity_id=11,
            action="create",
            actor_id=42,
            workspace_id=workspace.id,
            diff_json={"name": "Луна"},
        )

        persisted_entry = await db_session.scalar(
            select(ChangeLog).where(ChangeLog.id == created_entry.id),
        )
        assert persisted_entry is not None
        assert persisted_entry.workspace_id == workspace.id
