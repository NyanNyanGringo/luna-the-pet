"""
Тесты обработчиков текстовых и голосовых сообщений Phase 3 (US1) — T034, T035.

Покрывает:
- T034: handle_text_message, handle_voice_message, create_message_router
- T035: регистрация message router в create_dispatcher

Хендлеры тестируются через моки aiogram Message и AsyncMock.
Зависимости (run_agent, transcribe_voice, get_member) мокируются через patch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные фабрики для моков aiogram
# ═══════════════════════════════════════════════════════════════════════════════

_FAKE_USER_ID = 111222333
_FAKE_FAMILY_ID = 42
_FAKE_MEMBER_ID = 111222333


def _make_mock_member(
    member_id: int = _FAKE_MEMBER_ID,
    family_id: int = _FAKE_FAMILY_ID,
) -> MagicMock:
    """Создаёт мок FamilyMember.

    Аргументы:
        member_id: ID участника (совпадает с Telegram user ID)
        family_id: ID семьи

    Возвращает:
        MagicMock: мок FamilyMember с заданными атрибутами
    """
    member = MagicMock()
    member.id = member_id
    member.family_id = family_id
    member.is_authorized = True
    return member


def _make_mock_text_message(
    user_id: int = _FAKE_USER_ID,
    text: str = "Когда кормить Луну?",
) -> MagicMock:
    """Создаёт мок aiogram.types.Message для текстового сообщения.

    Аргументы:
        user_id: Telegram user ID
        text: текст сообщения

    Возвращает:
        MagicMock: мок Message с from_user, text и answer
    """
    message = MagicMock()
    message.from_user = MagicMock(id=user_id)
    message.text = text
    message.answer = AsyncMock()
    return message


def _make_mock_voice_message(
    user_id: int = _FAKE_USER_ID,
    voice_file_id: str = "AgACAgIAAxkBAAI",
) -> MagicMock:
    """Создаёт мок aiogram.types.Message для голосового сообщения.

    Аргументы:
        user_id: Telegram user ID
        voice_file_id: ID голосового файла в Telegram

    Возвращает:
        MagicMock: мок Message с from_user, voice.file_id и answer
    """
    message = MagicMock()
    message.from_user = MagicMock(id=user_id)
    message.voice = MagicMock(file_id=voice_file_id)
    message.answer = AsyncMock()
    return message


# ═══════════════════════════════════════════════════════════════════════════════
# T034: handle_text_message — обработка текстовых сообщений
# ═══════════════════════════════════════════════════════════════════════════════


class TestTextMessageHandler:
    """Тесты handle_text_message — обработка обычных текстовых сообщений."""

    async def test_calls_run_agent_with_correct_arguments(self) -> None:
        """run_agent вызывается с family_id, user_id и текстом из сообщения."""
        from backend.app.bot.handlers.message import handle_text_message

        message = _make_mock_text_message(
            user_id=_FAKE_USER_ID,
            text="Когда следующая прививка?",
        )
        mock_session = AsyncMock(spec=AsyncSession)
        mock_bot = MagicMock()
        mock_member = _make_mock_member()

        with (
            patch(
                "backend.app.bot.handlers.message.get_member",
                new_callable=AsyncMock,
                return_value=mock_member,
            ),
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new_callable=AsyncMock,
                return_value="Следующая прививка через месяц.",
            ) as mock_run_agent,
        ):
            await handle_text_message(message, mock_session, mock_bot)

        mock_run_agent.assert_awaited_once_with(
            mock_session,
            family_id=_FAKE_FAMILY_ID,
            user_id=_FAKE_MEMBER_ID,
            user_message="Когда следующая прививка?",
        )

    async def test_sends_agent_response_via_message_answer(self) -> None:
        """Ответ агента отправляется пользователю через message.answer."""
        from backend.app.bot.handlers.message import handle_text_message

        agent_response = "Луну нужно покормить в 18:00."
        message = _make_mock_text_message(text="Когда кормить?")
        mock_session = AsyncMock(spec=AsyncSession)
        mock_bot = MagicMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(),
            ),
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new_callable=AsyncMock,
                return_value=agent_response,
            ),
        ):
            await handle_text_message(message, mock_session, mock_bot)

        message.answer.assert_awaited_once_with(agent_response)

    async def test_uses_message_text_as_user_message(self) -> None:
        """В run_agent передаётся именно message.text, а не другой атрибут."""
        from backend.app.bot.handlers.message import handle_text_message

        original_text = "Какой корм лучше для щенка?"
        message = _make_mock_text_message(text=original_text)
        mock_session = AsyncMock(spec=AsyncSession)
        mock_bot = MagicMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(),
            ),
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new_callable=AsyncMock,
                return_value="Рекомендую корм X.",
            ) as mock_run_agent,
        ):
            await handle_text_message(message, mock_session, mock_bot)

        # Проверяем, что user_message в вызове совпадает с message.text
        call_kwargs = mock_run_agent.call_args
        assert call_kwargs.kwargs["user_message"] == original_text


# ═══════════════════════════════════════════════════════════════════════════════
# T034: handle_voice_message — обработка голосовых сообщений
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoiceMessageHandler:
    """Тесты handle_voice_message — обработка голосовых сообщений."""

    async def test_calls_transcribe_voice_with_bot_and_file_id(self) -> None:
        """transcribe_voice вызывается с bot и voice.file_id из сообщения."""
        from backend.app.bot.handlers.message import handle_voice_message

        voice_file_id = "AgACAgIAAxkBAAI_VOICE"
        message = _make_mock_voice_message(voice_file_id=voice_file_id)
        mock_session = AsyncMock(spec=AsyncSession)
        mock_bot = MagicMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(),
            ),
            patch(
                "backend.app.bot.handlers.message.transcribe_voice",
                new_callable=AsyncMock,
                return_value="Транскрибированный текст",
            ) as mock_transcribe,
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new_callable=AsyncMock,
                return_value="Ответ агента на голос.",
            ),
        ):
            await handle_voice_message(message, mock_session, mock_bot)

        mock_transcribe.assert_awaited_once_with(mock_bot, voice_file_id)

    async def test_passes_transcription_to_run_agent(self) -> None:
        """Транскрибированный текст передаётся в run_agent как user_message."""
        from backend.app.bot.handlers.message import handle_voice_message

        transcribed_text = "Нужно записать Луну к ветеринару"
        message = _make_mock_voice_message()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_bot = MagicMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(),
            ),
            patch(
                "backend.app.bot.handlers.message.transcribe_voice",
                new_callable=AsyncMock,
                return_value=transcribed_text,
            ),
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new_callable=AsyncMock,
                return_value="Записал на прием.",
            ) as mock_run_agent,
        ):
            await handle_voice_message(message, mock_session, mock_bot)

        mock_run_agent.assert_awaited_once_with(
            mock_session,
            family_id=_FAKE_FAMILY_ID,
            user_id=_FAKE_MEMBER_ID,
            user_message=transcribed_text,
        )

    async def test_sends_agent_response_via_message_answer(self) -> None:
        """Ответ агента на голосовое сообщение отправляется через message.answer."""
        from backend.app.bot.handlers.message import handle_voice_message

        agent_response = "Визит к ветеринару назначен на завтра."
        message = _make_mock_voice_message()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_bot = MagicMock()

        with (
            patch(
                "backend.app.bot.handlers.message.get_member",
                new_callable=AsyncMock,
                return_value=_make_mock_member(),
            ),
            patch(
                "backend.app.bot.handlers.message.transcribe_voice",
                new_callable=AsyncMock,
                return_value="Запиши к ветеринару",
            ),
            patch(
                "backend.app.bot.handlers.message.run_agent",
                new_callable=AsyncMock,
                return_value=agent_response,
            ),
        ):
            await handle_voice_message(message, mock_session, mock_bot)

        message.answer.assert_awaited_once_with(agent_response)


# ═══════════════════════════════════════════════════════════════════════════════
# T034: create_message_router — фабрика роутера сообщений
# ═══════════════════════════════════════════════════════════════════════════════


class TestMessageRouter:
    """Тесты create_message_router — создание Router для сообщений."""

    def test_returns_router_instance(self) -> None:
        """create_message_router() возвращает экземпляр aiogram.Router."""
        from backend.app.bot.handlers.message import create_message_router

        router = create_message_router()
        assert isinstance(router, Router)

    def test_router_has_name_message(self) -> None:
        """Router имеет name='message'."""
        from backend.app.bot.handlers.message import create_message_router

        router = create_message_router()
        assert router.name == "message"


# ═══════════════════════════════════════════════════════════════════════════════
# T035: Dispatcher включает message router
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateDispatcherIncludesMessageRouter:
    """Тесты регистрации message router в Dispatcher (T035)."""

    def test_dispatcher_includes_message_router(self) -> None:
        """create_dispatcher() регистрирует роутер с name='message'."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        router_names = {router.name for router in dispatcher.sub_routers}

        assert "message" in router_names
