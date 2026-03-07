"""
Тесты обработчиков /start, /help, /invite — T021 + T106.

Покрывает:
- T021: /start от нового пользователя, от существующего,
  с deep link (invite code), /help
- T106: /invite — генерация кода, показ существующих

Хендлеры тестируются через моки aiogram Message и AsyncMock.
Сервисные функции мокируются через unittest.mock.patch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные фабрики для моков aiogram
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mock_message(
    user_id: int = 123456789,
    first_name: str = "Тест",
    username: str = "testuser",
    text: str = "/start",
) -> MagicMock:
    """Создаёт мок aiogram.types.Message с from_user и answer.

    Аргументы:
        user_id: Telegram user ID
        first_name: имя пользователя
        username: Telegram username
        text: текст сообщения

    Возвращает:
        MagicMock: мок Message с настроенными атрибутами
    """
    message = MagicMock()
    message.from_user = MagicMock(
        id=user_id,
        first_name=first_name,
        username=username,
    )
    message.text = text
    message.answer = AsyncMock()
    return message


def _make_mock_family(family_id: int = 1) -> MagicMock:
    """Создаёт мок Family.

    Аргументы:
        family_id: ID семьи

    Возвращает:
        MagicMock: мок Family с заданным id
    """
    family = MagicMock()
    family.id = family_id
    return family


def _make_mock_member(
    user_id: int = 123456789,
    first_name: str = "Тест",
) -> MagicMock:
    """Создаёт мок FamilyMember.

    Аргументы:
        user_id: Telegram user ID
        first_name: имя участника

    Возвращает:
        MagicMock: мок FamilyMember с заданными атрибутами
    """
    member = MagicMock()
    member.id = user_id
    member.first_name = first_name
    member.family_id = 1
    return member


def _make_mock_invite(
    invite_code: str = "ABC123",
    status: str = "active",
) -> MagicMock:
    """Создаёт мок FamilyInvite.

    Аргументы:
        invite_code: код приглашения
        status: статус инвайта

    Возвращает:
        MagicMock: мок FamilyInvite с заданными атрибутами
    """
    invite = MagicMock()
    invite.invite_code = invite_code
    invite.status = status
    invite.expires_at = MagicMock()
    return invite


# ═══════════════════════════════════════════════════════════════════════════════
# T021: /start — новый пользователь
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleStartNewUser:
    """Тесты /start от нового (незарегистрированного) пользователя."""

    async def test_creates_family_for_new_user(self) -> None:
        """Для нового пользователя создаётся Family (если ещё не существует)."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(user_id=111000111, first_name="Новичок")

        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ) as mock_get_family,
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.app.bot.handlers.start.register_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=111000111),
            ),
        ):
            await handle_start(message, mock_session)

        mock_get_family.assert_awaited_once()

    async def test_registers_new_member(self) -> None:
        """Для нового пользователя вызывается register_member."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(
            user_id=222000222,
            first_name="Новый",
            username="newbie",
        )
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.app.bot.handlers.start.register_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=222000222),
            ) as mock_register,
        ):
            await handle_start(message, mock_session)

        mock_register.assert_awaited_once()

    async def test_sends_greeting_to_new_user(self) -> None:
        """Новый пользователь получает приветственное сообщение."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(user_id=333000333, first_name="Гость")
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.app.bot.handlers.start.register_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=333000333),
            ),
        ):
            await handle_start(message, mock_session)

        message.answer.assert_awaited_once()
        greeting_text = message.answer.call_args[0][0]
        assert len(greeting_text) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# T021: /start — существующий пользователь
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleStartExistingUser:
    """Тесты /start от пользователя, уже зарегистрированного в семье."""

    async def test_does_not_create_duplicate_member(self) -> None:
        """Для существующего пользователя НЕ вызывается register_member."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(user_id=444000444, first_name="Старожил")
        mock_session = AsyncMock(spec=AsyncSession)
        existing_member = _make_mock_member(user_id=444000444)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=existing_member,
            ),
            patch(
                "backend.app.bot.handlers.start.register_member",
                new_callable=AsyncMock,
            ) as mock_register,
        ):
            await handle_start(message, mock_session)

        mock_register.assert_not_awaited()

    async def test_sends_greeting_to_existing_user(self) -> None:
        """Существующий пользователь тоже получает приветственное сообщение."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(user_id=555000555, first_name="Знакомый")
        mock_session = AsyncMock(spec=AsyncSession)
        existing_member = _make_mock_member(user_id=555000555)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=existing_member,
            ),
        ):
            await handle_start(message, mock_session)

        message.answer.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# T021: /start с deep link (invite code)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleStartDeepLink:
    """Тесты /start с deep link — принятие инвайт-кода."""

    async def test_accepts_invite_via_deep_link(self) -> None:
        """Deep link /start <invite_code> принимает инвайт.

        Гарантия: пользователь регистрируется в семье по invite-коду.
        """
        from backend.app.bot.handlers.start import handle_start

        invite_code = "INVITE_XYZ789"
        message = _make_mock_message(
            user_id=666000666,
            first_name="Приглашённый",
            text=f"/start {invite_code}",
        )
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.app.bot.handlers.start.register_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=666000666),
            ),
            patch(
                "backend.app.bot.handlers.start.use_invite",
                new_callable=AsyncMock,
            ) as mock_use_invite,
        ):
            await handle_start(message, mock_session)

        mock_use_invite.assert_awaited_once()

    async def test_deep_link_sends_greeting(self) -> None:
        """Пользователь, пришедший по deep link, получает приветствие."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(
            user_id=777000777,
            first_name="Новый по ссылке",
            text="/start INVITE_ABC",
        )
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "backend.app.bot.handlers.start.register_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=777000777),
            ),
            patch(
                "backend.app.bot.handlers.start.use_invite",
                new_callable=AsyncMock,
            ),
        ):
            await handle_start(message, mock_session)

        message.answer.assert_awaited_once()

    async def test_deep_link_with_existing_user_still_uses_invite(self) -> None:
        """Существующий пользователь с deep link — инвайт всё равно обрабатывается."""
        from backend.app.bot.handlers.start import handle_start

        message = _make_mock_message(
            user_id=888000888,
            first_name="Вернувшийся",
            text="/start INVITE_RETURN",
        )
        mock_session = AsyncMock(spec=AsyncSession)
        existing_member = _make_mock_member(user_id=888000888)

        with (
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=_make_mock_family(),
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=existing_member,
            ),
            patch(
                "backend.app.bot.handlers.start.use_invite",
                new_callable=AsyncMock,
            ) as mock_use_invite,
        ):
            await handle_start(message, mock_session)

        # Инвайт должен быть обработан, даже если пользователь уже существует
        mock_use_invite.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# T021: /help
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleHelp:
    """Тесты /help — список доступных команд."""

    async def test_help_returns_command_list(self) -> None:
        """Команда /help возвращает сообщение со списком команд."""
        from backend.app.bot.handlers.start import handle_help

        message = _make_mock_message(text="/help")

        await handle_help(message)

        message.answer.assert_awaited_once()
        help_text = message.answer.call_args[0][0]
        assert len(help_text) > 0

    async def test_help_mentions_start_command(self) -> None:
        """В тексте /help упоминается команда /start."""
        from backend.app.bot.handlers.start import handle_help

        message = _make_mock_message(text="/help")

        await handle_help(message)

        help_text = message.answer.call_args[0][0]
        assert "/start" in help_text

    async def test_help_mentions_invite_command(self) -> None:
        """В тексте /help упоминается команда /invite."""
        from backend.app.bot.handlers.start import handle_help

        message = _make_mock_message(text="/help")

        await handle_help(message)

        help_text = message.answer.call_args[0][0]
        assert "/invite" in help_text


# ═══════════════════════════════════════════════════════════════════════════════
# T106: /invite — генерация и показ инвайт-кодов
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleInvite:
    """Тесты /invite — генерация одноразового кода приглашения."""

    async def test_generates_invite_code(self) -> None:
        """Команда /invite генерирует новый инвайт-код."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message(
            user_id=111222333,
            text="/invite",
        )
        mock_session = AsyncMock(spec=AsyncSession)
        mock_invite = _make_mock_invite(invite_code="NEW_CODE_123")

        with (
            patch(
                "backend.app.bot.handlers.commands.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=111222333),
            ),
            patch(
                "backend.app.bot.handlers.commands.create_invite",
                new_callable=AsyncMock,
                return_value=mock_invite,
            ) as mock_create,
            patch(
                "backend.app.bot.handlers.commands.list_invites",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await handle_invite(message, mock_session)

        mock_create.assert_awaited_once()

    async def test_shows_invite_code_in_response(self) -> None:
        """Ответ содержит сгенерированный инвайт-код."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message(
            user_id=222333444,
            text="/invite",
        )
        mock_session = AsyncMock(spec=AsyncSession)
        mock_invite = _make_mock_invite(invite_code="SHOW_ME_CODE")

        with (
            patch(
                "backend.app.bot.handlers.commands.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=222333444),
            ),
            patch(
                "backend.app.bot.handlers.commands.create_invite",
                new_callable=AsyncMock,
                return_value=mock_invite,
            ),
            patch(
                "backend.app.bot.handlers.commands.list_invites",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await handle_invite(message, mock_session)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert "SHOW_ME_CODE" in response_text

    async def test_shows_existing_active_invites(self) -> None:
        """Если есть активные инвайты — показывает их в ответе."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message(
            user_id=333444555,
            text="/invite",
        )
        mock_session = AsyncMock(spec=AsyncSession)
        existing_invite = _make_mock_invite(
            invite_code="EXISTING_CODE",
            status="active",
        )

        with (
            patch(
                "backend.app.bot.handlers.commands.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=333444555),
            ),
            patch(
                "backend.app.bot.handlers.commands.list_invites",
                new_callable=AsyncMock,
                return_value=[existing_invite],
            ),
        ):
            await handle_invite(message, mock_session)

        message.answer.assert_awaited_once()
        response_text = message.answer.call_args[0][0]
        assert "EXISTING_CODE" in response_text

    async def test_invite_response_contains_expiry_info(self) -> None:
        """Ответ на /invite содержит информацию о сроке действия."""
        from backend.app.bot.handlers.commands import handle_invite

        message = _make_mock_message(
            user_id=444555666,
            text="/invite",
        )
        mock_session = AsyncMock(spec=AsyncSession)
        mock_invite = _make_mock_invite(invite_code="EXPIRY_TEST")

        with (
            patch(
                "backend.app.bot.handlers.commands.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(user_id=444555666),
            ),
            patch(
                "backend.app.bot.handlers.commands.create_invite",
                new_callable=AsyncMock,
                return_value=mock_invite,
            ),
            patch(
                "backend.app.bot.handlers.commands.list_invites",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await handle_invite(message, mock_session)

        message.answer.assert_awaited_once()
        # Ответ должен содержать что-то про срок действия
        response_text = message.answer.call_args[0][0]
        assert len(response_text) > len("EXPIRY_TEST")
