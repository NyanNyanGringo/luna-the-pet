"""
Middleware: проверка авторизации FamilyMember.

Пропускает команды из whitelist (например, /start) без проверки.
Для остальных сообщений — ищет пользователя в БД и проверяет is_authorized.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from backend.app.db.models.family import FamilyMember
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Команды, которые разрешены без проверки авторизации
WHITELIST_COMMANDS = frozenset({"/start", "/help"})


class AuthMiddleware(BaseMiddleware):
    """Middleware проверки авторизации пользователя по FamilyMember.is_authorized.

    Команды из WHITELIST_COMMANDS (/start, /help) проходят без проверки.
    Если пользователь не найден в БД или is_authorized=False — хендлер не вызывается,
    пользователь получает сообщение об отказе.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Проверяет авторизацию перед передачей в хендлер.

        Аргументы:
            handler: следующий обработчик в цепочке
            event: входящее событие Telegram
            data: словарь данных хендлера
                (ожидается ключ 'session' от DbSessionMiddleware)

        Возвращает:
            Any: результат хендлера (если авторизация пройдена) или None

        Побочные эффекты:
            Отправляет сообщение об отказе неавторизованным пользователям.
        """
        if _is_whitelisted_command(event):
            return await handler(event, data)

        member = await _lookup_member(event, data)

        if member is None or not member.is_authorized:
            await _send_rejection(event)
            return None

        return await handler(event, data)


def _is_whitelisted_command(event: TelegramObject) -> bool:
    """Проверяет, является ли событие командой из whitelist.

    Аргументы:
        event: входящее событие Telegram

    Возвращает:
        bool: True если команда в whitelist (/start, /help), включая deep link
    """
    text = getattr(event, "text", None)
    if text is None:
        return False

    # Извлекаем саму команду (без аргументов, например "/start invite_abc" -> "/start")
    command = text.split()[0] if text else ""
    return command in WHITELIST_COMMANDS


async def _lookup_member(
    event: TelegramObject,
    data: dict[str, Any],
) -> FamilyMember | None:
    """Ищет FamilyMember в БД по Telegram user ID из события.

    Аргументы:
        event: событие Telegram с from_user.id
        data: словарь данных с ключом 'session'

    Возвращает:
        FamilyMember | None: найденный участник или None
    """
    from_user = getattr(event, "from_user", None)
    if from_user is None:
        logger.warning("Событие без from_user — отклоняем")
        return None

    session = data["session"]
    telegram_user_id = from_user.id

    query = select(FamilyMember).where(FamilyMember.id == telegram_user_id)
    result = await session.execute(query)
    return cast(FamilyMember | None, result.scalar_one_or_none())


async def _send_rejection(event: TelegramObject) -> None:
    """Отправляет пользователю сообщение об отказе в доступе.

    Аргументы:
        event: событие Telegram (должно поддерживать метод answer)

    Побочные эффекты:
        Вызывает event.answer() с текстом отказа.
        Если event не поддерживает answer — молча пропускает.
    """
    answer_method = getattr(event, "answer", None)
    if answer_method is None or not callable(answer_method):
        return

    # Проверяем, что answer — корутинная функция (async)
    if not inspect.iscoroutinefunction(answer_method):
        logger.debug("event.answer не является async-методом, пропускаем")
        return

    await answer_method("Доступ запрещён. Обратитесь к администратору семьи.")
    logger.info("Доступ запрещён для пользователя")
