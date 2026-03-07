"""
Роутер для команд /start и /help — точка входа пользователя в бота.

Обрабатывает первое сообщение пользователя, deep link приглашения
и команду справки. Экспортирует фабрику create_start_router()
для безопасной многократной регистрации.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from backend.app.services.family_service import (
    get_member,
    get_or_create_family,
    register_member,
    use_invite,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Текст справки со списком доступных команд
_HELP_TEXT = (
    "Доступные команды:\n"
    "/start — начать работу с ботом\n"
    "/help — показать список команд\n"
    "/invite — создать приглашение в семью"
)


async def handle_start(message: Message, session: AsyncSession) -> None:
    """Обрабатывает команду /start: регистрация, deep link, приветствие.

    Новый пользователь: создаёт Family (если нет), регистрирует участника.
    Существующий: только приветствие.
    Deep link (/start <invite_code>): принимает инвайт в обоих случаях.

    Аргументы:
        message: входящее сообщение от пользователя
        session: асинхронная сессия SQLAlchemy

    Побочные эффекты:
        Создаёт Family/FamilyMember при необходимости.
        Использует инвайт при наличии deep link.
        Отправляет приветственное сообщение.
    """
    user = message.from_user
    user_name = user.first_name if user else "друг"
    user_id = user.id if user else 0
    username = user.username if user else None

    logger.info("Пользователь %s вызвал /start", user_id)

    invite_code = _extract_deep_link_code(message.text)
    family = await get_or_create_family(session)
    existing_member = await get_member(session, telegram_user_id=user_id)

    if existing_member is None:
        await register_member(
            session,
            telegram_user_id=user_id,
            first_name=user_name,
            username=username,
            family_id=family.id,
        )

    if invite_code:
        await use_invite(session, invite_code=invite_code, user_id=user_id)

    greeting = f"Привет, {user_name}! Я Luna — твой помощник по уходу за питомцами."
    await message.answer(greeting)


def _extract_deep_link_code(text: str | None) -> str | None:
    """Извлекает invite code из deep link текста '/start <code>'.

    Аргументы:
        text: текст сообщения (может быть None)

    Возвращает:
        str | None: код приглашения или None если deep link отсутствует
    """
    if not text:
        return None

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None

    return parts[1]


async def handle_help(message: Message) -> None:
    """Обрабатывает команду /help — отправляет список доступных команд.

    Аргументы:
        message: входящее сообщение от пользователя

    Побочные эффекты:
        Отправляет сообщение со списком команд.
    """
    await message.answer(_HELP_TEXT)


def create_start_router() -> Router:
    """Создаёт новый экземпляр Router с обработчиками /start и /help.

    Возвращает:
        Router: роутер с зарегистрированными handler'ами

    Примечание:
        Каждый вызов создаёт новый Router, чтобы избежать ошибки
        повторного прикрепления к разным Dispatcher.
    """
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    router.message.register(handle_help, Command("help"))
    return router
