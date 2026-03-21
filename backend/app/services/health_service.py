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
    HeatCycle,
    Measurement,
    MedicalRecord,
    Medication,
    MoodLog,
    Note,
    Vaccination,
    VetVisit,
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
_VALID_MEDICAL_RECORD_TYPES = {"illness", "checkup", "surgery"}


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
    limit: int = 10,
) -> list[WeightRecord]:
    """Возвращает историю веса питомца, отсортированную по дате (от новых к старым).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        limit: максимальное количество записей (по умолчанию 10)

    Возвращает:
        list[WeightRecord]: список записей, отсортированных по measured_at DESC
    """
    result = await session.execute(
        select(WeightRecord)
        .where(WeightRecord.pet_id == pet_id)
        .order_by(WeightRecord.measured_at.desc())
        .limit(limit)
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
    if vaccination.vet_name is not None:
        create_diff["vet_name"] = vaccination.vet_name
    if vaccination.batch_number is not None:
        create_diff["batch_number"] = vaccination.batch_number
    if vaccination.notes is not None:
        create_diff["notes"] = vaccination.notes
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
    if record_type not in _VALID_MEDICAL_RECORD_TYPES:
        raise ValueError(
            f"Недопустимый тип медицинской записи: {record_type}. "
            f"Допустимые: {', '.join(sorted(_VALID_MEDICAL_RECORD_TYPES))}"
        )
    # Валидация хронологии: resolved_date не раньше date
    resolved_date = kwargs.get("resolved_date")
    if (
        resolved_date is not None
        and isinstance(resolved_date, datetime.date)
        and resolved_date < date
    ):
        raise ValueError(
            "Некорректная хронология medical_record: "
            "resolved_date не может быть раньше date."
        )
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
    today: datetime.date | None = None,
    **kwargs: object,
) -> Medication:
    """Создаёт запись о лекарстве для питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        name: название препарата
        start_date: дата начала приёма
        today: текущая дата (для тестируемости); если None —
            используется UTC-дата на момент вызова
        **kwargs: доп. поля (dosage, frequency, end_date, notes, recorded_by).
            recorded_by обязателен.

    Возвращает:
        Medication: созданная запись. Если end_date передан и уже в прошлом
            относительно today — is_active автоматически выставляется в False.

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
    # Инвариант: завершённый курс (end_date в прошлом) не должен
    # считаться активным
    end_date = kwargs.get("end_date")
    if end_date is not None:
        effective_today = today or datetime.datetime.now(tz=datetime.UTC).date()
        if end_date < effective_today:  # type: ignore[operator]
            medication.is_active = False
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
    if "frequency" in kwargs and kwargs["frequency"] is not None:
        create_diff["frequency"] = kwargs["frequency"]
    if "end_date" in kwargs and kwargs["end_date"] is not None:
        create_diff["end_date"] = kwargs["end_date"]
    if "last_given_date" in kwargs and kwargs["last_given_date"] is not None:
        create_diff["last_given_date"] = kwargs["last_given_date"]
    if "notes" in kwargs and kwargs["notes"] is not None:
        create_diff["notes"] = kwargs["notes"]
    create_diff["is_active"] = medication.is_active
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
    today: datetime.date | None = None,
) -> list[Medication]:
    """Возвращает лекарства питомца с опциональным фильтром по активности.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        active_only: True -- только активные (is_active=True и
            end_date IS NULL или end_date >= today)
        today: текущая дата workspace (для фильтрации по end_date)

    Возвращает:
        list[Medication]: список лекарств
    """
    query = select(Medication).where(Medication.pet_id == pet_id)
    if active_only:
        query = query.where(Medication.is_active.is_(True))
        # Исключаем просроченные: end_date < today
        effective_today = (
            today
            if today is not None
            else datetime.datetime.now(tz=datetime.UTC).date()
        )
        query = query.where(
            Medication.end_date.is_(None) | (Medication.end_date >= effective_today)
        )
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
    limit: int = 10,
    offset: int = 0,
) -> list[Note]:
    """Возвращает заметки питомца с пагинацией, от новых к старым.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        limit: максимальное количество записей (по умолчанию 10)
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


# ═══════════════════════════════════════════════════════════════════════════════
# T016: Измерения (Measurement)
# ═══════════════════════════════════════════════════════════════════════════════

_VALID_MEASUREMENT_TYPES = {"temperature", "pulse", "respiration"}


