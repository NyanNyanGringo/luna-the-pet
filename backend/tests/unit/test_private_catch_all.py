"""Тесты catch-all обработчика для private-чата.

Проверяет, что любое сообщение в private корректно перенаправляет
пользователя в группу в зависимости от количества его workspace'ов.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.db.models.workspace import Workspace


def _make_mock_message(
    user_id: int = 100500,
    first_name: str = "Тестер",
) -> MagicMock:
    """Создаёт мок Message для private-чата."""
    message = MagicMock()
    message.from_user = MagicMock(
        id=user_id,
        first_name=first_name,
        username="tester",
    )
    message.answer = AsyncMock()
    return message


def _make_workspace(title: str, chat_id: int = -1001234567890) -> Workspace:
    """Создаёт мок workspace с заданным title."""
    workspace = Workspace(telegram_chat_id=chat_id, title=title)
    workspace.id = abs(chat_id) % 1000
    return workspace


class TestPrivateCatchAllZeroWorkspaces:
    """Когда у пользователя нет групп — инструкция по созданию."""

    async def test_no_workspaces_sends_start_text(self) -> None:
        """Без групп — отправляем инструкцию START_PRIVATE_TEXT."""
        from backend.app.bot.handlers.constants import START_PRIVATE_TEXT
        from backend.app.bot.handlers.message import handle_private_catch_all

        message = _make_mock_message()
        session = AsyncMock()
        bot = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_user_workspaces",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.bot.handlers.message.verify_user_workspaces",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await handle_private_catch_all(message, session, bot)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert response_text == START_PRIVATE_TEXT


class TestPrivateCatchAllOneWorkspace:
    """Когда у пользователя одна группа — перенаправление."""

    async def test_one_workspace_sends_redirect(self) -> None:
        """Одна группа — отправляем ссылку на конкретную группу."""
        from backend.app.bot.handlers.message import handle_private_catch_all

        workspace = _make_workspace("Семья Ивановых")
        message = _make_mock_message()
        session = AsyncMock()
        bot = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_user_workspaces",
                new=AsyncMock(return_value=[workspace]),
            ),
            patch(
                "backend.app.bot.handlers.message.verify_user_workspaces",
                new=AsyncMock(return_value=[workspace]),
            ),
        ):
            await handle_private_catch_all(message, session, bot)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert "Семья Ивановых" in response_text
        assert "группе" in response_text.lower()

    async def test_one_workspace_contains_group_only_message(self) -> None:
        """Ответ содержит сообщение о работе только в группе."""
        from backend.app.bot.handlers.constants import PRIVATE_ONE_GROUP_TEMPLATE
        from backend.app.bot.handlers.message import handle_private_catch_all

        workspace = _make_workspace("Наши питомцы")
        message = _make_mock_message()
        session = AsyncMock()
        bot = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_user_workspaces",
                new=AsyncMock(return_value=[workspace]),
            ),
            patch(
                "backend.app.bot.handlers.message.verify_user_workspaces",
                new=AsyncMock(return_value=[workspace]),
            ),
        ):
            await handle_private_catch_all(message, session, bot)

        response_text = message.answer.call_args[0][0]
        expected = PRIVATE_ONE_GROUP_TEMPLATE.format(title="Наши питомцы")
        assert response_text == expected


class TestPrivateCatchAllMultipleWorkspaces:
    """Когда у пользователя несколько групп — список."""

    async def test_multiple_workspaces_lists_all(self) -> None:
        """Несколько групп — список всех групп в ответе."""
        from backend.app.bot.handlers.message import handle_private_catch_all

        workspaces = [
            _make_workspace("Группа 1", chat_id=-1001111111111),
            _make_workspace("Группа 2", chat_id=-1002222222222),
        ]
        message = _make_mock_message()
        session = AsyncMock()
        bot = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_user_workspaces",
                new=AsyncMock(return_value=workspaces),
            ),
            patch(
                "backend.app.bot.handlers.message.verify_user_workspaces",
                new=AsyncMock(return_value=workspaces),
            ),
        ):
            await handle_private_catch_all(message, session, bot)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert "Группа 1" in response_text
        assert "Группа 2" in response_text
        assert "группах" in response_text.lower()

    async def test_multiple_workspaces_header(self) -> None:
        """Ответ начинается с заголовка PRIVATE_MULTI_GROUP_HEADER."""
        from backend.app.bot.handlers.constants import PRIVATE_MULTI_GROUP_HEADER
        from backend.app.bot.handlers.message import handle_private_catch_all

        workspaces = [
            _make_workspace("Альфа", chat_id=-1001111111111),
            _make_workspace("Бета", chat_id=-1002222222222),
        ]
        message = _make_mock_message()
        session = AsyncMock()
        bot = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_user_workspaces",
                new=AsyncMock(return_value=workspaces),
            ),
            patch(
                "backend.app.bot.handlers.message.verify_user_workspaces",
                new=AsyncMock(return_value=workspaces),
            ),
        ):
            await handle_private_catch_all(message, session, bot)

        response_text = message.answer.call_args[0][0]
        assert response_text.startswith(PRIVATE_MULTI_GROUP_HEADER)


class TestPrivateCatchAllCallsWorkspaceService:
    """Проверяет корректность вызова get_user_workspaces."""

    async def test_passes_user_id_to_workspace_service(self) -> None:
        """Передаёт telegram_user_id в get_user_workspaces."""
        from backend.app.bot.handlers.message import handle_private_catch_all

        message = _make_mock_message(user_id=999888)
        session = AsyncMock()
        bot = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_user_workspaces",
                new=AsyncMock(return_value=[]),
            ) as mock_get,
            patch(
                "backend.app.bot.handlers.message.verify_user_workspaces",
                new=AsyncMock(return_value=[]),
            ) as mock_verify,
        ):
            await handle_private_catch_all(message, session, bot)

        mock_get.assert_awaited_once_with(session, 999888)
        mock_verify.assert_awaited_once_with(
            bot=bot,
            session=session,
            telegram_user_id=999888,
            workspaces=[],
        )


class TestCreatePrivateMessageRouter:
    """Тесты фабрики create_private_message_router."""

    def test_router_created_with_name(self) -> None:
        """Фабрика возвращает Router с именем 'private_message'."""
        from backend.app.bot.handlers.message import create_private_message_router

        router = create_private_message_router()
        assert router.name == "private_message"

    def test_router_has_message_handler(self) -> None:
        """Роутер содержит хотя бы один handler для сообщений."""
        from backend.app.bot.handlers.message import create_private_message_router

        router = create_private_message_router()
        # aiogram 3.x: message.handlers — список зарегистрированных handler'ов
        assert len(router.message.handlers) > 0
