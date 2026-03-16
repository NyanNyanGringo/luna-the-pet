"""
Обработчики команд: /help, /invite и другие slash-команды.

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

logger = logging.getLogger(__name__)


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
        Router: роутер с handler'ами /help и /invite
    """
    router = Router(name="commands")
    router.message.register(handle_group_help, Command("help"))
    router.message.register(handle_invite, Command("invite"))
    return router


# Экспортируемый роутер для регистрации в Dispatcher
commands_router = create_commands_router()
