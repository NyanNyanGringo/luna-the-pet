"""
Точка входа FastAPI-приложения: lifespan, webhook, health check.

Управляет жизненным циклом бота через lifespan:
- dev: polling mode (asyncio.create_task + dp.start_polling)
- prod: webhook mode (bot.set_webhook)
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram.types import Update
from backend.app.bot.create import bot, dp
from backend.app.config import Settings
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

settings = Settings()

_polling_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager: startup и shutdown логика приложения.

    Dev: polling mode с DEBUG-логированием.
    Prod: webhook mode с INFO-логированием.
    См. contracts/startup-behavior.md для матрицы поведения.
    """
    _configure_logging()

    if settings.APP_ENV == "dev":
        await _start_polling()
    else:
        await _setup_webhook()

    try:
        yield
    finally:
        try:
            if settings.APP_ENV == "dev":
                await _stop_polling()
        finally:
            await bot.session.close()
            logger.info("Сессия бота закрыта")


def _configure_logging() -> None:
    """Применяет уровень логирования к уже созданным логгерам."""
    level = logging.DEBUG if settings.APP_ENV == "dev" else logging.INFO
    root_logger = logging.getLogger()
    application_logger = logging.getLogger("backend.app")
    _apply_level_to_logger(root_logger, level)
    _apply_level_to_logger(application_logger, level)
    _apply_level_to_logger(logger, level)


def _apply_level_to_logger(target_logger: logging.Logger, level: int) -> None:
    """Обновляет уровень логгера и его handlers."""
    target_logger.setLevel(level)
    for logger_handler in target_logger.handlers:
        logger_handler.setLevel(level)


async def _start_polling() -> None:
    """Запускает polling mode для dev-окружения.

    Удаляет webhook, затем запускает dp.start_polling как фоновую задачу.
    Если WEBHOOK_URL задан в dev — логирует предупреждение.
    """
    global _polling_task

    if settings.WEBHOOK_URL:
        logger.warning(
            "WEBHOOK_URL задан в dev-режиме — игнорируется, используется polling"
        )

    await bot.delete_webhook(drop_pending_updates=True)
    allowed_updates = dp.resolve_used_update_types()
    _polling_task = asyncio.create_task(
        dp.start_polling(
            bot,
            handle_signals=False,
            close_bot_session=False,
            allowed_updates=allowed_updates,
        )
    )
    logger.info("Polling запущен (APP_ENV=dev)")


async def _stop_polling() -> None:
    """Останавливает polling при завершении приложения."""
    global _polling_task

    if _polling_task is None:
        logger.info("Polling не был запущен, остановка не требуется")
        return

    try:
        await dp.stop_polling()
    except RuntimeError as error:
        if not _is_polling_not_started_error(error):
            raise
        logger.info("Polling уже был остановлен до shutdown")

    if _polling_task is not None:
        _polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _polling_task
        _polling_task = None

    logger.info("Polling остановлен")


def _is_polling_not_started_error(error: RuntimeError) -> bool:
    """Проверяет ожидаемый сценарий остановки неинициализированного polling."""
    error_message = str(error).lower()
    return "not started" in error_message or "not running" in error_message


async def _setup_webhook() -> None:
    """Устанавливает webhook для Telegram бота (prod mode).

    Побочные эффекты:
        Вызывает bot.set_webhook() с URL и secret_token из Settings.
    """
    if not settings.WEBHOOK_URL:
        logger.warning("WEBHOOK_URL не настроен — webhook не установлен")
        return

    try:
        allowed_updates = dp.resolve_used_update_types()
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            secret_token=settings.WEBHOOK_SECRET,
            allowed_updates=allowed_updates,
        )
        logger.info("Webhook установлен: %s", settings.WEBHOOK_URL)
    except Exception:
        logger.exception("Не удалось установить webhook")


app = FastAPI(title="Luna the Dog", lifespan=lifespan)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Возвращает:
        dict: {"status": "ok"} при работающем приложении
    """
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request) -> JSONResponse:
    """Принимает обновления от Telegram через webhook.

    Проверяет заголовок X-Telegram-Bot-Api-Secret-Token для верификации
    запроса от Telegram. При несовпадении — отвечает 403.

    Аргументы:
        request: входящий HTTP-запрос от Telegram

    Возвращает:
        JSONResponse: {"ok": true} при успешной обработке, 403 при невалидном secret

    Побочные эффекты:
        Парсит Update и передаёт его в dp.feed_update() для обработки.
    """
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not _is_valid_secret(received_secret):
        logger.warning("Webhook: невалидный secret token")
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    update_data = await request.json()
    telegram_update = Update(**update_data)

    # Telegram ожидает 200 от webhook в любом случае —
    # ошибки обработки update логируются, но не влияют на HTTP-ответ
    try:
        await dp.feed_update(bot, telegram_update)
    except Exception:
        logger.exception(
            "Ошибка при обработке Telegram update %s",
            telegram_update.update_id,
        )

    return JSONResponse(content={"ok": True})


def _is_valid_secret(received_secret: str | None) -> bool:
    """Проверяет совпадение полученного secret с настроенным WEBHOOK_SECRET.

    Аргументы:
        received_secret: значение заголовка X-Telegram-Bot-Api-Secret-Token

    Возвращает:
        bool: True если secret совпадает с настроенным
    """
    if settings.WEBHOOK_SECRET is None:
        return False
    return received_secret == settings.WEBHOOK_SECRET
