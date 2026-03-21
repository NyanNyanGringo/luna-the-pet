"""
Построение system prompt для AI-агента.

Загружает контекст workspace (питомцы, лекарства, таймзона) из БД
и формирует инструкции для модели OpenAI.
"""

from __future__ import annotations

import datetime
import logging

from backend.app.agent.date_utils import current_date_in_timezone
from backend.app.services import health_service, pet_service, workspace_service
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def build_system_prompt(
    session: AsyncSession,
    workspace_id: int,
    response_language: str = "ru",
    workspace_today: datetime.date | None = None,
) -> str:
    """Формирует system prompt для AI-агента с контекстом workspace.

    Загружает питомцев, их активные лекарства и таймзону workspace,
    затем собирает промпт с инструкциями для модели.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace

    Возвращает:
        str: system prompt для OpenAI API
    """
    pets = await pet_service.get_workspace_pets(session, workspace_id)
    timezone = await workspace_service.get_timezone(session, workspace_id)
    resolved_language = _resolve_response_language(response_language)
    resolved_workspace_today = workspace_today or current_date_in_timezone(timezone)
    pets_section = await _build_pets_section(
        session, pets, resolved_workspace_today, resolved_language
    )

    return _assemble_prompt(
        pets_section=pets_section,
        timezone=timezone,
        response_language=resolved_language,
        workspace_today=resolved_workspace_today,
    )


async def _build_pets_section(
    session: AsyncSession,
    pets: list,
    workspace_today: datetime.date | None = None,
    response_language: str = "ru",
) -> str:
    """Формирует раздел промпта с информацией о питомцах и их лекарствах.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pets: список питомцев workspace
        workspace_today: текущая дата workspace для фильтрации
            активных лекарств (если None — UTC fallback в сервисе)
        response_language: язык ответа (ru/en)

    Возвращает:
        str: текстовый блок с описанием питомцев
    """
    if not pets:
        if response_language == "en":
            return "No registered pets in workspace yet."
        return "В workspace пока нет зарегистрированных питомцев."

    lines = []
    for pet in pets:
        if response_language == "en":
            lines.append(f"- {pet.name} (species: {pet.species})")
        else:
            lines.append(f"- {pet.name} (вид: {pet.species})")
        medications = await health_service.get_medications(
            session, pet.id, active_only=True, today=workspace_today
        )
        for med in medications:
            if response_language == "en":
                lines.append(f"  Medication: {med.name} (dosage: {med.dosage})")
            else:
                lines.append(f"  Лекарство: {med.name} (дозировка: {med.dosage})")

    return "\n".join(lines)


def _assemble_prompt(
    pets_section: str,
    timezone: str,
    response_language: str,
    workspace_today: datetime.date,
) -> str:
    """Собирает финальный system prompt из частей.

    Аргументы:
        pets_section: блок с информацией о питомцах
        timezone: IANA-таймзона workspace

    Возвращает:
        str: готовый system prompt
    """
    if response_language == "en":
        return f"""\
[ROLE]
You are a workspace pet care assistant.
Respond in English. Be friendly and helpful.

[WORKSPACE INFO]
Workspace timezone: {timezone}
Current workspace date: {workspace_today.isoformat()}
Workspace pets:
{pets_section}

[INSTRUCTIONS]
- Use available tools to record and read pet-related data.
  Save new information, answer questions, show history.
- Always check the required field in tool descriptions —
  it defines the minimum set of properties for each tool.

[CAPABILITIES]
- Accept text and respond to user messages
- Accept voice messages
- Read and write to the database via available tools

[LIMITATIONS]
- Cannot process photos or videos
- Cannot send reminders

[IMPORTANT]
When calling tools, only pass fields that the user
explicitly mentioned. Do not fill in fields
the user did not bring up.

"""

    return f"""\
[РОЛЬ]
Ты — ассистент по уходу за домашними животными workspace.
Отвечай на русском языке. Будь дружелюбным и полезным.

[ИНФОРМАЦИЯ ПО ТЕКУЩЕМУ WORKSPACE]
Таймзона workspace: {timezone}
Текущая дата workspace: {workspace_today.isoformat()}
Питомцы workspace:
{pets_section}

[ИНСТРУКЦИИ]
- Используй инструменты для записи и чтения данных
  о питомцах. Записывай информацию, отвечай на вопросы,
  показывай историю.
- В описании инструментов обращай внимание на поле
  required — это минимальный набор properties
  для вызова инструмента.

[ЧТО ТЫ УМЕЕШЬ]
- Принимать текст и отвечать на сообщения от пользователя
- Принимать голосовые сообщения
- Записывать и читать базу данных через доступные команды/инструменты

[ЧТО ТЫ НЕ УМЕЕШЬ]
- Обрабатывать фото и видео
- Присылать напоминания

[ВАЖНО]
При вызове инструментов передавай ТОЛЬКО те поля,
которые пользователь явно упомянул.
Не заполняй поля, о которых пользователь не говорил.

"""


def _resolve_response_language(response_language: str) -> str:
    """Нормализует язык ответа до поддерживаемых значений ru/en."""
    if response_language in {"ru", "en"}:
        return response_language
    return "ru"
