"""
Роутер для обработки текстовых и голосовых сообщений.

Передаёт входящие сообщения в AI-агента (brain) и возвращает
ответ пользователю. Голосовые сообщения предварительно
транскрибируются через Whisper.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import Message
from backend.app.agent.brain import run_agent
from backend.app.agent.whisper import transcribe_voice
from backend.app.services.family_service import get_member
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def handle_text_message(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Обрабатывает текстовое сообщение: передаёт в AI-агент, отправляет ответ.

    Аргументы:
        message: входящее текстовое сообщение от пользователя
        session: асинхронная сессия SQLAlchemy
        bot: экземпляр Telegram бота

    Побочные эффекты:
        Вызывает AI-агента и отправляет ответ пользователю.
    """
    member = await get_member(session, telegram_user_id=message.from_user.id)
    response = await run_agent(
        session,
        family_id=member.family_id,
        user_id=member.id,
        user_message=message.text,
    )
    await message.answer(response)


async def handle_voice_message(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Обрабатывает голосовое сообщение: транскрибирует, передаёт в агент.

    Аргументы:
        message: входящее голосовое сообщение от пользователя
        session: асинхронная сессия SQLAlchemy
        bot: экземпляр Telegram бота

    Побочные эффекты:
        Транскрибирует голос, вызывает AI-агента, отправляет ответ.
    """
    transcribed_text = await transcribe_voice(bot, message.voice.file_id)
    member = await get_member(session, telegram_user_id=message.from_user.id)
    response = await run_agent(
        session,
        family_id=member.family_id,
        user_id=member.id,
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
