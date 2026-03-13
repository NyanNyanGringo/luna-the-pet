"""Тесты message handlers в group workspace-flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.db.models.workspace import Workspace, WorkspaceMember
from sqlalchemy.ext.asyncio import AsyncSession


def _make_text_message(text: str = "Привет") -> MagicMock:
    """Создаёт mock текстового сообщения."""
    message = MagicMock()
    message.text = text
    message.answer = AsyncMock()
    return message


def _make_voice_message(file_id: str = "voice-file-id") -> MagicMock:
    """Создаёт mock голосового сообщения."""
    message = MagicMock()
    message.voice = MagicMock(file_id=file_id)
    message.answer = AsyncMock()
    return message


def _workspace_and_member() -> tuple[Workspace, WorkspaceMember]:
    """Создаёт связку workspace/member для инъекции middleware."""
    workspace = Workspace(telegram_chat_id=-1001234567890, title="Группа")
    workspace.id = 777
    member = WorkspaceMember(
        workspace_id=777,
        telegram_user_id=100500,
        telegram_username="tester",
        telegram_first_name="Тестер",
    )
    return workspace, member


class TestTextHandler:
    """Тесты текстового handler'а."""

    async def test_calls_run_agent_with_workspace_id(self) -> None:
        """handle_text_message передаёт workspace.id в run_agent."""
        from backend.app.bot.handlers.message import handle_text_message

        message = _make_text_message("Когда кормить Луну?")
        workspace, member = _workspace_and_member()

        with patch(
            "backend.app.bot.handlers.message.run_agent",
            new=AsyncMock(return_value="В 18:00"),
        ) as run_agent_mock:
            await handle_text_message(
                message=message,
                session=AsyncMock(spec=AsyncSession),
                workspace=workspace,
                member=member,
            )

        run_agent_mock.assert_awaited_once()
        _, kwargs = run_agent_mock.await_args
        assert kwargs["workspace_id"] == workspace.id
        assert kwargs["user_id"] == member.telegram_user_id
        assert kwargs["user_message"] == "Когда кормить Луну?"
        message.answer.assert_awaited_once_with("В 18:00")


class TestVoiceHandler:
    """Тесты голосового handler'а."""

    async def test_transcribes_and_calls_agent(self) -> None:
        """Голос транскрибируется и результат отправляется в run_agent."""
        from backend.app.bot.handlers.message import handle_voice_message

        message = _make_voice_message("voice-123")
        workspace, member = _workspace_and_member()
        session = AsyncMock(spec=AsyncSession)
        bot = MagicMock()

        with (
            patch(
                "backend.app.bot.handlers.message.transcribe_voice",
                new=AsyncMock(return_value="Запиши прием к ветеринару"),
            ) as transcribe_mock,
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new=AsyncMock(return_value="Записал на завтра"),
            ) as run_agent_mock,
        ):
            await handle_voice_message(
                message=message,
                session=session,
                bot=bot,
                workspace=workspace,
                member=member,
            )

        transcribe_mock.assert_awaited_once_with(bot, "voice-123")
        _, kwargs = run_agent_mock.await_args
        assert kwargs["workspace_id"] == workspace.id
        assert kwargs["user_id"] == member.telegram_user_id
        assert kwargs["user_message"] == "Запиши прием к ветеринару"
        message.answer.assert_awaited_once_with("Записал на завтра")