async def add_measurement(
    session: AsyncSession,
    pet_id: int,
    measurement_type: str,
    value: Decimal,
    unit: str,
    measured_at: datetime.date,
    recorded_by: int | None = None,
) -> Measurement:
    """Создаёт запись физиологического измерения питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        measurement_type: тип измерения (temperature/pulse/respiration)
        value: числовое значение
        unit: единица измерения
        measured_at: дата измерения
        recorded_by: ID участника, записавшего измерение (обязательный)

    Возвращает:
        Measurement: созданная запись

    Ошибки:
        ValueError: если measurement_type не входит в допустимые значения

    Побочные эффекты:
        Добавляет Measurement в сессию, делает flush и пишет аудит create.
    """
    if measurement_type not in _VALID_MEASUREMENT_TYPES:
        raise ValueError(
            f"Недопустимый тип измерения: {measurement_type}. "
            f"Допустимые: {', '.join(sorted(_VALID_MEASUREMENT_TYPES))}"
        )
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    record = Measurement(
        pet_id=pet_id,
        measurement_type=measurement_type,
        value=value,
        unit=unit,
        measured_at=measured_at,
        recorded_by=valid_recorded_by,
    )
    session.add(record)
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="measurement",
        entity_id=record.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json={
            "pet_id": pet_id,
            "measurement_type": measurement_type,
            "value": value,
            "unit": unit,
            "measured_at": measured_at,
            "recorded_by": valid_recorded_by,
        },
    )

    logger.info(
        "Записано измерение %s=%.2f %s для питомца id=%d на %s",
        measurement_type,
        value,
        unit,
        pet_id,
        measured_at,
    )
    return record


