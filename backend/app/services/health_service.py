"""
Сервис управления здоровьем питомца: вес, вакцинации, медкарты,
лекарства, заметки и экстренный профиль.

Все функции принимают AsyncSession первым аргументом
и не управляют транзакциями (commit/rollback -- ответственность вызывающего).
"""

from __future__ import annotations

import datetime
import logging
import re
from decimal import Decimal

from backend.app.db.models.health import (
    EmergencyProfile,
    MedicalRecord,
    Medication,
    Note,
    Vaccination,
    WeightRecord,
)
from backend.app.db.models.pet import Pet
from backend.app.services import audit_service
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_EMERGENCY_NULL_SENTINELS = {"unknown", "null"}
_DEA_BLOOD_TYPE_PATTERN = re.compile(r"^DEA\s*([0-9]+(?:\.[0-9]+)?)\s*([+-])$")
_EMERGENCY_PROFILE_ALLOWED_UPDATE_FIELDS = {
    "allergies",
    "chronic_conditions",
    "vet_contact",
    "blood_type",
    "rabies_vaccination_date",
    "latest_weight_snapshot",
}
_EMERGENCY_PROFILE_FORBIDDEN_FIELDS = {"id", "pet_id"}


# ═══════════════════════════════════════════════════════════════════════════════
# T027: Вес
# ═══════════════════════════════════════════════════════════════════════════════


async def add_weight(
    session: AsyncSession,
    pet_id: int,
    weight_kg: Decimal,
    measured_at: datetime.date,
    recorded_by: int | None = None,
) -> WeightRecord:
    """Создаёт запись о весе питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        weight_kg: вес в килограммах
        measured_at: дата измерения
        recorded_by: ID участника, записавшего вес (обязательный)

    Возвращает:
        WeightRecord: созданная запись

    Побочные эффекты:
        Добавляет WeightRecord в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    record = WeightRecord(
        pet_id=pet_id,
        weight_kg=weight_kg,
        measured_at=measured_at,
        recorded_by=valid_recorded_by,
    )
    session.add(record)
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="weight_record",
        entity_id=record.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json={
            "pet_id": pet_id,
            "weight_kg": weight_kg,
            "measured_at": measured_at,
            "recorded_by": valid_recorded_by,
        },
    )

    logger.info(
        "Записан вес %.2f кг для питомца id=%d на %s",
        weight_kg,
        pet_id,
        measured_at,
    )
    return record


async def get_weight_history(
    session: AsyncSession,
    pet_id: int,
) -> list[WeightRecord]:
    """Возвращает историю веса питомца, отсортированную по дате (от новых к старым).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        list[WeightRecord]: список записей, отсортированных по measured_at DESC
    """
    result = await session.execute(
        select(WeightRecord)
        .where(WeightRecord.pet_id == pet_id)
        .order_by(WeightRecord.measured_at.desc())
    )
    return list(result.scalars().all())


async def get_latest_weight(
    session: AsyncSession,
    pet_id: int,
) -> WeightRecord | None:
    """Возвращает самую свежую запись о весе питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        WeightRecord | None: последняя запись или None
    """
    result = await session.execute(
        select(WeightRecord)
        .where(WeightRecord.pet_id == pet_id)
        .order_by(WeightRecord.measured_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════════════
# T027: Вакцинации
# ═══════════════════════════════════════════════════════════════════════════════


async def add_vaccination(
    session: AsyncSession,
    pet_id: int,
    vaccine_name: str,
    date: datetime.date,
    **kwargs: object,
) -> Vaccination:
    """Создаёт запись о вакцинации питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        vaccine_name: название вакцины
        date: дата вакцинации
        **kwargs: доп. поля (next_date, vet_name, batch_number, notes, recorded_by).
            recorded_by обязателен.

    Возвращает:
        Vaccination: созданная запись

    Побочные эффекты:
        Добавляет Vaccination в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_recorded_by_in_kwargs(kwargs)
    kwargs["recorded_by"] = valid_recorded_by
    vaccination = Vaccination(
        pet_id=pet_id,
        vaccine_name=vaccine_name,
        date=date,
        **kwargs,
    )
    session.add(vaccination)
    await session.flush()
    create_diff: dict[str, object] = {
        "pet_id": pet_id,
        "vaccine_name": vaccine_name,
        "date": date,
        "recorded_by": valid_recorded_by,
    }
    if vaccination.next_date is not None:
        create_diff["next_date"] = vaccination.next_date
    await _log_health_change(
        session=session,
        entity_type="vaccination",
        entity_id=vaccination.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json=create_diff,
    )

    logger.info(
        "Записана вакцинация '%s' для питомца id=%d на %s",
        vaccine_name,
        pet_id,
        date,
    )
    return vaccination


