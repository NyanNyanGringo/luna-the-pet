"""
Создание бота и диспетчера aiogram 3.x.

Экспортирует module-level объекты bot и dp, используемые
в FastAPI lifespan и webhook endpoint.
"""

import logging

from aiogram import Bot, Dispatcher
from backend.app.bot.handlers.commands import create_commands_router
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
        и AuthMiddleware для message-событий.
    """
    dispatcher.update.outer_middleware(DbSessionMiddleware())
    dispatcher.message.outer_middleware(AuthMiddleware())


def _register_routers(dispatcher: Dispatcher) -> None:
    """Регистрирует routers команд в Dispatcher.

    Аргументы:
        dispatcher: экземпляр aiogram.Dispatcher

    Побочные эффекты:
        Подключает start и commands routers.
    """
    dispatcher.include_router(create_start_router())
    dispatcher.include_router(create_commands_router())


# --- Module-level объекты для импорта в main.py и webhook ---
bot = create_bot()
dp = create_dispatcher()
