"""
Модель журнала аудита (ChangeLog).

Записывает все изменения сущностей (create, update, delete) с указанием
кто, когда и что изменил. diff_json хранит детали изменений в формате JSON.
Поддерживает привязку к workspace (мультитенантность).
"""

import datetime

from backend.app.db.base import Base
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class ChangeLog(Base):
    """Журнал аудита изменений сущностей.

    Поля:
        id: автоинкрементный PK
        entity_type: тип сущности (pet, vaccination, weight_record и т.д.)
        entity_id: ID изменённой сущности
        action: тип действия (create, update, delete)
        actor_id: Telegram user ID (кто выполнил, nullable)
        workspace_id: FK -> workspace.id (в каком workspace произошло, nullable)
        changed_at: дата изменения (timezone-aware, server_default)
        diff_json: детали изменений в формате JSON (nullable)

    Индексы:
        ix_changelog_entity: (entity_type, entity_id) — поиск по сущности
        ix_changelog_actor: (actor_id) — поиск по автору
        ix_changelog_changed_at: (changed_at) — поиск по дате
    """

    __tablename__ = "change_log"

    __table_args__ = (
        Index("ix_changelog_entity", "entity_type", "entity_id"),
        Index("ix_changelog_actor", "actor_id"),
        Index("ix_changelog_changed_at", "changed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    changed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    diff_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )
