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
from backend.app.config import Settings
from backend.app.db.models.family import ConversationState
from backend.app.services import workspace_service
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Максимальное количество ходов до сброса контекста
_MAX_TURN_COUNT = 10


def get_ai_client() -> AsyncOpenAI:
    """Возвращает настроенный AsyncOpenAI клиент через API-ключ."""
    settings = Settings()
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def run_agent(
    session: AsyncSession,
    workspace_id: int,
    user_id: int,
    user_message: str,
) -> str:
    """Основной цикл AI-агента: обработка сообщения пользователя.

    Загружает или создаёт ConversationState, строит system prompt,
    вызывает OpenAI Responses API, обрабатывает tool calls,
    обновляет состояние диалога.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        user_id: Telegram user ID пользователя
        user_message: текст сообщения от пользователя

    Возвращает:
        str: текстовый ответ агента
    """
    state = await _load_or_create_state(session, user_id, workspace_id)
    previous_response_id = _resolve_previous_response_id(state)

    response_language = _detect_response_language(user_message)
    workspace_today = await _resolve_workspace_today(session, workspace_id)
    system_prompt = await build_system_prompt(
        session=session,
        workspace_id=workspace_id,
        response_language=response_language,
        workspace_today=workspace_today,
    )
    client = get_ai_client()
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
        workspace_id,
        response_language,
        workspace_today,
    )

    answer = _extract_text_response(response)
    _update_state(state, response.id)
    await session.flush()

    return answer


async def _load_or_create_state(
    session: AsyncSession,
    user_id: int,
    workspace_id: int,
) -> ConversationState:
    """Загружает существующий ConversationState или создаёт новый.

    Использует savepoint для защиты от race condition: два параллельных
    первых сообщения одного пользователя могут оба пройти SELECT → None,
    но только один INSERT выиграет UNIQUE(telegram_user_id, workspace_id).
    Проигравший ловит IntegrityError и делает повторный SELECT.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        user_id: Telegram user ID
        workspace_id: ID workspace

    Возвращает:
        ConversationState: состояние диалога пользователя
    """
    state = await _find_conversation_state(session, user_id, workspace_id)
    if state is not None:
        return state

    try:
        async with session.begin_nested():
            state = ConversationState(
                telegram_user_id=user_id,
                workspace_id=workspace_id,
                turn_count=0,
            )
            session.add(state)
            await session.flush()
        return state
    except IntegrityError as concurrent_error:
        logger.info(
            "Конкурентное создание ConversationState user_id=%d workspace_id=%d",
            user_id,
            workspace_id,
        )
        state = await _find_conversation_state(session, user_id, workspace_id)
        if state is None:
            raise RuntimeError(
                f"ConversationState не найден после IntegrityError: "
                f"user_id={user_id}, workspace_id={workspace_id}"
            ) from concurrent_error
        return state


async def _find_conversation_state(
    session: AsyncSession,
    user_id: int,
    workspace_id: int,
) -> ConversationState | None:
    """Ищет ConversationState по паре (user_id, workspace_id).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        user_id: Telegram user ID
        workspace_id: ID workspace

    Возвращает:
        ConversationState | None: найденное состояние или None
    """
    result = await session.execute(
        select(ConversationState).where(
            ConversationState.telegram_user_id == user_id,
            ConversationState.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


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
        system_prompt: системный промпт с контекстом workspace
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
    workspace_id: int,
    response_language: str,
    workspace_today: datetime.date,
) -> object:
    """Обрабатывает tool calls в цикле до получения текстового ответа.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        client: AsyncOpenAI клиент
        response: текущий ответ от OpenAI
        system_prompt: системный промпт
        tools: определения инструментов
        user_id: Telegram user ID
        workspace_id: ID workspace
        workspace_today: текущая календарная дата workspace (общая для всего run_agent)

    Возвращает:
        Response: финальный ответ с текстовым сообщением
    """
    while _has_tool_calls(response):
        tool_results = await _execute_tool_calls(
            session=session,
            response=response,
            user_id=user_id,
            workspace_id=workspace_id,
            response_language=response_language,
            workspace_today=workspace_today,
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
    workspace_id: int,
    response_language: str,
    workspace_today: datetime.date,
) -> list[dict]:
    """Выполняет все tool calls из ответа.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        response: ответ с tool calls
        user_id: Telegram user ID
        workspace_id: ID workspace
        workspace_today: текущая календарная дата workspace (одна на весь цикл)

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
            workspace_id=workspace_id,
            response_language=response_language,
            workspace_today=workspace_today,
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


async def _resolve_workspace_today(
    session: AsyncSession,
    workspace_id: int,
) -> datetime.date:
    """Возвращает текущую календарную дату workspace в его таймзоне."""
    try:
        timezone = await workspace_service.get_timezone(session, workspace_id)
    except Exception:
        logger.exception(
            "Не удалось получить таймзону workspace id=%d, fallback UTC",
            workspace_id,
        )
        timezone = "UTC"
    return current_date_in_timezone(timezone)
