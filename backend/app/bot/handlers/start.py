"""
Роутер для команд /start и /help — точка входа пользователя в бота.

Обрабатывает private onboarding: объясняет, что бот работает
только в групповых чатах, и показывает инструкцию по добавлению.
Экспортирует фабрику create_start_router() для безопасной
многократной регистрации.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from backend.app.bot.handlers.constants import HELP_PRIVATE_TEXT, START_PRIVATE_TEXT

logger = logging.getLogger(__name__)


async def handle_start(message: Message) -> None:
    """Обрабатывает /start в private-чате — отправляет инструкцию по группе.

    Аргументы:
        message: входящее сообщение от пользователя

    Побочные эффекты:
        Отправляет START_PRIVATE_TEXT с инструкцией по созданию группы.
    """
    user = message.from_user
    user_id = user.id if user else 0
    logger.info("Пользователь %s вызвал /start в private", user_id)
    await message.answer(START_PRIVATE_TEXT)


async def handle_help(message: Message) -> None:
    """Обрабатывает /help в private-чате — список команд + инструкция по группе.

    Аргументы:
        message: входящее сообщение от пользователя

    Побочные эффекты:
        Отправляет HELP_PRIVATE_TEXT со списком команд и инструкцией.
    """
    await message.answer(HELP_PRIVATE_TEXT)


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
