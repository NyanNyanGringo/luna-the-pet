"""
Маршрутизация и выполнение вызовов инструментов AI-агента.

Принимает tool_name и аргументы от OpenAI function calling,
вызывает соответствующий сервис и возвращает строку-подтверждение.
"""

from __future__ import annotations

import datetime
import inspect
import logging
import zoneinfo
from decimal import Decimal

from backend.app.agent.date_utils import InvalidRuntimeDateError, parse_runtime_date
from backend.app.agent.i18n import get_message
from backend.app.db.models.pet import Pet
from backend.app.services import (
    health_service,
    nutrition_service,
    pet_service,
    workspace_service,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_MEASUREMENT_UNIT_MAP = {
    "temperature": "C",
    "pulse": "bpm",
    "respiration": "rpm",
}

_MEASUREMENT_DISPLAY_UNIT_MAP: dict[str, dict[str, str]] = {
    "ru": {
        "temperature": "°C",
        "pulse": "уд/мин",
        "respiration": "вд/мин",
    },
    "en": {
        "temperature": "°C",
        "pulse": "bpm",
        "respiration": "rpm",
    },
}


def _get_display_unit(measurement_type: str, response_language: str) -> str:
    """Возвращает отображаемую единицу измерения по языку."""
    lang_map = _MEASUREMENT_DISPLAY_UNIT_MAP.get(
        response_language, _MEASUREMENT_DISPLAY_UNIT_MAP["ru"]
    )
    return lang_map.get(measurement_type, measurement_type)


_PET_UPDATE_FIELD_WHITELIST = {
    "breed",
    "birth_date",
    "gender",
    "is_neutered",
    "origin_story",
    "chip_number",
}
_EMERGENCY_UPDATE_FIELD_WHITELIST = {
    "allergies",
    "chronic_conditions",
    "vet_contact",
    "blood_type",
    "rabies_vaccination_date",
    "latest_weight_snapshot",
}


async def handle_tool_call(
    session: AsyncSession,
    tool_name: str,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_today: datetime.date | None = None,
) -> str:
    """Маршрутизирует вызов инструмента к соответствующему сервису.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        tool_name: имя инструмента (например, "add_weight")
        arguments: словарь аргументов от OpenAI
        user_id: Telegram user ID вызывающего
        workspace_id: ID workspace
        workspace_today: текущая дата workspace (предвычисленная в brain.run_agent)

    Возвращает:
        str: строка-подтверждение или сообщение об ошибке
    """
    resolved_language = _resolve_response_language(response_language)
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return get_message("unknown_tool", language=resolved_language)

    try:
        workspace_timezone = await _resolve_workspace_timezone(session, workspace_id)
        async with session.begin_nested():
            return await handler(
                session=session,
                arguments=arguments,
                user_id=user_id,
                workspace_id=workspace_id,
                response_language=resolved_language,
                workspace_timezone=workspace_timezone,
                workspace_today=workspace_today,
            )
    except InvalidRuntimeDateError as error:
        logger.exception("Ошибка парсинга даты в инструменте '%s'", tool_name)
        return get_message(
            "error_occurred",
            language=resolved_language,
            error=str(error),
        )
    except Exception as error:
        logger.exception("Ошибка при выполнении инструмента '%s'", tool_name)
        return get_message(
            "error_occurred",
            language=resolved_language,
            error=str(error),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Обработчики отдельных инструментов
# ═══════════════════════════════════════════════════════════════════════════════


async def _handle_add_weight(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает вес питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    measured_at = _parse_date_field(
        arguments["measured_at"],
        field_name="measured_at",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    record = await health_service.add_weight(
        session=session,
        pet_id=pet.id,
        weight_kg=Decimal(str(arguments["weight_kg"])),
        measured_at=measured_at,
        recorded_by=user_id,
    )
    return get_message(
        "weight_saved",
        language=response_language,
        weight=record.weight_kg,
        pet_name=pet.name,
    )


async def _handle_add_vaccination(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает вакцинацию питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    vaccination_date = _parse_date_field(
        arguments["date"],
        field_name="date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры для расширенной записи вакцинации
    kwargs: dict = {}
    if "next_date" in arguments:
        kwargs["next_date"] = _parse_date_field(
            arguments["next_date"],
            field_name="next_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "vet_name" in arguments:
        kwargs["vet_name"] = arguments["vet_name"]
    if "batch_number" in arguments:
        kwargs["batch_number"] = arguments["batch_number"]
    if "notes" in arguments:
        kwargs["notes"] = arguments["notes"]
    record = await health_service.add_vaccination(
        session=session,
        pet_id=pet.id,
        vaccine_name=arguments["vaccine_name"],
        date=vaccination_date,
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "vaccination_saved",
        language=response_language,
        vaccine_name=record.vaccine_name,
        date=record.date,
    )


async def _handle_add_medication(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Добавляет лекарство для питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    medication_start_date = _parse_date_field(
        arguments["start_date"],
        field_name="start_date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры для расширенной записи лекарства
    kwargs: dict = {}
    if "frequency" in arguments:
        kwargs["frequency"] = arguments["frequency"]
    if "end_date" in arguments:
        kwargs["end_date"] = _parse_date_field(
            arguments["end_date"],
            field_name="end_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "last_given_date" in arguments:
        kwargs["last_given_date"] = _parse_date_field(
            arguments["last_given_date"],
            field_name="last_given_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "notes" in arguments:
        kwargs["notes"] = arguments["notes"]
    record = await health_service.add_medication(
        session=session,
        pet_id=pet.id,
        name=arguments["name"],
        start_date=medication_start_date,
        today=workspace_today,
        dosage=arguments.get("dosage"),
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "medication_saved",
        language=response_language,
        name=record.name,
        start_date=record.start_date,
    )


async def _handle_add_note(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Добавляет заметку о питомце."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    record = await health_service.add_note(
        session=session,
        pet_id=pet.id,
        content=arguments["content"],
        recorded_by=user_id,
    )
    return get_message(
        "note_saved",
        language=response_language,
        preview=record.content[:50],
    )


async def _handle_add_diet(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Добавляет запись о диете питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    diet_start_date = _parse_date_field(
        arguments["start_date"],
        field_name="start_date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры для расширенной записи диеты
    kwargs: dict = {}
    if "food_type" in arguments:
        kwargs["food_type"] = arguments["food_type"]
    if "end_date" in arguments:
        kwargs["end_date"] = _parse_date_field(
            arguments["end_date"],
            field_name="end_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "notes" in arguments:
        kwargs["notes"] = arguments["notes"]
    record = await nutrition_service.add_diet_record(
        session=session,
        pet_id=pet.id,
        food_brand=arguments["food_brand"],
        start_date=diet_start_date,
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "diet_saved",
        language=response_language,
        food_brand=record.food_brand,
        start_date=record.start_date,
    )


async def _handle_add_feeding(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает факт кормления питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    fed_at = _parse_offset_aware_datetime(
        raw_value=arguments["fed_at"],
        field_name="fed_at",
    )
    # Опциональный параметр portion_size
    kwargs: dict = {}
    if "portion_size" in arguments:
        kwargs["portion_size"] = arguments["portion_size"]
    record = await nutrition_service.add_feeding_entry(
        session=session,
        pet_id=pet.id,
        fed_at=fed_at,
        food_description=arguments["food_description"],
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "feeding_saved",
        language=response_language,
        food_description=record.food_description,
    )


async def _handle_get_pet_profile(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает профиль питомца в текстовом виде."""
    pet = await pet_service.get_pet_by_name(
        session, workspace_id, arguments["pet_name"]
    )
    if pet is None:
        raise ValueError(f"Питомец '{arguments['pet_name']}' не найден")

    return _format_pet_profile(pet, response_language)


async def _handle_update_pet(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Обновляет профиль питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    update_fields = _extract_update_fields(arguments)
    normalized_update_fields = _normalize_pet_update_fields(
        fields=update_fields,
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    updated_pet = await pet_service.update_pet(
        session,
        pet.id,
        actor_id=user_id,
        **normalized_update_fields,
    )
    return get_message(
        "pet_updated",
        language=response_language,
        pet_name=updated_pet.name,
    )


async def _handle_create_pet(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Создаёт нового питомца."""
    pet = await pet_service.create_pet(
        session=session,
        workspace_id=workspace_id,
        name=arguments["name"],
        species=arguments["species"],
        actor_id=user_id,
        breed=arguments.get("breed"),
    )
    return get_message(
        "pet_created",
        language=response_language,
        pet_name=pet.name,
    )


async def _handle_update_emergency_profile(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Обновляет экстренный профиль питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    update_fields = _extract_emergency_fields(arguments)
    normalized_update_fields = _normalize_emergency_update_fields(
        fields=update_fields,
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    await health_service.update_emergency_profile(
        session,
        pet.id,
        actor_id=user_id,
        **normalized_update_fields,
    )
    return get_message("emergency_profile_updated", language=response_language)


async def _handle_get_emergency_profile(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает экстренный профиль питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    profile = await health_service.get_or_create_emergency_profile(
        session,
        pet.id,
        actor_id=user_id,
    )
    return _format_emergency_profile(profile, response_language)


async def _handle_add_medical_record(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Создаёт медицинскую запись для питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    record_date = _parse_date_field(
        arguments["date"],
        field_name="date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры
    kwargs: dict = {}
    if "description" in arguments:
        kwargs["description"] = arguments["description"]
    if "resolved_date" in arguments:
        kwargs["resolved_date"] = _parse_date_field(
            arguments["resolved_date"],
            field_name="resolved_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "vet_name" in arguments:
        kwargs["vet_name"] = arguments["vet_name"]
    record = await health_service.add_medical_record(
        session=session,
        pet_id=pet.id,
        record_type=arguments["record_type"],
        title=arguments["title"],
        date=record_date,
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "medical_record_saved",
        language=response_language,
        title=record.title,
        record_type=record.record_type,
        date=record.date,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Обработчики read-инструментов
# ═══════════════════════════════════════════════════════════════════════════════


async def _handle_get_weight_history(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает историю веса питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    limit = arguments.get("limit", 10)
    records = await health_service.get_weight_history(
        session=session,
        pet_id=pet.id,
        limit=limit,
    )
    if not records:
        return get_message("no_weight_records", language=response_language)
    lines = []
    kg = _l("label_kg", response_language)
    for record in records:
        lines.append(f"• {record.measured_at} — {record.weight_kg} {kg}")
    return "\n".join(lines)


async def _handle_get_vaccinations(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает список вакцинаций питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    records = await health_service.get_vaccinations(
        session=session,
        pet_id=pet.id,
    )
    if not records:
        return get_message("no_vaccinations", language=response_language)
    lines = []
    for record in records:
        line = f"• {record.vaccine_name} ({record.date})"
        if getattr(record, "next_date", None) is not None:
            line += f", {_l('label_next_date', response_language)}: {record.next_date}"
        if getattr(record, "vet_name", None) is not None:
            line += f", {_l('label_vet_name', response_language)}: {record.vet_name}"
        if getattr(record, "batch_number", None) is not None:
            batch_lbl = _l("label_batch_number", response_language)
            line += f", {batch_lbl}: {record.batch_number}"
        if getattr(record, "notes", None) is not None:
            line += f", {_l('label_notes', response_language)}: {record.notes}"
        lines.append(line)
    return "\n".join(lines)


async def _handle_get_medications(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает список лекарств питомца.

    При active_only=False группирует лекарства по секциям:
    активные и завершённые. При active_only=True — плоский список.
    """
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    active_only = arguments.get("active_only", False)
    records = await health_service.get_medications(
        session=session,
        pet_id=pet.id,
        active_only=active_only,
        today=workspace_today,
    )
    if not records:
        return get_message("no_medications", language=response_language)

    if active_only:
        return _format_medications_flat(records, response_language)
    return _format_medications_grouped(
        records,
        response_language,
        workspace_today=workspace_today,
    )


def _format_medication_line(
    record: object,
    response_language: str,
) -> str:
    """Форматирует одну строку лекарства для вывода."""
    line = f"• {record.name}"  # type: ignore[union-attr]
    if getattr(record, "dosage", None) is not None:
        line += (
            f", {_l('label_dosage', response_language)}"
            f": {record.dosage}"  # type: ignore[union-attr]
        )
    if getattr(record, "frequency", None) is not None:
        line += (
            f", {_l('label_frequency', response_language)}"
            f": {record.frequency}"  # type: ignore[union-attr]
        )
    if getattr(record, "start_date", None) is not None:
        line += (
            f", {_l('label_start_date', response_language)}"
            f": {record.start_date}"  # type: ignore[union-attr]
        )
    if getattr(record, "end_date", None) is not None:
        line += (
            f", {_l('label_end_date', response_language)}"
            f": {record.end_date}"  # type: ignore[union-attr]
        )
    return line


def _format_medications_flat(
    records: list,
    response_language: str,
) -> str:
    """Плоский список лекарств (для active_only=True)."""
    lines = [_format_medication_line(r, response_language) for r in records]
    return "\n".join(lines)


def _format_medications_grouped(
    records: list,
    response_language: str,
    workspace_today: datetime.date | None = None,
) -> str:
    """Группирует лекарства на активные/завершённые секции.

    «Эффективно активным» считается препарат, у которого is_active=True
    И (end_date IS NULL ИЛИ end_date >= effective_today).
    """
    effective_today = workspace_today or datetime.datetime.now(tz=datetime.UTC).date()
    active = [
        r
        for r in records
        if getattr(r, "is_active", False)
        and (
            getattr(r, "end_date", None) is None
            or getattr(r, "end_date", None) >= effective_today
        )
    ]
    completed = [r for r in records if r not in active]

    lines: list[str] = []
    active_header = _l("medications_section_active", response_language)
    lines.append(active_header)
    if active:
        for record in active:
            lines.append(_format_medication_line(record, response_language))
    else:
        lines.append(_l("medications_section_empty", response_language))

    completed_header = _l("medications_section_completed", response_language)
    lines.append(completed_header)
    if completed:
        for record in completed:
            lines.append(_format_medication_line(record, response_language))
    else:
        lines.append(_l("medications_section_empty", response_language))

    return "\n".join(lines)


async def _handle_get_notes(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает заметки о питомце."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    limit = arguments.get("limit", 10)
    records = await health_service.get_notes(
        session=session,
        pet_id=pet.id,
        limit=limit,
    )
    if not records:
        return get_message("no_notes", language=response_language)
    lines = []
    for record in records:
        date_str = getattr(record, "created_at", "")
        lines.append(f"• {date_str}: {record.content[:100]}")
    return "\n".join(lines)


async def _handle_get_feeding_history(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает историю кормлений питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    tz = zoneinfo.ZoneInfo(workspace_timezone)
    today = workspace_today or datetime.datetime.now(tz=datetime.UTC).date()

    # Парсим опциональные даты периода
    raw_start = arguments.get("start_date")
    raw_end = arguments.get("end_date")
    parsed_start = (
        _parse_date_field(
            raw_start,
            field_name="start_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
        if raw_start is not None
        else None
    )
    parsed_end = (
        _parse_date_field(
            raw_end,
            field_name="end_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
        if raw_end is not None
        else None
    )

    # Вычисляем since_dt / until_dt
    if parsed_start is not None:
        since_date = parsed_start
    elif parsed_end is not None:
        since_date = parsed_end - datetime.timedelta(days=6)
    else:
        since_date = today - datetime.timedelta(days=6)

    since_dt = datetime.datetime.combine(
        since_date,
        datetime.time.min,
        tzinfo=tz,
    )
    until_dt = None
    if parsed_end is not None:
        until_dt = datetime.datetime.combine(
            parsed_end,
            datetime.time(23, 59, 59, 999999),
            tzinfo=tz,
        )

    records = await nutrition_service.get_feeding_entries(
        session=session,
        pet_id=pet.id,
        since_dt=since_dt,
        until_dt=until_dt,
    )
    if not records:
        return get_message("no_feeding_entries", language=response_language)
    lines = []
    for record in records:
        line = f"• {record.fed_at}: {record.food_description}"
        if getattr(record, "portion_size", None) is not None:
            portion_lbl = _l("label_portion_size", response_language)
            line += f", {portion_lbl}: {record.portion_size}"
        lines.append(line)
    return "\n".join(lines)


async def _handle_get_current_diet(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает текущую диету питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    diet = await nutrition_service.get_current_diet(
        session=session,
        pet_id=pet.id,
        today=workspace_today,
    )
    if diet is None:
        return get_message("no_current_diet", language=response_language)
    line = f"{_l('label_brand', response_language)}: {diet.food_brand}"
    if getattr(diet, "food_type", None) is not None:
        line += f", {_l('label_food_type', response_language)}: {diet.food_type}"
    if getattr(diet, "start_date", None) is not None:
        line += f", {_l('label_start_date', response_language)}: {diet.start_date}"
    if getattr(diet, "notes", None) is not None:
        line += f", {_l('label_notes', response_language)}: {diet.notes}"
    return line


async def _handle_get_medical_records(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает медицинские записи питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    record_type = arguments.get("record_type")
    records = await health_service.get_medical_records(
        session=session,
        pet_id=pet.id,
        record_type=record_type,
    )
    if not records:
        return get_message("no_medical_records", language=response_language)
    lines = []
    for record in records:
        line = f"• [{record.record_type}] {record.title} ({record.date})"
        if getattr(record, "description", None) is not None:
            line += (
                f", {_l('label_description', response_language)}: {record.description}"
            )
        if getattr(record, "vet_name", None) is not None:
            line += f", {_l('label_vet_name', response_language)}: {record.vet_name}"
        if getattr(record, "resolved_date", None) is not None:
            resolved_lbl = _l("label_resolved_date", response_language)
            line += f", {resolved_lbl}: {record.resolved_date}"
        lines.append(line)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Обработчики новых сущностей (T019)
# ═══════════════════════════════════════════════════════════════════════════════


async def _handle_add_measurement(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает физиологическое измерение питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    measured_at = _parse_date_field(
        arguments["measured_at"],
        field_name="measured_at",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    measurement_type = arguments["measurement_type"]
    unit = _MEASUREMENT_UNIT_MAP.get(measurement_type, measurement_type)
    record = await health_service.add_measurement(
        session=session,
        pet_id=pet.id,
        measurement_type=measurement_type,
        value=Decimal(str(arguments["value"])),
        unit=unit,
        measured_at=measured_at,
        recorded_by=user_id,
    )
    display_unit = _get_display_unit(measurement_type, response_language)
    return get_message(
        "measurement_saved",
        language=response_language,
        measurement_type=record.measurement_type,
        value=record.value,
        unit=display_unit,
    )


async def _handle_get_measurements(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает физиологические измерения питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    measurement_type = arguments.get("measurement_type")
    limit = arguments.get("limit", 10)
    # Парсим опциональные даты периода
    start_date = None
    end_date = None
    if "start_date" in arguments:
        start_date = _parse_date_field(
            arguments["start_date"],
            field_name="start_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "end_date" in arguments:
        end_date = _parse_date_field(
            arguments["end_date"],
            field_name="end_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    records = await health_service.get_measurements(
        session=session,
        pet_id=pet.id,
        measurement_type=measurement_type,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    if not records:
        return get_message("no_measurements", language=response_language)
    lines = []
    for record in records:
        display_unit = _get_display_unit(record.measurement_type, response_language)
        lines.append(
            f"• {record.measured_at} — "
            f"{record.measurement_type}: "
            f"{record.value} {display_unit}"
        )
    return "\n".join(lines)


async def _handle_add_vet_visit(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает визит к ветеринару."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    visit_date = _parse_date_field(
        arguments["visit_date"],
        field_name="visit_date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры
    kwargs: dict = {}
    if "status" in arguments:
        kwargs["status"] = arguments["status"]
    if "clinic" in arguments:
        kwargs["clinic"] = arguments["clinic"]
    if "notes" in arguments:
        kwargs["notes"] = arguments["notes"]
    # status передаётся как позиционный, если указан; иначе default в сервисе
    status = kwargs.pop("status", "planned")
    record = await health_service.add_vet_visit(
        session=session,
        pet_id=pet.id,
        reason=arguments["reason"],
        visit_date=visit_date,
        status=status,
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "vet_visit_saved",
        language=response_language,
        reason=record.reason,
        visit_date=record.visit_date,
    )


async def _handle_get_vet_visits(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает визиты к ветеринару."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    status = arguments.get("status")
    records = await health_service.get_vet_visits(
        session=session,
        pet_id=pet.id,
        status=status,
    )
    if not records:
        return get_message("no_vet_visits", language=response_language)
    lines = []
    for record in records:
        line = f"• {record.visit_date} — {record.reason} ({record.status})"
        if getattr(record, "clinic", None) is not None:
            line += f", {_l('label_clinic', response_language)}: {record.clinic}"
        if getattr(record, "notes", None) is not None:
            line += f", {_l('label_notes', response_language)}: {record.notes}"
        lines.append(line)
    return "\n".join(lines)


async def _handle_add_mood_log(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает наблюдение за состоянием питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    log_date = _parse_date_field(
        arguments["log_date"],
        field_name="log_date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры
    kwargs: dict = {}
    if "notes" in arguments:
        kwargs["notes"] = arguments["notes"]
    record = await health_service.add_mood_log(
        session=session,
        pet_id=pet.id,
        mood=arguments["mood"],
        appetite=arguments["appetite"],
        log_date=log_date,
        recorded_by=user_id,
        **kwargs,
    )
    return get_message(
        "mood_log_saved",
        language=response_language,
        mood=record.mood,
        appetite=record.appetite,
    )


async def _handle_get_mood_logs(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает наблюдения за состоянием питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    limit = arguments.get("limit", 10)
    records = await health_service.get_mood_logs(
        session=session,
        pet_id=pet.id,
        limit=limit,
    )
    if not records:
        return get_message("no_mood_logs", language=response_language)
    lines = []
    for record in records:
        line = (
            f"• {record.log_date} — "
            f"{_l('label_mood', response_language)}: {record.mood}, "
            f"{_l('label_appetite', response_language)}: {record.appetite}"
        )
        if getattr(record, "notes", None) is not None:
            line += f", {_l('label_notes', response_language)}: {record.notes}"
        lines.append(line)
    return "\n".join(lines)


async def _handle_add_heat_cycle(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Записывает цикл течки питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    start_date = _parse_date_field(
        arguments["start_date"],
        field_name="start_date",
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )
    # Опциональные параметры
    kwargs: dict = {}
    if "end_date" in arguments:
        kwargs["end_date"] = _parse_date_field(
            arguments["end_date"],
            field_name="end_date",
            workspace_timezone=workspace_timezone,
            workspace_today=workspace_today,
        )
    if "notes" in arguments:
        kwargs["notes"] = arguments["notes"]
    # Доменная валидация: предупреждение для физиологически некорректных случаев
    warnings: list[str] = []
    if getattr(pet, "is_neutered", False):
        warnings.append(
            get_message("heat_cycle_warning_neutered", language=response_language)
        )
    if getattr(pet, "gender", None) == "male":
        warnings.append(
            get_message("heat_cycle_warning_male", language=response_language)
        )
    record = await health_service.add_heat_cycle(
        session=session,
        pet_id=pet.id,
        start_date=start_date,
        recorded_by=user_id,
        **kwargs,
    )
    result = get_message(
        "heat_cycle_saved",
        language=response_language,
        start_date=record.start_date,
    )
    if warnings:
        result += "\n" + "\n".join(warnings)
    return result


async def _handle_get_heat_cycles(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    workspace_id: int,
    response_language: str = "ru",
    workspace_timezone: str = "UTC",
    workspace_today: datetime.date | None = None,
) -> str:
    """Возвращает циклы течки питомца."""
    pet = await _resolve_pet(session, workspace_id, arguments["pet_name"])
    records = await health_service.get_heat_cycles(
        session=session,
        pet_id=pet.id,
    )
    if not records:
        return get_message("no_heat_cycles", language=response_language)
    lines = []
    for record in records:
        line = f"• {_l('label_start_date', response_language)}: {record.start_date}"
        if getattr(record, "end_date", None) is not None:
            line += f", {_l('label_end_date', response_language)}: {record.end_date}"
        if getattr(record, "notes", None) is not None:
            line += f", {_l('label_notes', response_language)}: {record.notes}"
        lines.append(line)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════════════════════════════════════


def _l(key: str, lang: str) -> str:
    """Возвращает локализованную метку для форматированного вывода."""
    return get_message(key, language=lang)


async def _resolve_pet(
    session: AsyncSession,
    workspace_id: int,
    pet_name: str,
) -> object:
    """Находит питомца по имени в workspace или бросает ValueError.

    Выполняет запрос к БД напрямую (без делегирования в pet_service),
    чтобы корректно работать с mock-сессиями в тестах.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        pet_name: имя питомца

    Возвращает:
        Pet: найденный питомец

    Ошибки:
        ValueError: если питомец не найден
    """
    result = await session.execute(
        select(Pet).where(
            Pet.workspace_id == workspace_id,
            Pet.is_active.is_(True),
            func.lower(Pet.name) == pet_name.lower(),
        )
    )
    pet = result.scalar_one_or_none()

    # В тестах mock-сессия может вернуть корутину вместо значения
    if inspect.isawaitable(pet):
        pet = await pet

    if pet is None:
        raise ValueError(f"Питомец '{pet_name}' не найден в workspace")
    return pet


def _format_pet_profile(
    pet: object,
    response_language: str,
) -> str:
    """Форматирует профиль питомца в текстовую строку.

    Аргументы:
        pet: объект Pet

    Возвращает:
        str: текстовое описание профиля
    """
    breed_part = _get_pet_profile_part(
        key="pet_profile_breed_part",
        value=getattr(pet, "breed", None),
        response_language=response_language,
        field_name="breed",
    )
    birth_date_part = _get_pet_profile_part(
        key="pet_profile_birth_date_part",
        value=getattr(pet, "birth_date", None),
        response_language=response_language,
        field_name="birth_date",
    )
    return get_message(
        "pet_profile",
        language=response_language,
        name=pet.name,
        species=pet.species,
        breed_part=breed_part,
        birth_date_part=birth_date_part,
    )


def _format_emergency_profile(
    profile: object,
    response_language: str,
) -> str:
    """Форматирует экстренный профиль в текстовую строку.

    Аргументы:
        profile: объект EmergencyProfile

    Возвращает:
        str: текстовое описание экстренного профиля
    """
    parts = _get_emergency_profile_parts(profile, response_language)
    if parts:
        return "; ".join(parts)
    return get_message("emergency_profile_empty", language=response_language)


def _get_pet_profile_part(
    key: str,
    value: object,
    response_language: str,
    field_name: str,
) -> str:
    """Возвращает локализованный фрагмент профиля или пустую строку."""
    if value is None:
        return ""
    return get_message(
        key,
        language=response_language,
        **{field_name: value},
    )


def _get_emergency_profile_parts(
    profile: object,
    response_language: str,
) -> list[str]:
    """Возвращает непустые локализованные части экстренного профиля."""
    values = {
        "emergency_profile_allergies": getattr(profile, "allergies", None),
        "emergency_profile_chronic_conditions": getattr(
            profile, "chronic_conditions", None
        ),
        "emergency_profile_vet_contact": getattr(profile, "vet_contact", None),
        "emergency_profile_blood_type": getattr(profile, "blood_type", None),
        "emergency_profile_rabies_vaccination_date": getattr(
            profile,
            "rabies_vaccination_date",
            None,
        ),
        "emergency_profile_latest_weight_snapshot": getattr(
            profile,
            "latest_weight_snapshot",
            None,
        ),
    }
    return [
        get_message(key, language=response_language, value=value)
        for key, value in values.items()
        if _has_non_empty_profile_value(value)
    ]


def _extract_update_fields(arguments: dict) -> dict:
    """Извлекает поля для обновления из аргументов (исключая pet_name).

    Аргументы:
        arguments: словарь аргументов от OpenAI

    Возвращает:
        dict: поля для передачи в update_pet
    """
    return _extract_whitelisted_fields(
        arguments=arguments,
        allowed_fields=_PET_UPDATE_FIELD_WHITELIST,
        tool_name="update_pet",
    )


def _extract_emergency_fields(arguments: dict) -> dict:
    """Извлекает поля экстренного профиля из аргументов (исключая pet_name).

    Аргументы:
        arguments: словарь аргументов от OpenAI

    Возвращает:
        dict: поля для передачи в update_emergency_profile
    """
    return _extract_whitelisted_fields(
        arguments=arguments,
        allowed_fields=_EMERGENCY_UPDATE_FIELD_WHITELIST,
        tool_name="update_emergency_profile",
    )


def _extract_whitelisted_fields(
    arguments: dict[str, object],
    allowed_fields: set[str],
    tool_name: str,
) -> dict[str, object]:
    """Возвращает поля только из whitelist и отклоняет лишние ключи."""
    payload_fields = {
        key: value for key, value in arguments.items() if key != "pet_name"
    }
    unexpected_fields = set(payload_fields) - allowed_fields
    if unexpected_fields:
        unexpected_fields_text = ", ".join(sorted(unexpected_fields))
        raise ValueError(
            f"Недопустимые поля для {tool_name}: {unexpected_fields_text}."
        )
    return payload_fields


def _normalize_pet_update_fields(
    fields: dict[str, object],
    workspace_timezone: str,
    workspace_today: datetime.date | None = None,
) -> dict[str, object]:
    """Нормализует поля update_pet до доменных типов."""
    normalized_fields: dict[str, object] = {}
    for field_name, field_value in fields.items():
        if field_name == "birth_date":
            normalized_fields[field_name] = _parse_optional_runtime_date(
                raw_value=field_value,
                field_name="birth_date",
                workspace_timezone=workspace_timezone,
                workspace_today=workspace_today,
            )
            continue
        normalized_fields[field_name] = field_value
    return normalized_fields


def _normalize_emergency_update_fields(
    fields: dict[str, object],
    workspace_timezone: str,
    workspace_today: datetime.date | None = None,
) -> dict[str, object]:
    """Нормализует поля update_emergency_profile до доменных типов."""
    normalized_fields: dict[str, object] = {}
    nullable_string_fields = {
        "allergies",
        "chronic_conditions",
        "vet_contact",
        "blood_type",
    }
    for field_name, field_value in fields.items():
        if field_name in nullable_string_fields:
            normalized_fields[field_name] = _normalize_nullable_emergency_value(
                field_name=field_name,
                field_value=field_value,
            )
            continue
        if field_name == "rabies_vaccination_date" and field_value is not None:
            normalized_fields[field_name] = _parse_optional_runtime_date(
                raw_value=field_value,
                field_name="rabies_vaccination_date",
                workspace_timezone=workspace_timezone,
                workspace_today=workspace_today,
            )
            continue
        if field_name == "latest_weight_snapshot" and field_value is not None:
            normalized_fields[field_name] = Decimal(str(field_value))
            continue
        normalized_fields[field_name] = field_value
    return normalized_fields


def _normalize_nullable_emergency_value(
    field_name: str,
    field_value: object,
) -> str | None:
    """Преобразует nullable-строки emergency-профиля и sentinel-значения."""
    if field_value is None:
        return None
    if not isinstance(field_value, str):
        raise TypeError(f"Параметр {field_name} должен быть строкой или None.")
    normalized_value = field_value.strip()
    if normalized_value.lower() in {"", "unknown", "null"}:
        return None
    return normalized_value


def _parse_optional_runtime_date(
    raw_value: object,
    field_name: str,
    workspace_timezone: str,
    workspace_today: datetime.date | None = None,
) -> datetime.date | None:
    """Парсит optional date-поле и поддерживает относительные даты."""
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise TypeError(f"Параметр {field_name} должен быть строкой или None.")
    return _parse_date_field(
        raw_value=raw_value,
        field_name=field_name,
        workspace_timezone=workspace_timezone,
        workspace_today=workspace_today,
    )


def _has_non_empty_profile_value(value: object) -> bool:
    """Проверяет, что значение профиля нужно включить в ответ."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


async def _resolve_workspace_timezone(
    session: AsyncSession,
    workspace_id: int,
) -> str:
    """Возвращает таймзону workspace; при ошибке использует UTC."""
    try:
        return await workspace_service.get_timezone(session, workspace_id)
    except Exception:
        logger.exception(
            "Не удалось получить таймзону workspace id=%d, fallback на UTC",
            workspace_id,
        )
        return "UTC"


def _resolve_response_language(response_language: str) -> str:
    """Нормализует язык ответа до ru/en (fallback ru)."""
    if response_language in {"ru", "en"}:
        return response_language
    return "ru"


def _parse_date_field(
    raw_value: str,
    field_name: str,
    workspace_timezone: str,
    workspace_today: datetime.date | None = None,
) -> datetime.date:
    """Парсит date-поле через единый runtime helper."""
    if workspace_today is None:
        return parse_runtime_date(
            value=raw_value,
            timezone=workspace_timezone,
            field_name=field_name,
        )
    return parse_runtime_date(
        value=raw_value,
        timezone=workspace_timezone,
        field_name=field_name,
        family_today=workspace_today,
    )


def _parse_offset_aware_datetime(
    raw_value: object,
    field_name: str,
) -> datetime.datetime:
    """Парсит datetime и проверяет наличие timezone offset."""
    if not isinstance(raw_value, str):
        raise TypeError(f"Параметр {field_name} должен быть строкой ISO datetime.")
    try:
        parsed_datetime = datetime.datetime.fromisoformat(raw_value)
    except ValueError as parsing_error:
        raise ValueError(
            f"Параметр {field_name} должен быть ISO datetime с offset "
            "(например, 2026-03-08T12:30:00+03:00)."
        ) from parsing_error
    if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
        raise ValueError(
            f"Параметр {field_name} должен содержать timezone offset "
            "(например, 2026-03-08T12:30:00+03:00)."
        )
    return parsed_datetime


# Маппинг имён инструментов на обработчики
_TOOL_HANDLERS: dict = {
    "add_weight": _handle_add_weight,
    "add_vaccination": _handle_add_vaccination,
    "add_medication": _handle_add_medication,
    "add_note": _handle_add_note,
    "add_diet": _handle_add_diet,
    "add_feeding": _handle_add_feeding,
    "get_pet_profile": _handle_get_pet_profile,
    "update_pet": _handle_update_pet,
    "create_pet": _handle_create_pet,
    "update_emergency_profile": _handle_update_emergency_profile,
    "get_emergency_profile": _handle_get_emergency_profile,
    "get_weight_history": _handle_get_weight_history,
    "get_vaccinations": _handle_get_vaccinations,
    "get_medications": _handle_get_medications,
    "get_notes": _handle_get_notes,
    "get_feeding_history": _handle_get_feeding_history,
    "get_current_diet": _handle_get_current_diet,
    "add_medical_record": _handle_add_medical_record,
    "get_medical_records": _handle_get_medical_records,
    "add_measurement": _handle_add_measurement,
    "get_measurements": _handle_get_measurements,
    "add_vet_visit": _handle_add_vet_visit,
    "get_vet_visits": _handle_get_vet_visits,
    "add_mood_log": _handle_add_mood_log,
    "get_mood_logs": _handle_get_mood_logs,
    "add_heat_cycle": _handle_add_heat_cycle,
    "get_heat_cycles": _handle_get_heat_cycles,
}
