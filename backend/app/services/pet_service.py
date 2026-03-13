"""
Сервис управления питомцами: CRUD, поиск по имени и тексту.

Все функции принимают AsyncSession первым аргументом
и не управляют транзакциями (commit/rollback -- ответственность вызывающего).
"""

from __future__ import annotations

import datetime
import logging

from backend.app.db.models.pet import Pet
from backend.app.services import audit_service
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PET_SERVICE_FORBIDDEN_UPDATE_FIELDS = {
    "id",
    "workspace_id",
    "created_by",
    "is_active",
    "created_at",
}


# ═══════════════════════════════════════════════════════════════════════════════
# T026: CRUD питомцев
# ═══════════════════════════════════════════════════════════════════════════════


async def get_workspace_pets(
    session: AsyncSession,
    workspace_id: int,
) -> list[Pet]:
    """Возвращает всех активных питомцев workspace.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace

    Возвращает:
        list[Pet]: список активных питомцев workspace (может быть пустым)
    """
    result = await session.execute(
        select(Pet).where(Pet.workspace_id == workspace_id, Pet.is_active.is_(True))
    )
    return list(result.scalars().all())


async def get_pet_by_id(
    session: AsyncSession,
    pet_id: int,
) -> Pet | None:
    """Ищет питомца по ID.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        Pet | None: найденный питомец или None
    """
    result = await session.execute(select(Pet).where(Pet.id == pet_id))
    return result.scalar_one_or_none()


async def get_pet_by_name(
    session: AsyncSession,
    workspace_id: int,
    name: str,
) -> Pet | None:
    """Ищет питомца по имени (case-insensitive) в указанном workspace.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        name: имя питомца (без учёта регистра)

    Возвращает:
        Pet | None: найденный питомец или None
    """
    result = await session.execute(
        select(Pet).where(
            Pet.workspace_id == workspace_id,
            Pet.is_active.is_(True),
            func.lower(Pet.name) == name.lower(),
        )
    )
    return result.scalar_one_or_none()


async def resolve_pet_from_text(
    session: AsyncSession,
    workspace_id: int,
    text: str,
) -> Pet | None:
    """Ищет имя питомца в произвольном тексте.

    Загружает все имена активных питомцев workspace и проверяет,
    встречается ли какое-либо из них в тексте (case-insensitive).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        text: произвольный текст для поиска имени питомца

    Возвращает:
        Pet | None: первый найденный питомец или None
    """
    pets = await get_workspace_pets(session, workspace_id)
    return _find_pet_name_in_text(pets, text)


def _find_pet_name_in_text(pets: list[Pet], text: str) -> Pet | None:
    """Ищет имя любого питомца из списка внутри текста (case-insensitive).

    Сначала проверяет точное вхождение имени в текст.
    Если не найдено -- проверяет вхождение основы имени (без последней буквы)
    в слова текста, чтобы учесть склонение имён в русском языке
    (например, "Луна" -> "Луну", "Луне", "Луной").

    Аргументы:
        pets: список питомцев для поиска
        text: текст, в котором ищем имя

    Возвращает:
        Pet | None: первый питомец, чьё имя найдено, или None
    """
    text_lower = text.lower()

    # Сначала ищем точное вхождение имени
    for pet in pets:
        if pet.name.lower() in text_lower:
            return pet

    # Затем ищем по основе имени (без последней буквы) для учёта склонения.
    # Минимальная длина основы -- 3 символа, чтобы избежать ложных срабатываний.
    min_stem_length = 3
    words = text_lower.split()
    for pet in pets:
        stem = pet.name.lower()[:-1]
        if len(stem) >= min_stem_length:
            for word in words:
                if word.startswith(stem):
                    return pet

    return None


async def create_pet(
    session: AsyncSession,
    workspace_id: int,
    name: str,
    species: str,
    actor_id: int | None,
    **kwargs: object,
) -> Pet:
    """Создаёт нового питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        name: имя питомца
        species: вид животного (dog/cat/other)
        actor_id: user-origin ID, от имени которого выполняется создание
        **kwargs: дополнительные поля (breed, birth_date и т.д.)

    Возвращает:
        Pet: созданный питомец

    Ошибки:
        ValueError: если actor_id равен None

    Побочные эффекты:
        Добавляет Pet в сессию, делает flush и пишет запись аудита.
    """
    created_by = _require_actor_id(actor_id)
    pet = Pet(
        workspace_id=workspace_id,
        name=name,
        species=species,
        created_by=created_by,
        **kwargs,
    )
    session.add(pet)
    await session.flush()
    await _log_pet_change(
        session=session,
        pet_id=pet.id,
        action="create",
        actor_id=created_by,
        workspace_id=workspace_id,
        diff_json=_build_create_diff(
            workspace_id=workspace_id,
            name=name,
            species=species,
            created_by=created_by,
            optional_fields=kwargs,
        ),
    )

    logger.info(
        "Создан питомец '%s' (вид=%s) в workspace %d",
        name,
        species,
        workspace_id,
    )
    return pet


