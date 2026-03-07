"""
Мозг AI-агента: получение настроенного OpenAI клиента.

Делегирует создание клиента в openai_auth_service, который реализует
логику OAuth primary -> refresh -> fallback на API key.
"""

import logging

from backend.app.services.openai_auth_service import get_openai_client
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_ai_client(
    session: AsyncSession,
    family_id: int,
) -> AsyncOpenAI:
    """Возвращает настроенный AsyncOpenAI клиент для семьи.

    Делегирует получение клиента в openai_auth_service, который
    выбирает OAuth или API key в зависимости от наличия credentials.

    Аргументы:
        session: AsyncSession для чтения OAuth credentials из БД
        family_id: ID семьи для поиска OAuth credential

    Возвращает:
        AsyncOpenAI: настроенный клиент для запросов к OpenAI API

    Побочные эффекты:
        Может выполнить HTTP-запрос при refresh OAuth токена.
    """
    logger.debug("Получаем AI-клиент для family_id=%d", family_id)
    return await get_openai_client(session, family_id=family_id)
