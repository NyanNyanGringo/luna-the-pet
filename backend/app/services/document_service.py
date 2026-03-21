"""
Сервис управления документами питомца: справки, результаты анализов, снимки.

Все функции принимают AsyncSession первым аргументом
и не управляют транзакциями (commit/rollback -- ответственность вызывающего).
"""

from __future__ import annotations

import datetime
import logging

from backend.app.db.models.documents import Document
from backend.app.db.models.pet import Pet
from backend.app.services import audit_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_VALID_DOCUMENT_TYPES = {"passport", "analysis", "certificate", "other"}


# ═══════════════════════════════════════════════════════════════════════════════
# T017: Документы
# ═══════════════════════════════════════════════════════════════════════════════


async def add_document(
    session: AsyncSession,
    pet_id: int,
    document_type: str,
    url: str,
    recorded_by: int | None = None,
    **kwargs: object,
) -> Document:
    """Создаёт запись о документе питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        document_type: каноничный тип документа
            (passport, analysis, certificate, other)
        url: ссылка на документ (непустая строка)
        recorded_by: ID участника, создающего запись (обязательный)
        **kwargs: доп. поля (issued_date, description)

    Возвращает:
        Document: созданная запись

    Ошибки:
        ValueError: если document_type не из канонического набора
        ValueError: если url пустой
        ValueError: если recorded_by отсутствует/None

    Побочные эффекты:
        Добавляет Document в сессию, делает flush и пишет аудит create.
    """
    if document_type not in _VALID_DOCUMENT_TYPES:
        raise ValueError(
            f"Недопустимый document_type: {document_type}. "
            f"Допустимые: {', '.join(sorted(_VALID_DOCUMENT_TYPES))}"
        )
    if not url or not isinstance(url, str) or not url.strip():
        raise ValueError("Параметр url обязателен и не может быть пустым.")
    valid_recorded_by = _require_actor_id(recorded_by, "recorded_by")
    workspace_id = await _get_workspace_id_for_pet(session, pet_id)
    document = Document(
        pet_id=pet_id,
        document_type=document_type,
        url=url,
        recorded_by=valid_recorded_by,
        **kwargs,
    )
    session.add(document)
    await session.flush()
    create_diff: dict[str, object] = {
        "pet_id": pet_id,
        "document_type": document_type,
        "url": url,
        "recorded_by": valid_recorded_by,
    }
    if document.issued_date is not None:
        create_diff["issued_date"] = document.issued_date
    if document.description is not None:
        create_diff["description"] = document.description
    await audit_service.log_change(
        session=session,
        entity_type="document",
        entity_id=document.id,
        action="create",
        actor_id=valid_recorded_by,
        workspace_id=workspace_id,
        diff_json=_to_audit_diff(create_diff),
    )

    logger.info(
        "Создан документ '%s' для питомца id=%d",
        document_type,
        pet_id,
    )
    return document


async def get_documents(
    session: AsyncSession,
    pet_id: int,
    document_type: str | None = None,
) -> list[Document]:
    """Возвращает документы питомца с опциональным фильтром по типу.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        document_type: фильтр по типу документа (None -- все типы)

    Возвращает:
        list[Document]: список записей, отсортированных по created_at DESC
    """
    query = select(Document).where(Document.pet_id == pet_id)
    if document_type is not None:
        query = query.where(Document.document_type == document_type)
    query = query.order_by(Document.created_at.desc())

    result = await session.execute(query)
    return list(result.scalars().all())


def _require_actor_id(
    actor_id: object | None,
    parameter_name: str = "actor_id",
) -> int:
    """Проверяет обязательный user-origin идентификатор и возвращает его."""
    if actor_id is None:
        raise ValueError(f"Параметр {parameter_name} обязателен и не может быть None.")
    if isinstance(actor_id, bool) or not isinstance(actor_id, int):
        raise TypeError(f"Параметр {parameter_name} должен быть int.")
    return actor_id


async def _get_workspace_id_for_pet(session: AsyncSession, pet_id: int) -> int:
    """Возвращает workspace_id питомца или бросает ValueError."""
    workspace_id = await session.scalar(
        select(Pet.workspace_id).where(Pet.id == pet_id),
    )
    if workspace_id is None:
        raise ValueError(f"Питомец с id={pet_id} не найден")
    return workspace_id


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
