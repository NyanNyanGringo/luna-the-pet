"""
Сервис журнала аудита: запись и чтение истории изменений сущностей.

Все функции принимают AsyncSession первым аргументом
и не управляют транзакциями (commit/rollback -- ответственность вызывающего).
"""

from __future__ import annotations

import logging

from backend.app.db.models.audit import ChangeLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# T109: Аудит
# ═══════════════════════════════════════════════════════════════════════════════


async def log_change(
    session: AsyncSession,
    entity_type: str,
    entity_id: int,
    action: str,
    actor_id: int,
    workspace_id: int | None = None,
    diff_json: dict[str, object] | None = None,
) -> ChangeLog:
    """Записывает изменение сущности в журнал аудита.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        entity_type: тип сущности (pet, vaccination, weight_record и т.д.)
        entity_id: ID изменённой сущности
        action: тип действия (create, update, delete)
        actor_id: ID участника, выполнившего действие (обязательный параметр)
        workspace_id: ID workspace для tenant-изоляции (nullable для system rows)
        diff_json: детали изменений в формате JSON (nullable)

    Возвращает:
        ChangeLog: созданная запись аудита

    Побочные эффекты:
        Добавляет ChangeLog в сессию, делает flush.

    Исключения:
        ValueError: если actor_id равен None.
        TypeError: если actor_id не int или передан bool.
    """
    valid_actor_id = _require_actor_id(actor_id)

    entry = ChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=valid_actor_id,
        workspace_id=workspace_id,
        diff_json=diff_json,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "Аудит: %s %s id=%d (actor=%s)",
        action,
        entity_type,
        entity_id,
        valid_actor_id,
    )
    return entry


def _require_actor_id(actor_id: object | None) -> int:
    """Проверяет обязательный actor_id и не принимает bool как int."""
    if actor_id is None:
        raise ValueError("Параметр actor_id обязателен и не может быть None.")
    if isinstance(actor_id, bool) or not isinstance(actor_id, int):
        raise TypeError("Параметр actor_id должен быть int.")
    return actor_id


async def get_entity_history(
    session: AsyncSession,
    entity_type: str,
    entity_id: int,
) -> list[ChangeLog]:
    """Возвращает историю изменений сущности, от новых к старым.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        entity_type: тип сущности для фильтрации
        entity_id: ID сущности для фильтрации

    Возвращает:
        list[ChangeLog]: список записей, отсортированных по changed_at DESC
    """
    # Сортировка по id DESC дополнительно к changed_at DESC,
    # т.к. записи в одной транзакции могут иметь одинаковый changed_at.
    result = await session.execute(
        select(ChangeLog)
        .where(
            ChangeLog.entity_type == entity_type,
            ChangeLog.entity_id == entity_id,
        )
        .order_by(ChangeLog.changed_at.desc(), ChangeLog.id.desc())
    )
    return list(result.scalars().all())