async def update_pet(
    session: AsyncSession,
    pet_id: int,
    actor_id: int | None,
    **fields: object,
) -> Pet:
    """Обновляет поля питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        actor_id: user-origin ID, от имени которого выполняется обновление
        **fields: поля для обновления (breed, is_neutered и т.д.)

    Возвращает:
        Pet: обновлённый питомец

    Ошибки:
        ValueError: если actor_id равен None
        ValueError: если питомец с указанным ID не найден

    Побочные эффекты:
        Обновляет атрибуты Pet, делает flush и пишет запись аудита.
    """
    valid_actor_id = _require_actor_id(actor_id)
    _validate_update_pet_fields(fields)
    pet = await _get_pet_or_raise(session, pet_id)
    changed_fields = _get_changed_fields(pet, fields)
    _apply_fields(pet, changed_fields)
    await session.flush()
    await _log_pet_change(
        session=session,
        pet_id=pet.id,
        action="update",
        actor_id=valid_actor_id,
        workspace_id=pet.workspace_id,
        diff_json=_to_audit_diff(changed_fields),
    )

    logger.info("Обновлён питомец id=%d, поля: %s", pet_id, list(fields.keys()))
    return pet


async def _get_pet_or_raise(
    session: AsyncSession,
    pet_id: int,
) -> Pet:
    """Возвращает питомца по ID или бросает ValueError.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца

    Возвращает:
        Pet: найденный питомец

    Ошибки:
        ValueError: если питомец не найден
    """
    pet = await get_pet_by_id(session, pet_id)
    if pet is None:
        raise ValueError(f"Питомец с id={pet_id} не найден")
    return pet


def _apply_fields(entity: object, fields: dict[str, object]) -> None:
    """Устанавливает атрибуты объекта из словаря.

    Аргументы:
        entity: объект для обновления
        fields: словарь {имя_атрибута: значение}
    """
    for key, value in fields.items():
        setattr(entity, key, value)


def _require_actor_id(actor_id: int | None) -> int:
    """Проверяет, что actor_id задан, и возвращает его.

    Аргументы:
        actor_id: user-origin ID инициатора изменения

    Возвращает:
        int: валидный actor_id

    Ошибки:
        ValueError: если actor_id равен None
        TypeError: если actor_id не int или имеет тип bool
    """
    if actor_id is None:
        raise ValueError("Параметр actor_id обязателен и не может быть None.")
    if isinstance(actor_id, bool) or not isinstance(actor_id, int):
        raise TypeError("Параметр actor_id должен быть int.")
    return actor_id


def _validate_update_pet_fields(fields: dict[str, object]) -> None:
    """Проверяет, что update_pet не содержит служебные/неизвестные ключи."""
    unexpected_fields = {
        field_name
        for field_name in fields
        if field_name in _PET_SERVICE_FORBIDDEN_UPDATE_FIELDS
        or not hasattr(Pet, field_name)
    }
    if unexpected_fields:
        unexpected_fields_text = ", ".join(sorted(unexpected_fields))
        raise ValueError(f"Недопустимые поля для update_pet: {unexpected_fields_text}.")


def _get_changed_fields(entity: object, fields: dict[str, object]) -> dict[str, object]:
    """Возвращает только реально изменённые значения полей.

    Аргументы:
        entity: целевой объект с текущими значениями
        fields: новые значения полей

    Возвращает:
        dict[str, object]: только поля, где новое значение отличается от текущего
    """
    changed_fields: dict[str, object] = {}
    for key, value in fields.items():
        if getattr(entity, key) != value:
            changed_fields[key] = value
    return changed_fields


def _build_create_diff(
    workspace_id: int,
    name: str,
    species: str,
    created_by: int,
    optional_fields: dict[str, object],
) -> dict[str, object]:
    """Собирает минимальный diff_json для audit create.

    Аргументы:
        workspace_id: ID workspace питомца
        name: имя питомца
        species: вид питомца
        created_by: actor_id, записанный в created_by
        optional_fields: реально переданные необязательные поля create

    Возвращает:
        dict[str, object]: JSON-совместимый diff для события create
    """
    create_diff = {
        "name": name,
        "species": species,
        "workspace_id": workspace_id,
        "created_by": created_by,
    }
    create_diff.update(optional_fields)
    return _to_audit_diff(create_diff)


def _to_audit_diff(fields: dict[str, object]) -> dict[str, object]:
    """Приводит значения diff_json к JSON-совместимому виду.

    Аргументы:
        fields: произвольный словарь значений для аудита

    Возвращает:
        dict[str, object]: словарь, безопасный для JSON-поля ChangeLog
    """
    return {key: _to_audit_value(value) for key, value in fields.items()}


def _to_audit_value(value: object) -> object:
    """Преобразует значение к формату, совместимому с JSON.

    Аргументы:
        value: исходное значение поля

    Возвращает:
        object: сериализуемое значение для JSON
    """
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    return value


async def _log_pet_change(
    session: AsyncSession,
    pet_id: int,
    action: str,
    actor_id: int,
    workspace_id: int,
    diff_json: dict[str, object],
) -> None:
    """Пишет запись в аудит по изменению питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        action: тип действия в аудите (create/update)
        actor_id: user-origin ID инициатора
        workspace_id: ID workspace питомца
        diff_json: минимальный diff изменённых полей
    """
    await audit_service.log_change(
        session=session,
        entity_type="pet",
        entity_id=pet_id,
        action=action,
        actor_id=actor_id,
        workspace_id=workspace_id,
        diff_json=diff_json,
    )
