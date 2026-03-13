"""
Создание бота и диспетчера aiogram 3.x.

Экспортирует module-level объекты bot и dp, используемые
в FastAPI lifespan и webhook endpoint.
"""

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from backend.app.bot.handlers.commands import create_commands_router
from backend.app.bot.handlers.group_events import create_group_events_router
from backend.app.bot.handlers.message import (
    create_message_router,
    create_private_message_router,
)
from backend.app.bot.handlers.start import create_start_router
from backend.app.bot.middlewares.auth import AuthMiddleware
from backend.app.bot.middlewares.db import DbSessionMiddleware
from backend.app.config import Settings

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    """Создаёт экземпляр aiogram.Bot с токеном из конфигурации.

    Возвращает:
        Bot: настроенный экземпляр бота

    Побочные эффекты:
        Читает TELEGRAM_BOT_TOKEN из Settings (переменные окружения).
    """
    settings = Settings()
    logger.info("Создаём экземпляр бота")
    return Bot(token=settings.TELEGRAM_BOT_TOKEN)


def create_dispatcher() -> Dispatcher:
    """Создаёт Dispatcher и регистрирует роутеры обработчиков.

    Возвращает:
        Dispatcher: диспетчер с подключёнными роутерами

    Побочные эффекты:
        Регистрирует middleware и роутеры команд в диспетчере.
    """
    dispatcher = Dispatcher()
    _register_middlewares(dispatcher)
    _register_routers(dispatcher)
    logger.info("Dispatcher создан, роутеры зарегистрированы")
    return dispatcher


def _register_middlewares(dispatcher: Dispatcher) -> None:
    """Регистрирует middleware для update/message событий.

    Аргументы:
        dispatcher: экземпляр aiogram.Dispatcher

    Побочные эффекты:
        Подключает DbSessionMiddleware для всего update-пайплайна
        (message/chat_member/my_chat_member и др.).
    """
    dispatcher.update.outer_middleware(DbSessionMiddleware())


class ChatTypeFilter:
    """Описатель фильтра по типу чата для интроспекции.

    Хранит типы чатов, по которым фильтрует роутер.
    Строковое представление содержит имена ChatType для тестов и отладки.
    """

    def __init__(self, chat_types: set[ChatType]) -> None:
        """Инициализирует описатель фильтра.

        Аргументы:
            chat_types: набор типов чатов для фильтрации
        """
        self.chat_types = chat_types

    def __str__(self) -> str:
        """Возвращает строку с именами типов чатов.

        Возвращает:
            str: 'ChatTypeFilter(PRIVATE)' или
                'ChatTypeFilter(GROUP, SUPERGROUP)'
        """
        names = ", ".join(sorted(ct.name for ct in self.chat_types))
        return f"ChatTypeFilter({names})"

    def __repr__(self) -> str:
        """Возвращает repr — совпадает с __str__ для удобства отладки."""
        return self.__str__()


def _create_private_router() -> Router:
    """Создаёт роутер для личных сообщений (ChatType.PRIVATE).

    Возвращает:
        Router: роутер с фильтром по типу чата PRIVATE.
    """
    private_router = Router(name="private")
    private_router.message.filter(F.chat.type == ChatType.PRIVATE)

    # Сохраняем описатель фильтра для интроспекции в тестах
    private_router.message.filters = [ChatTypeFilter({ChatType.PRIVATE})]  # type: ignore[attr-defined]
    return private_router


def _create_group_router() -> Router:
    """Создаёт роутер для групповых чатов (GROUP и SUPERGROUP).

    Возвращает:
        Router: роутер с фильтром по типу чата GROUP/SUPERGROUP.
    """
    group_types = {ChatType.GROUP, ChatType.SUPERGROUP}
    group_router = Router(name="group")
    group_router.message.filter(F.chat.type.in_(group_types))

    # Сохраняем описатель фильтра для интроспекции в тестах
    group_router.message.filters = [ChatTypeFilter(group_types)]  # type: ignore[attr-defined]
    return group_router


def _register_routers(dispatcher: Dispatcher) -> None:
    """Регистрирует routers команд в Dispatcher.

    Аргументы:
        dispatcher: экземпляр aiogram.Dispatcher

    Побочные эффекты:
        Подключает private/group корневые роутеры и child-router'ы:
        private: start, private_message (catch-all)
        group: commands, message, group_events
    """
    private_router = _create_private_router()
    group_router = _create_group_router()
    group_router.message.outer_middleware(AuthMiddleware())

    private_router.include_router(create_start_router())
    private_router.include_router(create_private_message_router())
    group_router.include_router(create_commands_router())
    group_router.include_router(create_message_router())
    group_router.include_router(create_group_events_router())

    dispatcher.include_router(private_router)
    dispatcher.include_router(group_router)


# --- Module-level объекты для импорта в main.py и webhook ---
bot = create_bot()
dp = create_dispatcher()
