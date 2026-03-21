"""
Сервис управления питанием питомца: диеты и записи кормлений.

Все функции принимают AsyncSession первым аргументом
и не управляют транзакциями (commit/rollback -- ответственность вызывающего).
"""

from __future__ import annotations

import datetime
import logging

from backend.app.db.models.nutrition import DietRecord, FeedingEntry
from backend.app.db.models.pet import Pet
from backend.app.services import audit_service
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# T028: Диеты
# ═══════════════════════════════════════════════════════════════════════════════


async def add_diet_record(
    session: AsyncSession,
    pet_id: int,
    food_brand: str,
    start_date: datetime.date,
    recorded_by: object | None,
    **kwargs: object,
) -> DietRecord:
    """Создаёт запись о диете питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        food_brand: бренд корма
        start_date: дата начала рациона
        recorded_by: ID участника, создающего запись (обязательный)
        **kwargs: доп. поля (food_type, end_date, notes)

    Возвращает:
        DietRecord: созданная запись

    Ошибки:
        ValueError: если recorded_by отсутствует/None
        TypeError: если recorded_by не int
        ValueError: если start_date раньше открытой текущей диеты

    Побочные эффекты:
        При создании открытой диеты автоматически закрывает предыдущую открытую
        (end_date = new start_date - 1 day), пишет аудит close/create и делает flush.
    """
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    workspace_id = await _get_workspace_id_for_pet(session, pet_id)
    has_explicit_end_date = kwargs.get("end_date") is not None
    # Базовая валидация: end_date не может быть раньше start_date
    if has_explicit_end_date:
        _end_date_raw = kwargs["end_date"]
        if not isinstance(_end_date_raw, datetime.date):
            raise TypeError("end_date должен быть datetime.date")
        _validate_diet_end_date(end_date=_end_date_raw, start_date=start_date)
    open_diets = await _get_open_diets(session, pet_id)
    if open_diets and not has_explicit_end_date:
        _validate_diet_chronology(start_date, open_diets[0].start_date)
        # Закрываем старую диету днём раньше новой, чтобы не было пересечения
        close_date = start_date - datetime.timedelta(days=1)
        for open_diet in open_diets:
            await _close_open_diet(
                session=session,
                diet=open_diet,
                end_date=close_date,
                actor_id=valid_recorded_by,
                workspace_id=workspace_id,
            )
    elif open_diets and has_explicit_end_date:
        # Проверяем пересечение с открытыми диетами
        # Тип уже проверен выше в _validate_diet_end_date
        new_end_date: datetime.date = kwargs["end_date"]  # type: ignore[assignment]
        for open_diet in open_diets:
            if new_end_date >= open_diet.start_date:
                raise ValueError(
                    "Некорректная хронология diet_record: "
                    "новая диета пересекается с открытой записью."
                )

    diet = DietRecord(
        pet_id=pet_id,
        food_brand=food_brand,
        start_date=start_date,
        recorded_by=valid_recorded_by,
        **kwargs,
    )
    session.add(diet)
    await session.flush()
    diff_json_data: dict[str, object] = {
        "pet_id": pet_id,
        "food_brand": food_brand,
        "start_date": start_date,
        "recorded_by": valid_recorded_by,
    }
    if diet.food_type is not None:
        diff_json_data["food_type"] = diet.food_type
    if diet.end_date is not None:
        diff_json_data["end_date"] = diet.end_date
    if diet.notes is not None:
        diff_json_data["notes"] = diet.notes
    await _log_diet_change(
        session=session,
        entity_id=diet.id,
        action="create",
        actor_id=valid_recorded_by,
        workspace_id=workspace_id,
        diff_json=diff_json_data,
    )

    logger.info(
        "Создана диета '%s' для питомца id=%d с %s",
        food_brand,
        pet_id,
        start_date,
    )
    return diet


async def get_diet_history(
    session: AsyncSession,
    pet_id: int,
) -> list[DietRecord]:
    """Возвращает историю диет питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        list[DietRecord]: список записей, отсортированных по start_date DESC
            (от новых к старым)
    """
    result = await session.execute(
        select(DietRecord)
        .where(DietRecord.pet_id == pet_id)
        .order_by(DietRecord.start_date.desc())
    )
    return list(result.scalars().all())


async def get_current_diet(
    session: AsyncSession,
    pet_id: int,
    today: datetime.date | None = None,
) -> DietRecord | None:
    """Возвращает текущую диету питомца.

    Текущей считается диета, у которой end_date IS NULL
    или end_date >= today (ещё не истекла).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        today: текущая дата workspace (для сравнения с end_date)

    Возвращает:
        DietRecord | None: текущая диета или None, если все закрыты
    """
    query = select(DietRecord).where(DietRecord.pet_id == pet_id)
    if today is not None:
        query = query.where(
            DietRecord.start_date <= today,
            DietRecord.end_date.is_(None) | (DietRecord.end_date >= today),
        )
    else:
        query = query.where(DietRecord.end_date.is_(None))
    result = await session.execute(
        query.order_by(DietRecord.start_date.desc(), DietRecord.id.desc()).limit(2)
    )
    current_diets = list(result.scalars().all())
    if len(current_diets) > 1:
        logger.error(
            "Нарушение данных diet_record: у питомца id=%d несколько текущих диет (%d)",
            pet_id,
            len(current_diets),
        )
    return current_diets[0] if current_diets else None


