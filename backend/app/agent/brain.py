"""
Мозг AI-агента: основной цикл обработки сообщений.

Получает сообщение пользователя, строит system prompt, вызывает OpenAI
Responses API, обрабатывает tool calls в цикле, обновляет ConversationState.
"""

from __future__ import annotations

import datetime
import json
import logging
import re

from backend.app.agent.date_utils import current_date_in_timezone
from backend.app.agent.prompts import build_system_prompt
from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.agent.tools import get_tool_definitions
from backend.app.db.models.family import ConversationState
from backend.app.services import family_service
from backend.app.services.openai_auth_service import get_openai_client
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Максимальное количество ходов до сброса контекста
_MAX_TURN_COUNT = 10


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


async def run_agent(
    session: AsyncSession,
    family_id: int,
    user_id: int,
    user_message: str,
) -> str:
    """Основной цикл AI-агента: обработка сообщения пользователя.

    Загружает или создаёт ConversationState, строит system prompt,
    вызывает OpenAI Responses API, обрабатывает tool calls,
    обновляет состояние диалога.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи
        user_id: Telegram user ID пользователя
        user_message: текст сообщения от пользователя

    Возвращает:
        str: текстовый ответ агента
    """
    state = await _load_or_create_state(session, user_id)
    previous_response_id = _resolve_previous_response_id(state)

    response_language = _detect_response_language(user_message)
    family_today = await _resolve_family_today(session, family_id)
    system_prompt = await build_system_prompt(
        session=session,
        family_id=family_id,
        response_language=response_language,
        family_today=family_today,
    )
    client = await get_ai_client(session, family_id)
    tools = get_tool_definitions()

    response = await _call_openai(
        client, system_prompt, user_message, tools, previous_response_id
    )

    # Цикл обработки tool calls
    response = await _process_tool_calls_loop(
        session,
        client,
        response,
        system_prompt,
        tools,
        user_id,
        family_id,
        response_language,
        family_today,
    )

    answer = _extract_text_response(response)
    _update_state(state, response.id)
    await session.flush()

    return answer


async def _load_or_create_state(
    session: AsyncSession,
    user_id: int,
) -> ConversationState:
    """Загружает существующий ConversationState или создаёт новый.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        user_id: Telegram user ID

    Возвращает:
        ConversationState: состояние диалога пользователя
    """
    result = await session.execute(
        select(ConversationState).where(ConversationState.user_id == user_id)
    )
    state = result.scalar_one_or_none()

    if state is not None:
        return state

    state = ConversationState(user_id=user_id, turn_count=0)
    session.add(state)
    return state


def _resolve_previous_response_id(
    state: ConversationState,
) -> str | None:
    """Определяет previous_response_id с учётом лимита ходов.

    Если turn_count > _MAX_TURN_COUNT, сбрасывает контекст.

    Аргументы:
        state: текущее состояние диалога

    Возвращает:
        str | None: ID предыдущего ответа или None при сбросе
    """
    if state.turn_count > _MAX_TURN_COUNT:
        state.last_response_id = None
        state.turn_count = 0
        return None

    return state.last_response_id


async def _call_openai(
    client: AsyncOpenAI,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    previous_response_id: str | None,
) -> object:
    """Вызывает OpenAI Responses API.

    Аргументы:
        client: настроенный AsyncOpenAI клиент
        system_prompt: системный промпт с контекстом семьи
        user_message: сообщение пользователя
        tools: определения инструментов
        previous_response_id: ID предыдущего ответа для продолжения

    Возвращает:
        Response: ответ от OpenAI API
    """
    return await client.responses.create(
        model="gpt-4.1",
        instructions=system_prompt,
        input=user_message,
        tools=tools,
        previous_response_id=previous_response_id,
    )


