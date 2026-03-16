"""
Group membership handlers для workspace-синхронизации.

Обрабатывает:
- my_chat_member: жизненный цикл workspace для бота в группе
- chat_member: ленивую активацию/деактивацию участников workspace
- message(migrate_to_chat_id): миграцию группы в супергруппу
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import ChatMemberUpdated, Message
from backend.app.bot.handlers.constants import (
    GROUP_REJOIN_ADMIN_TEXT,
    GROUP_REJOIN_TEXT,
    GROUP_WELCOME_TEXT,
)
from backend.app.services import workspace_service
from backend.app.services.workspace_service import is_chat_member_active
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
_ADMIN_STATUSES = {"administrator", "creator"}


async def _is_bot_admin(bot: Bot, chat_id: int) -> bool:
    """Проверяет, является ли бот администратором группы.

    Аргументы:
        bot: экземпляр aiogram Bot
        chat_id: ID Telegram-группы

    Возвращает:
        bool: True если бот — администратор или создатель группы.
        При любой ошибке возвращает False (безопасный fallback).
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
        return member.status in _ADMIN_STATUSES
    except Exception:
        logger.warning("Не удалось проверить admin-статус бота в chat_id=%d", chat_id)
        return False


async def _select_greeting(bot: Bot, chat_id: int, is_new: bool) -> str:
    """Выбирает текст приветствия в зависимости от is_new и admin-статуса.

    Аргументы:
        bot: экземпляр aiogram Bot
        chat_id: ID Telegram-группы
        is_new: True если workspace создан впервые

    Возвращает:
        str: текст приветственного сообщения
    """
    if is_new:
        return GROUP_WELCOME_TEXT

    if await _is_bot_admin(bot, chat_id):
        return GROUP_REJOIN_ADMIN_TEXT
    return GROUP_REJOIN_TEXT


async def handle_bot_membership_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Синхронизирует Workspace при изменении статуса бота в группе.

    При добавлении бота: создаёт workspace, регистрирует инициатора
    как участника и отправляет приветствие (первичное или rejoin).
    При удалении бота: деактивирует workspace.

    Аргументы:
        event: событие my_chat_member
        session: асинхронная сессия SQLAlchemy
        bot: экземпляр aiogram Bot (инжектится автоматически)
    """
    if event.chat.type not in _GROUP_CHAT_TYPES:
        return

    chat_id = event.chat.id
    chat_title = event.chat.title or f"chat-{chat_id}"
    was_active = is_chat_member_active(event.old_chat_member)
    now_active = is_chat_member_active(event.new_chat_member)

    if not was_active and now_active:
        workspace, is_new = await workspace_service.get_or_create_workspace(
            session, chat_id, chat_title
        )
        await _register_initiator(session, workspace.id, event)
        greeting_text = await _select_greeting(bot, chat_id, is_new)
        await event.answer(greeting_text)
        logger.info("Workspace активирован по my_chat_member chat_id=%d", chat_id)
        return

    if was_active and not now_active:
        await workspace_service.deactivate_workspace(session, chat_id)
        logger.info("Workspace деактивирован по my_chat_member chat_id=%d", chat_id)


async def _register_initiator(
    session: AsyncSession,
    workspace_id: int,
    event: ChatMemberUpdated,
) -> None:
    """Регистрирует пользователя, добавившего бота, как участника workspace.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID созданного workspace
        event: событие my_chat_member с данными инициатора (from_user)
    """
    user = event.from_user
    await workspace_service.add_or_reactivate_member(
        session=session,
        workspace_id=workspace_id,
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )


async def handle_member_update(
    event: ChatMemberUpdated,
    session: AsyncSession,
) -> None:
    """Синхронизирует WorkspaceMember по событиям вступления/выхода."""
    if event.chat.type not in _GROUP_CHAT_TYPES:
        return

    workspace = await workspace_service.get_workspace_by_chat_id(session, event.chat.id)
    if workspace is None or not workspace.is_active:
        return

    was_active = is_chat_member_active(event.old_chat_member)
    now_active = is_chat_member_active(event.new_chat_member)
    user = event.new_chat_member.user

    if not was_active and now_active:
        await workspace_service.add_or_reactivate_member(
            session=session,
            workspace_id=workspace.id,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
        return

    if was_active and not now_active:
        await workspace_service.deactivate_member(
            session=session,
            workspace_id=workspace.id,
            telegram_user_id=user.id,
        )


async def handle_group_migration(
    message: Message,
    session: AsyncSession,
) -> None:
    """Обновляет telegram_chat_id workspace при миграции группы в супергруппу.

    Аргументы:
        message: сообщение с migrate_to_chat_id
        session: асинхронная сессия SQLAlchemy

    Побочные эффекты:
        Вызывает workspace_service.update_chat_id для атомарного обновления.
    """
    old_chat_id = message.chat.id
    new_chat_id = message.migrate_to_chat_id
    await workspace_service.update_chat_id(session, old_chat_id, new_chat_id)
    logger.info("Миграция группы: chat_id %d → %d", old_chat_id, new_chat_id)


def create_group_events_router() -> Router:
    """Создаёт Router с membership и migration handlers для групповых событий."""
    router = Router(name="group_events")
    router.my_chat_member.register(handle_bot_membership_update)
    router.chat_member.register(handle_member_update)
    router.message.register(handle_group_migration, F.migrate_to_chat_id)
    return router