async def end_diet_record(
    session: AsyncSession,
    diet_record_id: int,
    end_date: datetime.date,
    actor_id: object | None,
) -> DietRecord:
    """Закрывает запись о диете, устанавливая end_date.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        diet_record_id: ID записи о диете
        end_date: дата окончания рациона
        actor_id: ID участника, закрывшего запись (обязательный)

    Возвращает:
        DietRecord: обновлённая запись

    Ошибки:
        ValueError: если actor_id равен None
        TypeError: если actor_id не int
        ValueError: если запись о диете не найдена

    Побочные эффекты:
        Устанавливает end_date, делает flush и пишет аудит close.
    """
    valid_actor_id = _require_actor_id(actor_id)
    diet = await _get_diet_record_or_raise(session, diet_record_id)
    workspace_id = await _get_workspace_id_for_pet(session, diet.pet_id)
    _validate_diet_end_date(end_date=end_date, start_date=diet.start_date)
    diet.end_date = end_date
    await session.flush()
    await _log_diet_change(
        session=session,
        entity_id=diet.id,
        action="close",
        actor_id=valid_actor_id,
        workspace_id=workspace_id,
        diff_json={"end_date": end_date},
    )

    logger.info(
        "Закрыта диета id=%d, end_date=%s",
        diet_record_id,
        end_date,
    )
    return diet


def _validate_diet_end_date(
    end_date: datetime.date,
    start_date: datetime.date,
) -> None:
    """Проверяет, что дата закрытия диеты не раньше её даты начала."""
    if end_date < start_date:
        raise ValueError(
            "Некорректная хронология diet_record: end_date не может быть "
            "раньше start_date."
        )


async def _get_diet_record_or_raise(
    session: AsyncSession,
    diet_record_id: int,
) -> DietRecord:
    """Возвращает запись о диете по ID или бросает ValueError.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        diet_record_id: ID записи о диете

    Возвращает:
        DietRecord: найденная запись

    Ошибки:
        ValueError: если запись не найдена
    """
    result = await session.execute(
        select(DietRecord).where(DietRecord.id == diet_record_id)
    )
    diet = result.scalar_one_or_none()

    if diet is None:
        raise ValueError(f"Запись о диете с id={diet_record_id} не найдена")

    return diet


def _require_actor_id(
    actor_id: object | None,
    parameter_name: str = "actor_id",
) -> int:
    """Проверяет обязательный user-origin идентификатор и возвращает его.

    Аргументы:
        actor_id: значение ID инициатора изменения
        parameter_name: имя параметра для текста ошибки

    Возвращает:
        int: валидный ID инициатора

    Ошибки:
        ValueError: если actor_id равен None
        TypeError: если actor_id не int
    """
    if actor_id is None:
        raise ValueError(f"Параметр {parameter_name} обязателен и не может быть None.")
    if isinstance(actor_id, bool) or not isinstance(actor_id, int):
        raise TypeError(f"Параметр {parameter_name} должен быть int.")
    return actor_id


def _open_diets_query(pet_id: int) -> Select[tuple[DietRecord]]:
    """Возвращает базовый запрос открытых диет питомца (end_date IS NULL)."""
    return select(DietRecord).where(
        DietRecord.pet_id == pet_id,
        DietRecord.end_date.is_(None),
    )


async def _get_open_diets(
    session: AsyncSession,
    pet_id: int,
) -> list[DietRecord]:
    """Возвращает все открытые диеты питомца от новых к старым.

    Если в данных обнаружено несколько открытых диет, пишет лог об ошибке
    целостности.
    """
    result = await session.execute(
        _open_diets_query(pet_id).order_by(
            DietRecord.start_date.desc(), DietRecord.id.desc()
        )
    )
    open_diets = list(result.scalars().all())
    if len(open_diets) > 1:
        logger.error(
            "Нарушение данных diet_record: у питомца id=%d "
            "несколько открытых диет (%d)",
            pet_id,
            len(open_diets),
        )
    return open_diets


def _validate_diet_chronology(
    new_start_date: datetime.date,
    current_start_date: datetime.date,
) -> None:
    """Проверяет хронологию дат при создании новой диеты.

    Ошибки:
        ValueError: если новая start_date раньше start_date открытой диеты
    """
    if new_start_date < current_start_date:
        raise ValueError(
            "Некорректная хронология diet_record: start_date новой диеты "
            "не может быть раньше start_date текущей открытой записи."
        )


