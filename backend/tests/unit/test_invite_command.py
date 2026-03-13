"""Тесты команды /invite — генерация пригласительной ссылки на группу.

Покрывает:
- Успешное создание invite-ссылки через bot.create_chat_invite_link
- Ошибка при отсутствии прав администратора (TelegramBadRequest)
- Регистрация handle_invite в commands router
- Корректность констант INVITE_SUCCESS_TEMPLATE и INVITE_NO_ADMIN_TEXT
"""

from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramBadRequest


def _make_mock_message(
    chat_id: int = -1001234567890,
) -> MagicMock:
    """Создаёт мок Message для группового чата с chat.id и answer()."""
    message = MagicMock()
    message.chat = MagicMock(id=chat_id)
    message.answer = AsyncMock()
    return message


def _make_mock_bot(invite_link: str = "https://t.me/+AbCdEfGhIjK") -> AsyncMock:
    """Создаёт мок Bot с create_chat_invite_link().

    Аргументы:
        invite_link: URL, который вернёт create_chat_invite_link

    Возвращает:
        AsyncMock: мок Bot
    """
    bot = AsyncMock()
    link_obj = MagicMock()
    link_obj.invite_link = invite_link
    bot.create_chat_invite_link = AsyncMock(return_value=link_obj)
    return bot


def _make_mock_bot_no_admin() -> AsyncMock:
    """Создаёт мок Bot, который выбрасывает TelegramBadRequest при создании ссылки."""
    bot = AsyncMock()
    method = MagicMock()
    method.method = "createChatInviteLink"
    bot.create_chat_invite_link = AsyncMock(
        side_effect=TelegramBadRequest(method=method, message="Not enough rights")
    )
    return bot


# ═══════════════════════════════════════════════════════════════════════════════
# Константы INVITE_SUCCESS_TEMPLATE и INVITE_NO_ADMIN_TEXT
# ═══════════════════════════════════════════════════════════════════════════════


class TestInviteConstants:
    """Проверяет наличие и корректность констант для /invite."""

    def test_invite_success_template_exists(self) -> None:
        """Константа INVITE_SUCCESS_TEMPLATE определена в constants.py."""
        from backend.app.bot.handlers.constants import INVITE_SUCCESS_TEMPLATE

        assert isinstance(INVITE_SUCCESS_TEMPLATE, str)

    def test_invite_success_template_has_link_placeholder(self) -> None:
        """Шаблон содержит плейсхолдер {link} для подстановки ссылки."""
        from backend.app.bot.handlers.constants import INVITE_SUCCESS_TEMPLATE

        assert "{link}" in INVITE_SUCCESS_TEMPLATE

    def test_invite_success_template_contains_key_phrases(self) -> None:
        """Шаблон содержит ключевые фразы из контракта."""
        from backend.app.bot.handlers.constants import INVITE_SUCCESS_TEMPLATE

        assert "ссылка" in INVITE_SUCCESS_TEMPLATE.lower()
        assert "пригласить" in INVITE_SUCCESS_TEMPLATE.lower()

    def test_invite_no_admin_text_exists(self) -> None:
        """Константа INVITE_NO_ADMIN_TEXT определена в constants.py."""
        from backend.app.bot.handlers.constants import INVITE_NO_ADMIN_TEXT

        assert isinstance(INVITE_NO_ADMIN_TEXT, str)

    def test_invite_no_admin_text_contains_key_phrases(self) -> None:
        """Текст ошибки содержит ключевые фразы из контракта."""
        from backend.app.bot.handlers.constants import INVITE_NO_ADMIN_TEXT

        text_lower = INVITE_NO_ADMIN_TEXT.lower()
        assert "администратор" in text_lower
        assert "права" in text_lower

    def test_invite_success_template_matches_contract(self) -> None:
        """Шаблон успешного ответа точно соответствует контракту."""
        from backend.app.bot.handlers.constants import INVITE_SUCCESS_TEMPLATE

        expected = (
            "🔗 Пригласительная ссылка на группу:\n"
            "{link}\n"
            "\n"
            "Отправьте эту ссылку тому, кого хотите пригласить."
        )
        assert expected == INVITE_SUCCESS_TEMPLATE

    def test_invite_no_admin_text_matches_contract(self) -> None:
        """Текст ошибки точно соответствует контракту."""
        from backend.app.bot.handlers.constants import INVITE_NO_ADMIN_TEXT

        expected = (
            "⚠️ Мне нужны права администратора, чтобы создать ссылку.\n"
            "\n"
            "Попросите администратора группы назначить меня админом "
            "или создайте ссылку вручную через настройки группы."
        )
        assert expected == INVITE_NO_ADMIN_TEXT


# ═══════════════════════════════════════════════════════════════════════════════
# Успешное создание invite-ссылки
# ═══════════════════════════════════════════════════════════════════════════════


class TestInviteSuccess:
    """Тесты /invite — успешное создание пригласительной ссылки."""

    async def test_creates_invite_link_with_correct_chat_id(self) -> None:
        """Вызывает bot.create_chat_invite_link с chat_id из сообщения."""
        from backend.app.bot.handlers.commands import handle_invite

        chat_id = -1009876543210
        message = _make_mock_message(chat_id=chat_id)
        bot = _make_mock_bot()

        await handle_invite(message, bot)

        bot.create_chat_invite_link.assert_awaited_once()
        call_kwargs = bot.create_chat_invite_link.call_args
        assert (
            call_kwargs[0][0] == chat_id or call_kwargs.kwargs.get("chat_id") == chat_id
        )

    async def test_creates_invite_link_with_name(self) -> None:
        """Передаёт name='Luna Bot Invite' при создании ссылки."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message()
        bot = _make_mock_bot()

        await handle_invite(message, bot)

        call_kwargs = bot.create_chat_invite_link.call_args
        # name может быть как positional, так и keyword аргументом
        assert call_kwargs.kwargs.get("name") == "Luna Bot Invite" or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "Luna Bot Invite"
        )

    async def test_responds_with_formatted_invite_link(self) -> None:
        """Отвечает сообщением с invite-ссылкой по шаблону INVITE_SUCCESS_TEMPLATE."""
        from backend.app.bot.handlers.commands import handle_invite
        from backend.app.bot.handlers.constants import INVITE_SUCCESS_TEMPLATE

        link = "https://t.me/+TestInviteLink123"
        message = _make_mock_message()
        bot = _make_mock_bot(invite_link=link)

        await handle_invite(message, bot)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        expected = INVITE_SUCCESS_TEMPLATE.format(link=link)
        assert response_text == expected

    async def test_response_contains_actual_link(self) -> None:
        """В ответе содержится реальная invite-ссылка."""
        from backend.app.bot.handlers.commands import handle_invite

        link = "https://t.me/+UniqueLink999"
        message = _make_mock_message()
        bot = _make_mock_bot(invite_link=link)

        await handle_invite(message, bot)

        response_text = message.answer.call_args[0][0]
        assert link in response_text


# ═══════════════════════════════════════════════════════════════════════════════
# Ошибка — нет прав администратора
# ═══════════════════════════════════════════════════════════════════════════════


class TestInviteNoAdminRights:
    """Тесты /invite — бот без прав администратора."""

    async def test_responds_with_no_admin_text(self) -> None:
        """При TelegramBadRequest отвечает текстом INVITE_NO_ADMIN_TEXT."""
        from backend.app.bot.handlers.commands import handle_invite
        from backend.app.bot.handlers.constants import INVITE_NO_ADMIN_TEXT

        message = _make_mock_message()
        bot = _make_mock_bot_no_admin()

        await handle_invite(message, bot)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert response_text == INVITE_NO_ADMIN_TEXT

    async def test_does_not_raise_on_bad_request(self) -> None:
        """TelegramBadRequest обрабатывается внутри, исключение не пробрасывается."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message()
        bot = _make_mock_bot_no_admin()

        # Не должно выбросить исключение
        await handle_invite(message, bot)

    async def test_error_message_mentions_admin(self) -> None:
        """Сообщение об ошибке упоминает администратора."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message()
        bot = _make_mock_bot_no_admin()

        await handle_invite(message, bot)

        response_text = message.answer.call_args[0][0]
        assert "администратор" in response_text.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Регистрация handle_invite в commands router
# ═══════════════════════════════════════════════════════════════════════════════


class TestInviteRouterRegistration:
    """Тесты регистрации /invite в commands router."""

    def test_invite_handler_registered_in_commands_router(self) -> None:
        """handle_invite зарегистрирован в роутере commands."""
        from backend.app.bot.handlers.commands import (
            create_commands_router,
            handle_invite,
        )

        router = create_commands_router()

        handler_callbacks = [h.callback for h in router.message.handlers]
        assert handle_invite in handler_callbacks

    def test_commands_router_has_at_least_two_handlers(self) -> None:
        """После добавления /invite роутер содержит минимум 2 обработчика."""
        from backend.app.bot.handlers.commands import create_commands_router

        router = create_commands_router()
        assert len(router.message.handlers) >= 2
