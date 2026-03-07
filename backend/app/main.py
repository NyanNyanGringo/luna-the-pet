"""
Точка входа FastAPI-приложения: lifespan, webhook, health check.

Управляет жизненным циклом бота (set/delete webhook) через lifespan
и принимает обновления от Telegram через POST /webhook.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram.types import Update
from backend.app.api.auth import auth_router
from backend.app.bot.create import bot, dp
from backend.app.config import Settings
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

settings = Settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager: startup и shutdown логика приложения.

    Побочные эффекты:
        Startup: устанавливает webhook для Telegram бота (если настроен WEBHOOK_URL).
        Shutdown: закрывает сессию бота.
    """
    await _setup_webhook()
    yield
    await _shutdown_bot()


async def _setup_webhook() -> None:
    """Устанавливает webhook для Telegram бота.

    Побочные эффекты:
        Вызывает bot.set_webhook() с URL и secret_token из Settings.
        Логирует результат установки.
    """
    if not settings.WEBHOOK_URL:
        logger.warning("WEBHOOK_URL не настроен — webhook не установлен")
        return

    try:
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            secret_token=settings.WEBHOOK_SECRET,
        )
        logger.info("Webhook установлен: %s", settings.WEBHOOK_URL)
    except Exception:
        logger.exception("Не удалось установить webhook")


async def _shutdown_bot() -> None:
    """Закрывает сессию бота при остановке приложения.

    Побочные эффекты:
        Вызывает bot.session.close() для освобождения ресурсов.
    """
    await bot.session.close()
    logger.info("Сессия бота закрыта")


app = FastAPI(title="Luna the Dog", lifespan=lifespan)
app.include_router(auth_router)


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
