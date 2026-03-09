"""
Маршрутизация и выполнение вызовов инструментов AI-агента.

Принимает tool_name и аргументы от OpenAI function calling,
вызывает соответствующий сервис и возвращает строку-подтверждение.
"""

from __future__ import annotations

import datetime
import inspect
import logging
from decimal import Decimal

from backend.app.agent.date_utils import InvalidRuntimeDateError, parse_runtime_date
from backend.app.agent.i18n import get_message
from backend.app.db.models.pet import Pet
from backend.app.services import (
    family_service,
    health_service,
    nutrition_service,
    pet_service,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PET_UPDATE_FIELD_WHITELIST = {
    "breed",
    "birth_date",
    "gender",
    "is_neutered",
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
    family_id: int,
    response_language: str = "ru",
    family_today: datetime.date | None = None,
) -> str:
    """Маршрутизирует вызов инструмента к соответствующему сервису.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        tool_name: имя инструмента (например, "add_weight")
        arguments: словарь аргументов от OpenAI
        user_id: Telegram user ID вызывающего
        family_id: ID семьи
        family_today: текущая дата семьи (предвычисленная в brain.run_agent)

    Возвращает:
        str: строка-подтверждение или сообщение об ошибке
    """
    resolved_language = _resolve_response_language(response_language)
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return get_message("unknown_tool", language=resolved_language)

    try:
        family_timezone = await _resolve_family_timezone(session, family_id)
        async with session.begin_nested():
            return await handler(
                session=session,
                arguments=arguments,
                user_id=user_id,
                family_id=family_id,
                response_language=resolved_language,
                family_timezone=family_timezone,
                family_today=family_today,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Записывает вес питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    measured_at = _parse_date_field(
        arguments["measured_at"],
        field_name="measured_at",
        family_timezone=family_timezone,
        family_today=family_today,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Записывает вакцинацию питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    vaccination_date = _parse_date_field(
        arguments["date"],
        field_name="date",
        family_timezone=family_timezone,
        family_today=family_today,
    )
    record = await health_service.add_vaccination(
        session=session,
        pet_id=pet.id,
        vaccine_name=arguments["vaccine_name"],
        date=vaccination_date,
        recorded_by=user_id,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Добавляет лекарство для питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    medication_start_date = _parse_date_field(
        arguments["start_date"],
        field_name="start_date",
        family_timezone=family_timezone,
        family_today=family_today,
    )
    record = await health_service.add_medication(
        session=session,
        pet_id=pet.id,
        name=arguments["name"],
        start_date=medication_start_date,
        dosage=arguments.get("dosage"),
        recorded_by=user_id,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Добавляет заметку о питомце."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Добавляет запись о диете питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    diet_start_date = _parse_date_field(
        arguments["start_date"],
        field_name="start_date",
        family_timezone=family_timezone,
        family_today=family_today,
    )
    record = await nutrition_service.add_diet_record(
        session=session,
        pet_id=pet.id,
        food_brand=arguments["food_brand"],
        start_date=diet_start_date,
        recorded_by=user_id,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Записывает факт кормления питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    fed_at = _parse_offset_aware_datetime(
        raw_value=arguments["fed_at"],
        field_name="fed_at",
    )
    record = await nutrition_service.add_feeding_entry(
        session=session,
        pet_id=pet.id,
        fed_at=fed_at,
        food_description=arguments["food_description"],
        recorded_by=user_id,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Возвращает профиль питомца в текстовом виде."""
    pet = await pet_service.get_pet_by_name(session, family_id, arguments["pet_name"])
    if pet is None:
        raise ValueError(f"Питомец '{arguments['pet_name']}' не найден")

    return _format_pet_profile(pet, response_language)


async def _handle_update_pet(
    session: AsyncSession,
    arguments: dict,
    user_id: int,
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Обновляет профиль питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    update_fields = _extract_update_fields(arguments)
    normalized_update_fields = _normalize_pet_update_fields(
        fields=update_fields,
        family_timezone=family_timezone,
        family_today=family_today,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Создаёт нового питомца."""
    pet = await pet_service.create_pet(
        session=session,
        family_id=family_id,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Обновляет экстренный профиль питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    update_fields = _extract_emergency_fields(arguments)
    normalized_update_fields = _normalize_emergency_update_fields(
        fields=update_fields,
        family_timezone=family_timezone,
        family_today=family_today,
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
    family_id: int,
    response_language: str = "ru",
    family_timezone: str = "UTC",
    family_today: datetime.date | None = None,
) -> str:
    """Возвращает экстренный профиль питомца."""
    pet = await _resolve_pet(session, family_id, arguments["pet_name"])
    profile = await health_service.get_or_create_emergency_profile(
        session,
        pet.id,
        actor_id=user_id,
    )
    return _format_emergency_profile(profile, response_language)


# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════════════════════════════════════


async def _resolve_pet(
    session: AsyncSession,
    family_id: int,
    pet_name: str,
) -> object:
    """Находит питомца по имени в семье или бросает ValueError.

    Выполняет запрос к БД напрямую (без делегирования в pet_service),
    чтобы корректно работать с mock-сессиями в тестах.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи
        pet_name: имя питомца

    Возвращает:
        Pet: найденный питомец

    Ошибки:
        ValueError: если питомец не найден
    """
    result = await session.execute(
        select(Pet).where(
            Pet.family_id == family_id,
            Pet.is_active.is_(True),
            func.lower(Pet.name) == pet_name.lower(),
        )
    )
    pet = result.scalar_one_or_none()

    # В тестах mock-сессия может вернуть корутину вместо значения
    if inspect.isawaitable(pet):
        pet = await pet

    if pet is None:
        raise ValueError(f"Питомец '{pet_name}' не найден в семье")
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
    family_timezone: str,
    family_today: datetime.date | None = None,
) -> dict[str, object]:
    """Нормализует поля update_pet до доменных типов."""
    normalized_fields: dict[str, object] = {}
    for field_name, field_value in fields.items():
        if field_name == "birth_date":
            normalized_fields[field_name] = _parse_optional_runtime_date(
                raw_value=field_value,
                field_name="birth_date",
                family_timezone=family_timezone,
                family_today=family_today,
            )
            continue
        normalized_fields[field_name] = field_value
    return normalized_fields


def _normalize_emergency_update_fields(
    fields: dict[str, object],
    family_timezone: str,
    family_today: datetime.date | None = None,
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
                family_timezone=family_timezone,
                family_today=family_today,
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
    family_timezone: str,
    family_today: datetime.date | None = None,
) -> datetime.date | None:
    """Парсит optional date-поле и поддерживает относительные даты."""
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise TypeError(f"Параметр {field_name} должен быть строкой или None.")
    return _parse_date_field(
        raw_value=raw_value,
        field_name=field_name,
        family_timezone=family_timezone,
        family_today=family_today,
    )


def _has_non_empty_profile_value(value: object) -> bool:
    """Проверяет, что значение профиля нужно включить в ответ."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


async def _resolve_family_timezone(
    session: AsyncSession,
    family_id: int,
) -> str:
    """Возвращает таймзону семьи; при ошибке использует UTC."""
    try:
        return await family_service.get_timezone(session, family_id)
    except Exception:
        logger.exception(
            "Не удалось получить таймзону семьи id=%d, fallback на UTC",
            family_id,
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
    family_timezone: str,
    family_today: datetime.date | None = None,
) -> datetime.date:
    """Парсит date-поле через единый runtime helper."""
    if family_today is None:
        return parse_runtime_date(
            value=raw_value,
            timezone=family_timezone,
            field_name=field_name,
        )
    return parse_runtime_date(
        value=raw_value,
        timezone=family_timezone,
        field_name=field_name,
        family_today=family_today,
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
}