async def _close_open_diet(
    session: AsyncSession,
    diet: DietRecord,
    end_date: datetime.date,
    actor_id: int,
    workspace_id: int,
) -> None:
    """Закрывает открытую диету и пишет аудит close."""
    diet.end_date = end_date
    await session.flush()
    await _log_diet_change(
        session=session,
        entity_id=diet.id,
        action="close",
        actor_id=actor_id,
        workspace_id=workspace_id,
        diff_json={"end_date": end_date},
    )


async def _log_diet_change(
    session: AsyncSession,
    entity_id: int,
    action: str,
    actor_id: int,
    workspace_id: int,
    diff_json: dict[str, object],
) -> None:
    """Пишет запись аудита по изменениям DietRecord."""
    await audit_service.log_change(
        session=session,
        entity_type="diet_record",
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        workspace_id=workspace_id,
        diff_json=_to_audit_diff(diff_json),
    )


def _to_audit_diff(fields: dict[str, object]) -> dict[str, object]:
    """Преобразует словарь diff_json к JSON-safe виду."""
    return {key: _to_audit_value(value) for key, value in fields.items()}


def _to_audit_value(value: object) -> object:
    """Преобразует значение в формат, безопасный для JSON."""
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_audit_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_audit_value(item) for item in value]
    return value


# ═══════════════════════════════════════════════════════════════════════════════
# T028: Записи кормлений
# ═══════════════════════════════════════════════════════════════════════════════


async def add_feeding_entry(
    session: AsyncSession,
    pet_id: int,
    fed_at: datetime.datetime,
    food_description: str,
    recorded_by: object | None,
    **kwargs: object,
) -> FeedingEntry:
    """Создаёт запись о кормлении питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        fed_at: дата и время кормления (timezone-aware)
        food_description: описание еды
        recorded_by: ID участника, создающего запись (обязательный)
        **kwargs: доп. поля (portion_size)

    Возвращает:
        FeedingEntry: созданная запись

    Ошибки:
        ValueError: если recorded_by отсутствует/None
        TypeError: если recorded_by не int или bool

    Побочные эффекты:
        Добавляет FeedingEntry в сессию, делает flush и пишет аудит create.
    """
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    workspace_id = await _get_workspace_id_for_pet(session, pet_id)
    valid_fed_at = _require_timezone_aware_datetime(fed_at, "fed_at")
    entry = FeedingEntry(
        pet_id=pet_id,
        fed_at=valid_fed_at,
        food_description=food_description,
        recorded_by=valid_recorded_by,
        **kwargs,
    )
    session.add(entry)
    await session.flush()
    diff_json_data: dict[str, object] = {
        "pet_id": pet_id,
        "fed_at": valid_fed_at,
        "food_description": food_description,
        "recorded_by": valid_recorded_by,
    }
    if entry.portion_size is not None:
        diff_json_data["portion_size"] = entry.portion_size
    await _log_feeding_change(
        session=session,
        entity_id=entry.id,
        action="create",
        actor_id=valid_recorded_by,
        workspace_id=workspace_id,
        diff_json=diff_json_data,
    )

    logger.info(
        "Записано кормление питомца id=%d в %s",
        pet_id,
        valid_fed_at,
    )
    return entry


def _require_timezone_aware_datetime(
    value: object,
    parameter_name: str,
) -> datetime.datetime:
    """Проверяет, что datetime содержит timezone offset."""
    if not isinstance(value, datetime.datetime):
        raise TypeError(f"Параметр {parameter_name} должен быть datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"Параметр {parameter_name} должен быть timezone-aware "
            "ISO datetime с offset."
        )
    return value


async def _log_feeding_change(
    session: AsyncSession,
    entity_id: int,
    action: str,
    actor_id: int,
    workspace_id: int,
    diff_json: dict[str, object],
) -> None:
    """Пишет запись аудита по изменениям FeedingEntry."""
    await audit_service.log_change(
        session=session,
        entity_type="feeding_entry",
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


async def get_feeding_entries(
    session: AsyncSession,
    pet_id: int,
    limit: int = 20,
    since_dt: datetime.datetime | None = None,
    until_dt: datetime.datetime | None = None,
) -> list[FeedingEntry]:
    """Возвращает записи кормлений питомца, от новых к старым.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        limit: максимальное количество записей (по умолчанию 20)
        since_dt: если указан, возвращает только кормления начиная с этого
            момента (timezone-aware datetime)
        until_dt: если указан, возвращает только кормления до этого
            момента включительно (timezone-aware datetime)

    Возвращает:
        list[FeedingEntry]: список записей, отсортированных по fed_at DESC
    """
    query = select(FeedingEntry).where(FeedingEntry.pet_id == pet_id)
    if since_dt is not None:
        query = query.where(FeedingEntry.fed_at >= since_dt)
    if until_dt is not None:
        query = query.where(FeedingEntry.fed_at <= until_dt)
    query = query.order_by(FeedingEntry.fed_at.desc())
    query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())
