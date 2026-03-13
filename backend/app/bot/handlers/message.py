"""
Роутеры для обработки сообщений в group и private чатах.

Group-роутер: передаёт входящие сообщения в AI-агента (brain)
и возвращает ответ пользователю. Голосовые сообщения предварительно
транскрибируются через Whisper.

Private-роутер: catch-all для любых сообщений в личке —
перенаправляет пользователя в группу.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import Message
from backend.app.agent.brain import run_agent
from backend.app.agent.whisper import transcribe_voice
from backend.app.bot.handlers.constants import (
    PRIVATE_MULTI_GROUP_HEADER,
    PRIVATE_ONE_GROUP_TEMPLATE,
    START_PRIVATE_TEXT,
)
from backend.app.db.models.workspace import Workspace, WorkspaceMember
from backend.app.services.workspace_service import (
    get_user_workspaces,
    verify_user_workspaces,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Group message handlers
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_text_message(
    message: Message,
    session: AsyncSession,
    workspace: Workspace,
    member: WorkspaceMember,
) -> None:
    """Обрабатывает текстовое сообщение: передаёт в AI-агент, отправляет ответ.

    Аргументы:
        message: входящее текстовое сообщение от пользователя
        session: асинхронная сессия SQLAlchemy
        workspace: активный workspace из AuthMiddleware
        member: активный участник workspace из AuthMiddleware

    Побочные эффекты:
        Вызывает AI-агента и отправляет ответ пользователю.
    """
    response = await run_agent(
        session,
        workspace_id=workspace.id,
        user_id=member.telegram_user_id,
        user_message=message.text,
    )
    await message.answer(response)


async def handle_voice_message(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    workspace: Workspace,
    member: WorkspaceMember,
) -> None:
    """Обрабатывает голосовое сообщение: транскрибирует, передаёт в агент.

    Аргументы:
        message: входящее голосовое сообщение от пользователя
        session: асинхронная сессия SQLAlchemy
        bot: экземпляр Telegram бота
        workspace: активный workspace из AuthMiddleware
        member: активный участник workspace из AuthMiddleware

    Побочные эффекты:
        Транскрибирует голос, вызывает AI-агента, отправляет ответ.
    """
    transcribed_text = await transcribe_voice(bot, message.voice.file_id)
    response = await run_agent(
        session,
        workspace_id=workspace.id,
        user_id=member.telegram_user_id,
        user_message=transcribed_text,
    )
    await message.answer(response)


def create_message_router() -> Router:
    """Создаёт Router(name='message') с хендлерами для текста и голоса.

    Текстовые сообщения фильтруются: обрабатываются только обычные
    сообщения (не начинающиеся с '/').

    Возвращает:
        Router: роутер с зарегистрированными handler'ами
    """
    router = Router(name="message")
    router.message.register(handle_text_message, F.text, ~F.text.startswith("/"))
    router.message.register(handle_voice_message, F.voice)
    return router


# ═══════════════════════════════════════════════════════════════════════════════
# Private catch-all handler
# ═══════════════════════════════════════════════════════════════════════════════


async def handle_private_catch_all(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Отклоняет любое сообщение в private — перенаправляет в группу.

    Определяет количество workspace'ов пользователя и формирует ответ:
    - 0 групп: инструкция по созданию группы (START_PRIVATE_TEXT)
    - 1 группа: перенаправление в конкретную группу
    - N групп: список всех групп пользователя

    Аргументы:
        message: входящее сообщение (любой тип: текст, голос, фото, стикер)
        session: асинхронная сессия SQLAlchemy
        bot: экземпляр Telegram-бота для верификации членства

    Побочные эффекты:
        Запрашивает workspace'ы пользователя из БД, отправляет ответ.
    """
    user = message.from_user
    telegram_user_id = user.id if user else 0

    workspaces = await get_user_workspaces(session, telegram_user_id)
    verified_workspaces = await verify_user_workspaces(
        bot=bot,
        session=session,
        telegram_user_id=telegram_user_id,
        workspaces=workspaces,
    )
    response_text = _build_private_response(verified_workspaces)
    await message.answer(response_text)


def _build_private_response(workspaces: list[Workspace]) -> str:
    """Формирует текст ответа в зависимости от количества групп.

    Аргументы:
        workspaces: список активных workspace'ов пользователя

    Возвращает:
        str: текст ответа для private-чата
    """
    if len(workspaces) == 0:
        return START_PRIVATE_TEXT

    if len(workspaces) == 1:
        return PRIVATE_ONE_GROUP_TEMPLATE.format(title=workspaces[0].title)

    group_lines = [f"• {workspace.title}" for workspace in workspaces]
    return PRIVATE_MULTI_GROUP_HEADER + "\n".join(group_lines)


def create_private_message_router() -> Router:
    """Создаёт Router(name='private_message') с catch-all для private-чата.

    Ловит все сообщения, не обработанные предыдущими хендлерами
    (после /start и /help). Должен регистрироваться последним
    в private_router.

    Возвращает:
        Router: роутер с catch-all handler'ом
    """
    router = Router(name="private_message")
    router.message.register(handle_private_catch_all)
    return router