async def get_vaccinations(
    session: AsyncSession,
    pet_id: int,
) -> list[Vaccination]:
    """Возвращает все вакцинации питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        list[Vaccination]: список записей о вакцинации
    """
    result = await session.execute(
        select(Vaccination)
        .where(Vaccination.pet_id == pet_id)
        .order_by(Vaccination.date.desc())
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# T027: Медицинские записи
# ═══════════════════════════════════════════════════════════════════════════════


async def add_medical_record(
    session: AsyncSession,
    pet_id: int,
    record_type: str,
    title: str,
    date: datetime.date,
    **kwargs: object,
) -> MedicalRecord:
    """Создаёт медицинскую запись для питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        record_type: тип записи (illness/checkup/surgery/...)
        title: заголовок записи
        date: дата события
        **kwargs: доп. поля (description, resolved_date, vet_name, recorded_by)

    Возвращает:
        MedicalRecord: созданная запись

    Побочные эффекты:
        Добавляет MedicalRecord в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_recorded_by_in_kwargs(kwargs)
    kwargs["recorded_by"] = valid_recorded_by
    record = MedicalRecord(
        pet_id=pet_id,
        record_type=record_type,
        title=title,
        date=date,
        **kwargs,
    )
    session.add(record)
    await session.flush()
    create_diff: dict[str, object] = {
        "pet_id": pet_id,
        "record_type": record_type,
        "title": title,
        "date": date,
        "recorded_by": valid_recorded_by,
    }
    if record.description is not None:
        create_diff["description"] = record.description
    if record.resolved_date is not None:
        create_diff["resolved_date"] = record.resolved_date
    if record.vet_name is not None:
        create_diff["vet_name"] = record.vet_name
    await _log_health_change(
        session=session,
        entity_type="medical_record",
        entity_id=record.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json=create_diff,
    )

    logger.info(
        "Создана медкарта '%s' (тип=%s) для питомца id=%d",
        title,
        record_type,
        pet_id,
    )
    return record


async def get_medical_records(
    session: AsyncSession,
    pet_id: int,
    record_type: str | None = None,
    active_only: bool = False,
) -> list[MedicalRecord]:
    """Возвращает медицинские записи питомца с опциональными фильтрами.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        record_type: фильтр по типу записи (None -- все типы)
        active_only: True -- только незакрытые (resolved_date IS NULL)

    Возвращает:
        list[MedicalRecord]: отфильтрованный список записей
    """
    query = select(MedicalRecord).where(MedicalRecord.pet_id == pet_id)
    query = _apply_medical_filters(query, record_type, active_only)
    query = query.order_by(MedicalRecord.date.desc())

    result = await session.execute(query)
    return list(result.scalars().all())


def _apply_medical_filters(
    query: Select[tuple[MedicalRecord]],
    record_type: str | None,
    active_only: bool,
) -> Select[tuple[MedicalRecord]]:
    """Применяет фильтры record_type и active_only к запросу MedicalRecord.

    Аргументы:
        query: SQLAlchemy select-запрос
        record_type: фильтр по типу (None -- пропустить)
        active_only: True -- добавить фильтр resolved_date IS NULL

    Возвращает:
        Модифицированный запрос
    """
    if record_type is not None:
        query = query.where(MedicalRecord.record_type == record_type)
    if active_only:
        query = query.where(MedicalRecord.resolved_date.is_(None))
    return query


# ═══════════════════════════════════════════════════════════════════════════════
# T027: Лекарства
# ═══════════════════════════════════════════════════════════════════════════════


async def add_medication(
    session: AsyncSession,
    pet_id: int,
    name: str,
    start_date: datetime.date,
    **kwargs: object,
) -> Medication:
    """Создаёт запись о лекарстве для питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        name: название препарата
        start_date: дата начала приёма
        **kwargs: доп. поля (dosage, frequency, end_date, notes, recorded_by).
            recorded_by обязателен.

    Возвращает:
        Medication: созданная запись (is_active=True по умолчанию)

    Побочные эффекты:
        Добавляет Medication в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_recorded_by_in_kwargs(kwargs)
    kwargs["recorded_by"] = valid_recorded_by
    medication = Medication(
        pet_id=pet_id,
        name=name,
        start_date=start_date,
        **kwargs,
    )
    session.add(medication)
    await session.flush()
    create_diff: dict[str, object] = {
        "pet_id": pet_id,
        "name": name,
        "start_date": start_date,
        "recorded_by": valid_recorded_by,
    }
    if "dosage" in kwargs and kwargs["dosage"] is not None:
        create_diff["dosage"] = kwargs["dosage"]
    await _log_health_change(
        session=session,
        entity_type="medication",
        entity_id=medication.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json=create_diff,
    )

    logger.info(
        "Добавлено лекарство '%s' для питомца id=%d с %s",
        name,
        pet_id,
        start_date,
    )
    return medication


async def get_medications(
    session: AsyncSession,
    pet_id: int,
    active_only: bool = False,
) -> list[Medication]:
    """Возвращает лекарства питомца с опциональным фильтром по активности.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        active_only: True -- только активные (is_active=True)

    Возвращает:
        list[Medication]: список лекарств
    """
    query = select(Medication).where(Medication.pet_id == pet_id)
    if active_only:
        query = query.where(Medication.is_active.is_(True))
    query = query.order_by(Medication.start_date.desc())

    result = await session.execute(query)
    return list(result.scalars().all())


async def deactivate_medication(
    session: AsyncSession,
    medication_id: int,
    actor_id: int | None = None,
    deactivated_on: datetime.date | None = None,
) -> Medication:
    """Деактивирует лекарство (is_active=False).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        medication_id: ID лекарства
        actor_id: user-origin ID инициатора закрытия препарата
        deactivated_on: календарная дата завершения (если None — текущая дата UTC)

    Возвращает:
        Medication: обновлённое лекарство

    Ошибки:
        ValueError: если actor_id равен None
        ValueError: если лекарство не найдено

    Побочные эффекты:
        Устанавливает is_active=False, end_date=deactivated_on (или текущая дата UTC),
        делает flush и пишет аудит close.
    """
    valid_actor_id = _require_actor_id(actor_id)
    medication = await _get_medication_or_raise(session, medication_id)
    medication.is_active = False
    medication.end_date = (
        deactivated_on or datetime.datetime.now(tz=datetime.UTC).date()
    )
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="medication",
        entity_id=medication.id,
        pet_id=medication.pet_id,
        action="close",
        actor_id=valid_actor_id,
        diff_json={
            "is_active": medication.is_active,
            "end_date": medication.end_date,
        },
    )

    logger.info("Деактивировано лекарство id=%d", medication_id)
    return medication


