"""
Обработчики команд: /connectai, /invite и другие slash-команды.

Содержит логику подключения OpenAI OAuth и генерации invite-ссылок.
Экспортирует commands_router (Router).
"""

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from backend.app.bot.handlers.constants import (
    HELP_GROUP_TEXT,
    INVITE_NO_ADMIN_TEXT,
    INVITE_SUCCESS_TEMPLATE,
)
from backend.app.config import Settings
from backend.app.db.models.workspace import Workspace, WorkspaceMember
from backend.app.services.openai_auth_service import (
    build_authorize_url,
    generate_pkce_params,
    store_pkce_state_context,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def handle_connectai(
    message: Message,
    session: AsyncSession,
    workspace: Workspace,
    member: WorkspaceMember,
) -> None:
    """Обрабатывает /connectai — генерирует OAuth URL для подключения OpenAI.

    Проверяет наличие OPENAI_OAUTH_CLIENT_ID в конфиге. Если настроен —
    генерирует PKCE параметры и отправляет ссылку для авторизации.
    Если не настроен — сообщает об ошибке.

    Аргументы:
        message: входящее сообщение от пользователя
        session: асинхронная сессия SQLAlchemy

    Побочные эффекты:
        Отправляет сообщение со ссылкой OAuth или сообщением об ошибке.
    """
    settings = Settings()

    if not settings.OPENAI_OAUTH_CLIENT_ID:
        await message.answer("OAuth не настроен. Обратитесь к администратору.")
        return

    client_id = settings.OPENAI_OAUTH_CLIENT_ID
    redirect_uri = _build_oauth_redirect_uri(settings)
    await _send_oauth_link(
        message=message,
        client_id=client_id,
        redirect_uri=redirect_uri,
        workspace_id=workspace.id,
        member_id=member.telegram_user_id,
    )


def _build_oauth_redirect_uri(settings: Settings) -> str:
    """Строит redirect URI для OAuth callback на основе WEBHOOK_URL.

    Аргументы:
        settings: настройки с WEBHOOK_URL

    Возвращает:
        str: URL для OAuth callback
    """
    base_url = settings.WEBHOOK_URL or "http://localhost:8000"
    base_url = base_url.replace("/webhook", "")
    return f"{base_url}/api/auth/openai/callback"


async def _send_oauth_link(
    message: Message,
    client_id: str,
    redirect_uri: str,
    workspace_id: int,
    member_id: int,
) -> None:
    """Генерирует PKCE параметры и отправляет OAuth ссылку пользователю.

    Аргументы:
        message: сообщение для ответа
        client_id: гарантированно непустой OPENAI_OAUTH_CLIENT_ID
        redirect_uri: URL обратного вызова
        workspace_id: ID workspace для последующего OAuth callback
        member_id: Telegram user ID инициатора /connectai

    Побочные эффекты:
        Сохраняет state->code_verifier контекст для callback.
        Отправляет сообщение со ссылкой на авторизацию.
    """
    pkce_params = generate_pkce_params()
    store_pkce_state_context(
        state=pkce_params["state"],
        code_verifier=pkce_params["code_verifier"],
        workspace_id=workspace_id,
        member_id=member_id,
    )
    authorize_url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        pkce_params=pkce_params,
    )

    response_text = f"Для подключения OpenAI перейдите по ссылке:\n{authorize_url}"
    await message.answer(response_text)


async def handle_group_help(message: Message) -> None:
    """Обрабатывает /help в группе — стандартная справка с командами.

    Контракт (telegram-bot-commands.md#L73): /help работает в обоих контекстах.
    В группе — стандартная справка без инструкции по созданию группы.

    Аргументы:
        message: входящее сообщение с командой /help

    Побочные эффекты:
        Отправляет HELP_GROUP_TEXT со списком доступных команд.
    """
    await message.answer(HELP_GROUP_TEXT)


async def handle_invite(message: Message, bot: Bot) -> None:
    """Обрабатывает /invite — создаёт пригласительную ссылку на группу.

    Вызывает Telegram API для генерации invite-ссылки. Если бот не имеет
    прав администратора, отправляет пользователю инструкцию.

    Аргументы:
        message: входящее сообщение с командой /invite
        bot: экземпляр Bot для вызова Telegram API

    Побочные эффекты:
        Отправляет сообщение с invite-ссылкой или текстом ошибки.

    Ошибки:
        TelegramBadRequest: перехватывается, пользователь получает INVITE_NO_ADMIN_TEXT.
    """
    try:
        invite_link = await bot.create_chat_invite_link(
            message.chat.id, name="Luna Bot Invite"
        )
        response_text = INVITE_SUCCESS_TEMPLATE.format(link=invite_link.invite_link)
        await message.answer(response_text)
    except TelegramBadRequest:
        logger.warning(
            "Не удалось создать invite-ссылку для чата %s: нет прав", message.chat.id
        )
        await message.answer(INVITE_NO_ADMIN_TEXT)


def create_commands_router() -> Router:
    """Создаёт Router с обработчиками команд.

    Возвращает:
        Router: роутер с handler'ами /connectai и /invite
    """
    router = Router(name="commands")
    router.message.register(handle_group_help, Command("help"))
    router.message.register(handle_connectai, Command("connectai"))
    router.message.register(handle_invite, Command("invite"))
    return router


# Экспортируемый роутер для регистрации в Dispatcher
commands_router = create_commands_router()