async def _process_tool_calls_loop(
    session: AsyncSession,
    client: AsyncOpenAI,
    response: object,
    system_prompt: str,
    tools: list[dict],
    user_id: int,
    family_id: int,
    response_language: str,
    family_today: datetime.date,
) -> object:
    """Обрабатывает tool calls в цикле до получения текстового ответа.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        client: AsyncOpenAI клиент
        response: текущий ответ от OpenAI
        system_prompt: системный промпт
        tools: определения инструментов
        user_id: Telegram user ID
        family_id: ID семьи
        family_today: текущая календарная дата семьи (общая для всего run_agent)

    Возвращает:
        Response: финальный ответ с текстовым сообщением
    """
    while _has_tool_calls(response):
        tool_results = await _execute_tool_calls(
            session=session,
            response=response,
            user_id=user_id,
            family_id=family_id,
            response_language=response_language,
            family_today=family_today,
        )
        response = await _send_tool_results(
            client, response, system_prompt, tools, tool_results
        )

    return response


def _has_tool_calls(response: object) -> bool:
    """Проверяет, содержит ли ответ вызовы инструментов.

    Аргументы:
        response: ответ от OpenAI API

    Возвращает:
        bool: True если есть function_call в output
    """
    return any(
        getattr(item, "type", None) == "function_call" for item in response.output
    )


async def _execute_tool_calls(
    session: AsyncSession,
    response: object,
    user_id: int,
    family_id: int,
    response_language: str,
    family_today: datetime.date,
) -> list[dict]:
    """Выполняет все tool calls из ответа.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        response: ответ с tool calls
        user_id: Telegram user ID
        family_id: ID семьи
        family_today: текущая календарная дата семьи (одна на весь цикл)

    Возвращает:
        list[dict]: результаты выполнения инструментов
    """
    results = []
    for item in response.output:
        if getattr(item, "type", None) != "function_call":
            continue

        arguments = json.loads(item.arguments)
        result = await handle_tool_call(
            session=session,
            tool_name=item.name,
            arguments=arguments,
            user_id=user_id,
            family_id=family_id,
            response_language=response_language,
            family_today=family_today,
        )
        results.append(
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": result,
            }
        )

    return results


async def _send_tool_results(
    client: AsyncOpenAI,
    previous_response: object,
    system_prompt: str,
    tools: list[dict],
    tool_results: list[dict],
) -> object:
    """Отправляет результаты tool calls обратно в OpenAI.

    Аргументы:
        client: AsyncOpenAI клиент
        previous_response: предыдущий ответ с tool calls
        system_prompt: системный промпт
        tools: определения инструментов
        tool_results: результаты выполнения инструментов

    Возвращает:
        Response: новый ответ от OpenAI
    """
    return await client.responses.create(
        model="gpt-4.1",
        instructions=system_prompt,
        input=tool_results,
        tools=tools,
        previous_response_id=previous_response.id,
    )


def _extract_text_response(response: object) -> str:
    """Извлекает текстовый ответ из output модели.

    Аргументы:
        response: ответ от OpenAI API

    Возвращает:
        str: текст ответа или пустая строка
    """
    for item in response.output:
        if getattr(item, "type", None) == "message" and item.content:
            return item.content[0].text
    return ""


def _update_state(
    state: ConversationState,
    response_id: str,
) -> None:
    """Обновляет ConversationState после получения ответа.

    Аргументы:
        state: состояние диалога для обновления
        response_id: ID нового ответа от OpenAI
    """
    state.last_response_id = response_id
    state.turn_count += 1


def _detect_response_language(user_message: str) -> str:
    """Определяет язык ответа по входному сообщению (ru/en, fallback ru)."""
    if re.search(r"[А-Яа-яЁё]", user_message):
        return "ru"
    if re.search(r"[A-Za-z]", user_message):
        return "en"
    return "ru"


async def _resolve_family_today(
    session: AsyncSession,
    family_id: int,
) -> datetime.date:
    """Возвращает текущую календарную дату семьи в её таймзоне."""
    try:
        timezone = await family_service.get_timezone(session, family_id)
    except Exception:
        logger.exception(
            "Не удалось получить таймзону семьи id=%d, fallback UTC",
            family_id,
        )
        timezone = "UTC"
    return current_date_in_timezone(timezone)
