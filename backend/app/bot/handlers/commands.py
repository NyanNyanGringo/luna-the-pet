"""
Обработчики команд: /invite, /connectai и другие slash-команды.

Содержит логику генерации инвайт-кодов, подключения OpenAI OAuth
и отображения существующих приглашений. Экспортирует commands_router (Router).
"""

import logging
from collections.abc import Sequence

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from backend.app.config import Settings
from backend.app.db.models.family import FamilyInvite
from backend.app.services.family_service import (
    create_invite,
    get_member,
    list_invites,
)
from backend.app.services.openai_auth_service import (
    build_authorize_url,
    generate_pkce_params,
    store_pkce_state_context,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def handle_invite(message: Message, session: AsyncSession) -> None:
    """Обрабатывает команду /invite — генерирует или показывает инвайт-коды.

    Если есть активные инвайты — показывает их.
    Если активных нет — создаёт новый и отправляет код с информацией о сроке.

    Аргументы:
        message: входящее сообщение от пользователя
        session: асинхронная сессия SQLAlchemy

    Побочные эффекты:
        Может создать новый FamilyInvite в БД.
        Отправляет сообщение с кодом приглашения.
    """
    user_id = message.from_user.id if message.from_user else 0
    member = await get_member(session, telegram_user_id=user_id)

    if member is None:
        await message.answer("Вы не зарегистрированы. Используйте /start.")
        return

    existing_invites = await list_invites(session, family_id=member.family_id)
    active_invites = _filter_active_invites(existing_invites)

    if active_invites:
        response = _format_existing_invites(active_invites)
        await message.answer(response)
        return

    new_invite = await create_invite(
        session,
        family_id=member.family_id,
        created_by_id=member.id,
    )
    response = _format_new_invite(new_invite)
    await message.answer(response)


def _filter_active_invites(invites: Sequence[FamilyInvite]) -> list[FamilyInvite]:
    """Отбирает инвайты со статусом 'active'.

    Аргументы:
        invites: список инвайтов (любого статуса)

    Возвращает:
        list: только активные инвайты
    """
    return [invite for invite in invites if invite.status == "active"]


def _format_new_invite(invite: FamilyInvite) -> str:
    """Форматирует сообщение о новом инвайте.

    Аргументы:
        invite: созданный FamilyInvite

    Возвращает:
        str: текст с кодом и информацией о сроке действия
    """
    return (
        f"Код приглашения: {invite.invite_code}\nДействителен до: {invite.expires_at}"
    )


def _format_existing_invites(invites: Sequence[FamilyInvite]) -> str:
    """Форматирует сообщение о существующих активных инвайтах.

    Аргументы:
        invites: список активных инвайтов

    Возвращает:
        str: текст со списком активных кодов
    """
    codes = [invite.invite_code for invite in invites]
    codes_text = "\n".join(f"  {code}" for code in codes)
    return f"Активные приглашения:\n{codes_text}"


async def handle_connectai(message: Message, session: AsyncSession) -> None:
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
    user_id = message.from_user.id if message.from_user else 0
    member = await get_member(session, telegram_user_id=user_id)

    if member is None:
        await message.answer("Вы не зарегистрированы. Используйте /start.")
        return

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
        family_id=member.family_id,
        member_id=member.id,
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
    family_id: int,
    member_id: int,
) -> None:
    """Генерирует PKCE параметры и отправляет OAuth ссылку пользователю.

    Аргументы:
        message: сообщение для ответа
        client_id: гарантированно непустой OPENAI_OAUTH_CLIENT_ID
        redirect_uri: URL обратного вызова
        family_id: ID семьи для последующего OAuth callback
        member_id: Telegram user ID инициатора /connectai

    Побочные эффекты:
        Сохраняет state->code_verifier контекст для callback.
        Отправляет сообщение со ссылкой на авторизацию.
    """
    pkce_params = generate_pkce_params()
    store_pkce_state_context(
        state=pkce_params["state"],
        code_verifier=pkce_params["code_verifier"],
        family_id=family_id,
        member_id=member_id,
    )
    authorize_url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        pkce_params=pkce_params,
    )

    response_text = f"Для подключения OpenAI перейдите по ссылке:\n{authorize_url}"
    await message.answer(response_text)


def create_commands_router() -> Router:
    """Создаёт Router с обработчиками команд.

    Возвращает:
        Router: роутер с handler'ами /invite и /connectai
    """
    router = Router(name="commands")
    router.message.register(handle_invite, Command("invite"))
    router.message.register(handle_connectai, Command("connectai"))
    return router


# Экспортируемый роутер для регистрации в Dispatcher
commands_router = create_commands_router()