async def _get_medication_or_raise(
    session: AsyncSession,
    medication_id: int,
) -> Medication:
    """Возвращает лекарство по ID или бросает ValueError.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        medication_id: ID лекарства

    Возвращает:
        Medication: найденное лекарство

    Ошибки:
        ValueError: если лекарство не найдено
    """
    result = await session.execute(
        select(Medication).where(Medication.id == medication_id)
    )
    medication = result.scalar_one_or_none()

    if medication is None:
        raise ValueError(f"Лекарство с id={medication_id} не найдено")

    return medication


# ═══════════════════════════════════════════════════════════════════════════════
# T027: Заметки
# ═══════════════════════════════════════════════════════════════════════════════


async def add_note(
    session: AsyncSession,
    pet_id: int,
    content: str,
    recorded_by: int | None = None,
) -> Note:
    """Создаёт заметку о питомце.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        content: текст заметки
        recorded_by: ID участника, записавшего заметку (обязательный)

    Возвращает:
        Note: созданная заметка

    Побочные эффекты:
        Добавляет Note в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    note = Note(
        pet_id=pet_id,
        content=content,
        recorded_by=valid_recorded_by,
    )
    session.add(note)
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="note",
        entity_id=note.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json={
            "pet_id": pet_id,
            "content": content,
            "recorded_by": valid_recorded_by,
        },
    )

    logger.info("Создана заметка для питомца id=%d", pet_id)
    return note


async def get_notes(
    session: AsyncSession,
    pet_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[Note]:
    """Возвращает заметки питомца с пагинацией, от новых к старым.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        limit: максимальное количество записей (по умолчанию 20)
        offset: количество записей для пропуска (по умолчанию 0)

    Возвращает:
        list[Note]: список заметок, отсортированных по created_at DESC
    """
    result = await session.execute(
        select(Note)
        .where(Note.pet_id == pet_id)
        .order_by(Note.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# T108: Экстренный профиль
# ═══════════════════════════════════════════════════════════════════════════════


async def get_or_create_emergency_profile(
    session: AsyncSession,
    pet_id: int,
    actor_id: int | None = None,
) -> EmergencyProfile:
    """Возвращает экстренный профиль питомца; создаёт пустой, если отсутствует.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        actor_id: user-origin ID; обязателен только при auto-create профиля

    Возвращает:
        EmergencyProfile: существующий или новый профиль

    Побочные эффекты:
        При отсутствии профиля -- создаёт новый, делает flush и пишет аудит create.
    """
    existing = await _find_emergency_profile(session, pet_id)
    if existing is not None:
        return existing

    valid_actor_id = _require_actor_id(actor_id)
    return await _create_empty_emergency_profile(session, pet_id, valid_actor_id)


async def _find_emergency_profile(
    session: AsyncSession,
    pet_id: int,
) -> EmergencyProfile | None:
    """Ищет экстренный профиль питомца по pet_id.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        EmergencyProfile | None: найденный профиль или None
    """
    result = await session.execute(
        select(EmergencyProfile).where(EmergencyProfile.pet_id == pet_id)
    )
    return result.scalar_one_or_none()


async def _create_empty_emergency_profile(
    session: AsyncSession,
    pet_id: int,
    actor_id: int,
) -> EmergencyProfile:
    """Создаёт пустой экстренный профиль для питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        actor_id: user-origin ID инициатора создания

    Возвращает:
        EmergencyProfile: созданный профиль

    Побочные эффекты:
        Добавляет EmergencyProfile в сессию, делает flush и пишет аудит create.
    """
    profile = EmergencyProfile(pet_id=pet_id)
    session.add(profile)
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="emergency_profile",
        entity_id=profile.id,
        pet_id=pet_id,
        action="create",
        actor_id=actor_id,
        diff_json={"pet_id": pet_id},
    )

    logger.info("Создан экстренный профиль для питомца id=%d", pet_id)
    return profile


async def update_emergency_profile(
    session: AsyncSession,
    pet_id: int,
    actor_id: int | None = None,
    **fields: object,
) -> EmergencyProfile:
    """Обновляет поля экстренного профиля питомца (partial update).

    Обновляет только переданные поля, не затрагивая остальные.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        actor_id: user-origin ID инициатора обновления
        **fields: поля для обновления (allergies, chronic_conditions и т.д.)

    Возвращает:
        EmergencyProfile: обновлённый профиль

    Побочные эффекты:
        Обновляет атрибуты EmergencyProfile, делает flush и пишет аудит update.
    """
    valid_actor_id = _require_actor_id(actor_id)
    validated_fields = _validate_emergency_profile_update_fields(fields)
    normalized_fields = _normalize_emergency_profile_fields(validated_fields)
    profile = await _find_emergency_profile(session, pet_id)
    if profile is None:
        profile = await _create_empty_emergency_profile(session, pet_id, valid_actor_id)
    changed_fields = _get_changed_fields(profile, normalized_fields)
    for key, value in changed_fields.items():
        setattr(profile, key, value)
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="emergency_profile",
        entity_id=profile.id,
        pet_id=pet_id,
        action="update",
        actor_id=valid_actor_id,
        diff_json=changed_fields,
    )

    logger.info(
        "Обновлён экстренный профиль питомца id=%d, поля: %s",
        pet_id,
        list(changed_fields.keys()),
    )
    return profile


def _normalize_emergency_profile_fields(fields: dict[str, object]) -> dict[str, object]:
    """Нормализует и валидирует входные поля update_emergency_profile."""
    normalized_fields: dict[str, object] = {}
    for field_name, field_value in fields.items():
        if field_name in {"allergies", "chronic_conditions"}:
            normalized_fields[field_name] = _normalize_nullable_emergency_text(
                field_name=field_name,
                field_value=field_value,
            )
            continue
        if field_name == "vet_contact":
            normalized_fields[field_name] = _normalize_vet_contact(field_value)
            continue
        if field_name == "blood_type":
            normalized_fields[field_name] = _normalize_blood_type(field_value)
            continue
        normalized_fields[field_name] = field_value
    return normalized_fields


def _validate_emergency_profile_update_fields(
    fields: dict[str, object],
) -> dict[str, object]:
    """Проверяет whitelist update_emergency_profile и служебные ключи."""
    unexpected_fields = {
        field_name
        for field_name in fields
        if field_name in _EMERGENCY_PROFILE_FORBIDDEN_FIELDS
        or field_name not in _EMERGENCY_PROFILE_ALLOWED_UPDATE_FIELDS
    }
    if unexpected_fields:
        unexpected_fields_text = ", ".join(sorted(unexpected_fields))
        raise ValueError(
            f"Недопустимые поля для update_emergency_profile: {unexpected_fields_text}."
        )
    return fields


def _normalize_nullable_emergency_text(
    field_name: str,
    field_value: object,
) -> str | None:
    """Нормализует nullable-текстовые поля экстренного профиля."""
    if field_value is None:
        return None
    if not isinstance(field_value, str):
        raise TypeError(f"Параметр {field_name} должен быть строкой или None.")
    normalized_value = field_value.strip()
    if normalized_value == "":
        return None
    if normalized_value.lower() in _EMERGENCY_NULL_SENTINELS:
        return None
    return normalized_value


def _normalize_vet_contact(field_value: object) -> str | None:
    """Проверяет vet_contact и отбрасывает sentinel-значения."""
    if field_value is None:
        return None
    if not isinstance(field_value, str):
        raise TypeError("Параметр vet_contact должен быть строкой или None.")
    normalized_value = field_value.strip()
    if normalized_value.lower() in _EMERGENCY_NULL_SENTINELS:
        return None
    if normalized_value == "":
        raise ValueError("Параметр vet_contact не может быть пустым.")
    if not any(character.isalnum() for character in normalized_value):
        raise ValueError("Параметр vet_contact содержит невалидное значение.")
    return normalized_value


def _normalize_blood_type(field_value: object) -> str | None:
    """Нормализует blood_type к каноничному формату DEA N.N±."""
    if field_value is None:
        return None
    if not isinstance(field_value, str):
        raise TypeError("Параметр blood_type должен быть строкой или None.")
    normalized_value = field_value.strip()
    if normalized_value.lower() in _EMERGENCY_NULL_SENTINELS:
        return None
    if normalized_value == "":
        raise ValueError("Параметр blood_type не может быть пустым.")

    uppercase_value = normalized_value.upper()
    match = _DEA_BLOOD_TYPE_PATTERN.match(uppercase_value)
    if match is None:
        raise ValueError("Параметр blood_type содержит нераспознаваемое значение.")
    return f"DEA {match.group(1)}{match.group(2)}"


def _require_actor_id(
    actor_id: object | None,
    parameter_name: str = "actor_id",
) -> int:
    """Проверяет, что actor_id/recorded_by задан и имеет тип int.

    Аргументы:
        actor_id: значение идентификатора инициатора изменения
        parameter_name: имя параметра для текста ошибки

    Возвращает:
        int: валидный ID инициатора

    Ошибки:
        ValueError: если параметр отсутствует (None)
        TypeError: если параметр не является int или передан bool
    """
    if actor_id is None:
        raise ValueError(f"Параметр {parameter_name} обязателен и не может быть None.")
    if isinstance(actor_id, bool) or not isinstance(actor_id, int):
        raise TypeError(f"Параметр {parameter_name} должен быть int.")
    return actor_id


def _require_recorded_by_in_kwargs(kwargs: dict[str, object]) -> int:
    """Извлекает обязательный recorded_by из kwargs и валидирует его.

    Аргументы:
        kwargs: словарь опциональных полей create-метода

    Возвращает:
        int: валидный recorded_by

    Ошибки:
        ValueError: если recorded_by отсутствует
        ValueError/TypeError: если recorded_by невалиден
    """
    if "recorded_by" not in kwargs:
        raise ValueError("Параметр recorded_by обязателен и не может отсутствовать.")
    return _require_actor_id(kwargs["recorded_by"], "recorded_by")


def _get_changed_fields(entity: object, fields: dict[str, object]) -> dict[str, object]:
    """Возвращает только реально изменённые поля относительно текущего объекта.

    Аргументы:
        entity: объект, который будет обновляться
        fields: входные значения для обновления

    Возвращает:
        dict[str, object]: пары ключ-значение только для изменённых полей
    """
    changed_fields: dict[str, object] = {}
    for key, value in fields.items():
        if getattr(entity, key) != value:
            changed_fields[key] = value
    return changed_fields


async def _log_health_change(
    session: AsyncSession,
    entity_type: str,
    entity_id: int,
    pet_id: int,
    action: str,
    actor_id: int,
    diff_json: dict[str, object],
) -> None:
    """Пишет запись аудита по изменению health-сущности.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        entity_type: тип сущности для ChangeLog
        entity_id: ID изменённой сущности
        pet_id: ID питомца-владельца изменённой сущности
        action: тип действия (create/update/close)
        actor_id: ID инициатора изменения
        diff_json: минимальный diff изменения
    """
    workspace_id = await _get_workspace_id_for_pet(session, pet_id)
    await audit_service.log_change(
        session=session,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        workspace_id=workspace_id,
        diff_json=_to_audit_diff(diff_json),
    )


async def _get_workspace_id_for_pet(session: AsyncSession, pet_id: int) -> int:
    """Возвращает workspace_id питомца или бросает ValueError."""
    workspace_id = await session.scalar(
        select(Pet.workspace_id).where(Pet.id == pet_id),
    )
    if workspace_id is None:
        raise ValueError(f"Питомец с id={pet_id} не найден")
    return workspace_id


def _to_audit_diff(fields: dict[str, object]) -> dict[str, object]:
    """Преобразует словарь diff_json к JSON-совместимому формату."""
    return {key: _to_audit_value(value) for key, value in fields.items()}


def _to_audit_value(value: object) -> object:
    """Преобразует значение в JSON-safe формат для ChangeLog.diff_json."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_audit_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_audit_value(item) for item in value]
    return value
