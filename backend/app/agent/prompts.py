"""
Построение system prompt для AI-агента.

Загружает контекст семьи (питомцы, лекарства, таймзона) из БД
и формирует инструкции для модели OpenAI.
"""

from __future__ import annotations

import datetime
import logging

from backend.app.agent.date_utils import current_date_in_timezone
from backend.app.services import family_service, health_service, pet_service
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def build_system_prompt(
    session: AsyncSession,
    family_id: int,
    response_language: str = "ru",
    family_today: datetime.date | None = None,
) -> str:
    """Формирует system prompt для AI-агента с контекстом семьи.

    Загружает питомцев, их активные лекарства и таймзону семьи,
    затем собирает промпт с инструкциями для модели.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи

    Возвращает:
        str: system prompt для OpenAI API
    """
    pets = await pet_service.get_family_pets(session, family_id)
    timezone = await family_service.get_timezone(session, family_id)
    pets_section = await _build_pets_section(session, pets)

    resolved_language = _resolve_response_language(response_language)
    resolved_family_today = family_today or current_date_in_timezone(timezone)

    return _assemble_prompt(
        pets_section=pets_section,
        timezone=timezone,
        response_language=resolved_language,
        family_today=resolved_family_today,
    )


async def _build_pets_section(
    session: AsyncSession,
    pets: list,
) -> str:
    """Формирует раздел промпта с информацией о питомцах и их лекарствах.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pets: список питомцев семьи

    Возвращает:
        str: текстовый блок с описанием питомцев
    """
    if not pets:
        return "У семьи пока нет зарегистрированных питомцев."

    lines = []
    for pet in pets:
        lines.append(f"- {pet.name} (вид: {pet.species})")
        medications = await health_service.get_medications(
            session, pet.id, active_only=True
        )
        for med in medications:
            lines.append(f"  Лекарство: {med.name} (дозировка: {med.dosage})")

    return "\n".join(lines)


def _assemble_prompt(
    pets_section: str,
    timezone: str,
    response_language: str,
    family_today: datetime.date,
) -> str:
    """Собирает финальный system prompt из частей.

    Аргументы:
        pets_section: блок с информацией о питомцах
        timezone: IANA-таймзона семьи

    Возвращает:
        str: готовый system prompt
    """
    if response_language == "en":
        return (
            "You are a family pet care assistant.\n"
            "Respond in English.\n"
            "Use available tools to record pet-related data.\n"
            "\n"
            "IMPORTANT: when calling tools, only pass fields that the user "
            "explicitly mentioned. Do not ask about or fill in fields "
            "the user did not bring up.\n"
            "\n"
            f"Family timezone: {timezone}\n"
            f"Current family date: {family_today.isoformat()}\n"
            "\n"
            "Family pets:\n"
            f"{pets_section}\n"
        )

    return (
        "Ты — ассистент по уходу за домашними животными семьи.\n"
        "Отвечай на русском языке. Будь дружелюбным и полезным.\n"
        "Используй доступные инструменты для записи данных о питомцах.\n"
        "\n"
        "ВАЖНО: при вызове инструментов передавай ТОЛЬКО те поля, которые "
        "пользователь явно упомянул. Не запрашивай и не заполняй поля, "
        "о которых пользователь не говорил.\n"
        "\n"
        f"Таймзона семьи: {timezone}\n"
        f"Текущая дата семьи: {family_today.isoformat()}\n"
        "\n"
        "Питомцы семьи:\n"
        f"{pets_section}\n"
    )


def _resolve_response_language(response_language: str) -> str:
    """Нормализует язык ответа до поддерживаемых значений ru/en."""
    if response_language in {"ru", "en"}:
        return response_language
    return "ru"
