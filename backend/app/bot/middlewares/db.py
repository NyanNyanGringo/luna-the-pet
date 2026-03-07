"""
Middleware: инъекция AsyncSession в data хендлера.

Создаёт новую сессию БД для каждого вызова хендлера
и гарантирует её закрытие в finally-блоке.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from backend.app.db.session import async_session_maker

logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Middleware для инъекции AsyncSession в словарь data хендлера.

    При каждом вызове создаёт новую сессию через async_session_maker,
    добавляет её в data["session"], коммитит транзакцию при успехе,
    откатывает при ошибке и закрывает после обработки.

    Побочные эффекты:
        Сессия закрывается в finally — даже при исключении в хендлере.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Оборачивает вызов хендлера: создаёт сессию, передаёт, закрывает.

        Аргументы:
            handler: следующий обработчик в цепочке
            event: входящее событие Telegram
            data: словарь данных хендлера (middleware добавляет ключ 'session')

        Возвращает:
            Any: результат выполнения хендлера

        Ошибки:
            Пробрасывает любое исключение из хендлера после закрытия сессии.
        """
        session = async_session_maker()
        data["session"] = session
        try:
            result = await handler(event, data)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            logger.exception("Транзакция бота откатена из-за ошибки в хендлере")
            raise
        finally:
            await session.close()
            logger.debug("Сессия БД закрыта после обработки события")
