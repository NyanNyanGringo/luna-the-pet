"""Тесты private start/help хендлеров — отклоняют личные сообщения."""

from unittest.mock import AsyncMock, MagicMock


def _make_mock_message(
    user_id: int = 123456789,
    first_name: str = "Тест",
    text: str = "/start",
) -> MagicMock:
    """Создаёт мок Message с from_user и answer()."""
    message = MagicMock()
    message.from_user = MagicMock(
        id=user_id,
        first_name=first_name,
        username="testuser",
    )
    message.text = text
    message.answer = AsyncMock()
    return message


class TestHandleStart:
    """Тесты /start в private-чате."""

    async def test_responds_with_group_instruction(self) -> None:
        """/start отправляет инструкцию по созданию группы из constants."""
        from backend.app.bot.handlers.constants import START_PRIVATE_TEXT
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(first_name="Новичок")
        await handle_start(message)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert response_text == START_PRIVATE_TEXT

    async def test_start_text_contains_key_phrases(self) -> None:
        """Текст /start содержит ключевые фразы про группу."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message()
        await handle_start(message)

        response_text = message.answer.call_args[0][0]
        assert "групп" in response_text.lower()
        assert "Луна" in response_text


class TestHandleHelp:
    """Тесты /help в private-чате."""

    async def test_help_contains_group_instruction(self) -> None:
        """/help содержит инструкцию о работе только в группах."""
        from backend.app.bot.handlers.start import handle_help

        message = _make_mock_message(text="/help")
        await handle_help(message)

        message.answer.assert_awaited_once()
        help_text = message.answer.call_args[0][0]
        assert "групп" in help_text.lower()

    async def test_help_contains_commands(self) -> None:
        """/help перечисляет доступные команды."""
        from backend.app.bot.handlers.start import handle_help

        message = _make_mock_message(text="/help")
        await handle_help(message)

        help_text = message.answer.call_args[0][0]
        assert "/start" in help_text
        assert "/help" in help_text
