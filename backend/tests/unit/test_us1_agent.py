"""Минимальные workspace-centric тесты brain/prompts для US1."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.app.db.models.family import ConversationState
from backend.app.db.models.workspace import Workspace, WorkspaceSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_workspace(session: AsyncSession) -> Workspace:
    """Создаёт workspace с settings для тестов агента."""
    workspace = Workspace(
        telegram_chat_id=-1001234567890,
        title="Agent Workspace",
    )
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceSettings(workspace_id=workspace.id, timezone="Europe/Moscow"))
    await session.flush()
    return workspace


class TestBuildSystemPrompt:
    """Проверки build_system_prompt с workspace_id."""

    async def test_uses_workspace_pets_and_timezone(
        self, db_session: AsyncSession
    ) -> None:
        """Промпт строится по данным workspace, а не по legacy family."""
        from backend.app.agent.prompts import build_system_prompt

        workspace = await _create_workspace(db_session)
        pet_stub = SimpleNamespace(id=1, name="Луна", species="dog")

        with (
            patch(
                "backend.app.agent.prompts.pet_service.get_workspace_pets",
                new=AsyncMock(return_value=[pet_stub]),
            ),
            patch(
                "backend.app.agent.prompts.workspace_service.get_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.prompts.health_service.get_medications",
                new=AsyncMock(return_value=[]),
            ),
        ):
            prompt_text = await build_system_prompt(
                session=db_session,
                workspace_id=workspace.id,
                response_language="ru",
            )

        assert "Питомцы workspace" in prompt_text
        assert "Луна" in prompt_text


class TestLoadOrCreateStateRaceCondition:
    """Проверки _load_or_create_state при конкурентном создании."""

    async def test_handles_integrity_error_and_returns_existing_state(
        self,
        db_session: AsyncSession,
    ) -> None:
        """При IntegrityError (race condition) ищет существующую запись."""
        from backend.app.agent.brain import _load_or_create_state

        workspace = await _create_workspace(db_session)

        # Первый вызов — создаёт state
        state_first = await _load_or_create_state(
            db_session, user_id=100500, workspace_id=workspace.id
        )
        assert state_first is not None
        assert state_first.workspace_id == workspace.id

        # Второй вызов — возвращает существующий state (идемпотентность)
        state_second = await _load_or_create_state(
            db_session, user_id=100500, workspace_id=workspace.id
        )
        assert state_second.id == state_first.id


class TestRunAgent:
    """Проверки run_agent контракта с workspace_id."""

    async def test_run_agent_creates_state_with_workspace_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Для нового пользователя run_agent создаёт state с workspace_id."""
        from backend.app.agent.brain import run_agent

        workspace = await _create_workspace(db_session)
        final_response = SimpleNamespace(
            id="resp_1",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(text="Готово")],
                )
            ],
        )

        with (
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new=AsyncMock(return_value="prompt"),
            ),
            patch(
                "backend.app.agent.brain.get_ai_client",
                new=AsyncMock(return_value=SimpleNamespace()),
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain._call_openai",
                new=AsyncMock(return_value=final_response),
            ),
            patch(
                "backend.app.agent.brain._process_tool_calls_loop",
                new=AsyncMock(return_value=final_response),
            ),
            patch(
                "backend.app.agent.brain._resolve_workspace_today",
                new=AsyncMock(),
            ),
        ):
            reply = await run_agent(
                session=db_session,
                workspace_id=workspace.id,
                user_id=100500,
                user_message="Привет",
            )

        assert reply == "Готово"
        state = await db_session.scalar(
            select(ConversationState).where(
                ConversationState.telegram_user_id == 100500,
                ConversationState.workspace_id == workspace.id,
            )
        )
        assert state is not None
        assert state.last_response_id == "resp_1"
        assert state.turn_count == 1