async def get_measurements(
    session: AsyncSession,
    pet_id: int,
    measurement_type: str | None = None,
    limit: int = 10,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[Measurement]:
    """Возвращает измерения питомца с опциональными фильтрами.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        measurement_type: фильтр по типу измерения (None -- все типы)
        limit: максимальное количество записей (по умолчанию 10)
        start_date: начальная дата периода (None -- без ограничения)
        end_date: конечная дата периода (None -- без ограничения)

    Возвращает:
        list[Measurement]: список записей, отсортированных по measured_at DESC
    """
    query = select(Measurement).where(Measurement.pet_id == pet_id)
    if measurement_type is not None:
        query = query.where(Measurement.measurement_type == measurement_type)
    if start_date is not None:
        query = query.where(Measurement.measured_at >= start_date)
    if end_date is not None:
        query = query.where(Measurement.measured_at <= end_date)
    query = query.order_by(Measurement.measured_at.desc()).limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# T016: Визиты к ветеринару (VetVisit)
# ═══════════════════════════════════════════════════════════════════════════════

_VALID_VET_VISIT_STATUSES = {"planned", "completed"}


async def add_vet_visit(
    session: AsyncSession,
    pet_id: int,
    reason: str,
    visit_date: datetime.date,
    status: str = "planned",
    recorded_by: int | None = None,
    **kwargs: object,
) -> VetVisit:
    """Создаёт запись о визите к ветеринару.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        reason: причина визита
        visit_date: дата визита
        status: статус визита (planned/completed)
        recorded_by: ID участника, записавшего визит (обязательный)
        **kwargs: доп. поля (clinic, notes)

    Возвращает:
        VetVisit: созданная запись

    Ошибки:
        ValueError: если status не входит в допустимые значения

    Побочные эффекты:
        Добавляет VetVisit в сессию, делает flush и пишет аудит create.
    """
    if status not in _VALID_VET_VISIT_STATUSES:
        raise ValueError(
            f"Недопустимый статус визита: {status}. "
            f"Допустимые: {', '.join(sorted(_VALID_VET_VISIT_STATUSES))}"
        )
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    record = VetVisit(
        pet_id=pet_id,
        reason=reason,
        visit_date=visit_date,
        status=status,
        recorded_by=valid_recorded_by,
        **kwargs,
    )
    session.add(record)
    await session.flush()
    create_diff: dict[str, object] = {
        "pet_id": pet_id,
        "reason": reason,
        "visit_date": visit_date,
        "status": status,
        "recorded_by": valid_recorded_by,
    }
    if record.clinic is not None:
        create_diff["clinic"] = record.clinic
    await _log_health_change(
        session=session,
        entity_type="vet_visit",
        entity_id=record.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json=create_diff,
    )

    logger.info(
        "Записан визит к ветеринару '%s' для питомца id=%d на %s",
        reason,
        pet_id,
        visit_date,
    )
    return record


async def get_vet_visits(
    session: AsyncSession,
    pet_id: int,
    status: str | None = None,
) -> list[VetVisit]:
    """Возвращает визиты к ветеринару с опциональным фильтром по статусу.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        status: фильтр по статусу (None -- все статусы)

    Возвращает:
        list[VetVisit]: список записей, отсортированных по visit_date DESC
    """
    query = select(VetVisit).where(VetVisit.pet_id == pet_id)
    if status is not None:
        query = query.where(VetVisit.status == status)
    query = query.order_by(VetVisit.visit_date.desc())

    result = await session.execute(query)
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# T016: Наблюдения за состоянием (MoodLog)
# ═══════════════════════════════════════════════════════════════════════════════

_VALID_MOODS = {"excellent", "good", "normal", "poor"}
_VALID_APPETITES = {"good", "reduced", "none"}


async def add_mood_log(
    session: AsyncSession,
    pet_id: int,
    mood: str,
    appetite: str,
    log_date: datetime.date,
    recorded_by: int | None = None,
    **kwargs: object,
) -> MoodLog:
    """Создаёт запись наблюдения за состоянием питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        mood: настроение (excellent/good/normal/poor)
        appetite: аппетит (good/reduced/none)
        log_date: дата наблюдения
        recorded_by: ID участника, записавшего наблюдение (обязательный)
        **kwargs: доп. поля (notes)

    Возвращает:
        MoodLog: созданная запись

    Ошибки:
        ValueError: если mood или appetite не входят в допустимые значения

    Побочные эффекты:
        Добавляет MoodLog в сессию, делает flush и пишет аудит create.
    """
    if mood not in _VALID_MOODS:
        raise ValueError(
            f"Недопустимое настроение: {mood}. "
            f"Допустимые: {', '.join(sorted(_VALID_MOODS))}"
        )
    if appetite not in _VALID_APPETITES:
        raise ValueError(
            f"Недопустимый аппетит: {appetite}. "
            f"Допустимые: {', '.join(sorted(_VALID_APPETITES))}"
        )
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    record = MoodLog(
        pet_id=pet_id,
        mood=mood,
        appetite=appetite,
        log_date=log_date,
        recorded_by=valid_recorded_by,
        **kwargs,
    )
    session.add(record)
    await session.flush()
    await _log_health_change(
        session=session,
        entity_type="mood_log",
        entity_id=record.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json={
            "pet_id": pet_id,
            "mood": mood,
            "appetite": appetite,
            "log_date": log_date,
            "recorded_by": valid_recorded_by,
        },
    )

    logger.info(
        "Записано наблюдение (mood=%s, appetite=%s) для питомца id=%d на %s",
        mood,
        appetite,
        pet_id,
        log_date,
    )
    return record


async def get_mood_logs(
    session: AsyncSession,
    pet_id: int,
    limit: int = 10,
) -> list[MoodLog]:
    """Возвращает наблюдения за состоянием питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        limit: максимальное количество записей (по умолчанию 10)

    Возвращает:
        list[MoodLog]: список записей, отсортированных по log_date DESC
    """
    result = await session.execute(
        select(MoodLog)
        .where(MoodLog.pet_id == pet_id)
        .order_by(MoodLog.log_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════════
# T016: Циклы течки (HeatCycle)
# ═══════════════════════════════════════════════════════════════════════════════


async def add_heat_cycle(
    session: AsyncSession,
    pet_id: int,
    start_date: datetime.date,
    recorded_by: int | None = None,
    **kwargs: object,
) -> HeatCycle:
    """Создаёт запись о цикле течки.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        start_date: дата начала цикла
        recorded_by: ID участника, записавшего цикл (обязательный)
        **kwargs: доп. поля (end_date, notes)

    Возвращает:
        HeatCycle: созданная запись

    Побочные эффекты:
        Добавляет HeatCycle в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    # Базовая валидация: end_date не может быть раньше start_date
    end_date_val = kwargs.get("end_date")
    if end_date_val is not None:
        if not isinstance(end_date_val, datetime.date):
            raise TypeError("end_date должен быть datetime.date")
        if end_date_val < start_date:
            raise ValueError(
                "Некорректная хронология heat_cycle: end_date не может быть "
                "раньше start_date."
            )
    record = HeatCycle(
        pet_id=pet_id,
        start_date=start_date,
        recorded_by=valid_recorded_by,
        **kwargs,
    )
    session.add(record)
    await session.flush()
    create_diff: dict[str, object] = {
        "pet_id": pet_id,
        "start_date": start_date,
        "recorded_by": valid_recorded_by,
    }
    if record.end_date is not None:
        create_diff["end_date"] = record.end_date
    await _log_health_change(
        session=session,
        entity_type="heat_cycle",
        entity_id=record.id,
        pet_id=pet_id,
        action="create",
        actor_id=valid_recorded_by,
        diff_json=create_diff,
    )

    logger.info(
        "Записан цикл течки для питомца id=%d с %s",
        pet_id,
        start_date,
    )
    return record


async def get_heat_cycles(
    session: AsyncSession,
    pet_id: int,
) -> list[HeatCycle]:
    """Возвращает циклы течки питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        list[HeatCycle]: список записей, отсортированных по start_date DESC
    """
    result = await session.execute(
        select(HeatCycle)
        .where(HeatCycle.pet_id == pet_id)
        .order_by(HeatCycle.start_date.desc())
    )
    return list(result.scalars().all())


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
