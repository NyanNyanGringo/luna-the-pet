"""
Мультитенантные модели workspace: Workspace, WorkspaceMember, WorkspaceSettings.

Workspace — замена singleton Family. Каждый workspace привязан к одной
Telegram-группе через telegram_chat_id. Поддерживает soft-delete (is_active).

WorkspaceMember — участник workspace с soft-delete (is_active/left_at).
WorkspaceSettings — таймзона и локаль workspace (one-to-one).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from backend.app.db.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from backend.app.db.models.pet import Pet


# ── Workspace (мультитенантная замена Family) ────────────────────────────────


class Workspace(Base):
    """Рабочее пространство, привязанное к Telegram-группе.

    Поля:
        id: автоинкрементный PK
        telegram_chat_id: ID Telegram-группы (BigInteger, UNIQUE, NOT NULL)
        title: название группы, NOT NULL, до 255 символов
        is_active: активен ли workspace (soft-delete, default True)
        created_at: дата создания (timezone-aware, server_default)
        updated_at: дата последнего обновления (server_default, onupdate)

    Связи:
        members: список участников workspace
        pets: список питомцев workspace
        settings: настройки workspace (one-to-one)
    """

    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # --- Связи ---
    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace",
    )
    pets: Mapped[list[Pet]] = relationship(
        back_populates="workspace",
    )
    settings: Mapped[WorkspaceSettings | None] = relationship(
        back_populates="workspace",
        uselist=False,
    )


# ── WorkspaceMember (участник workspace) ─────────────────────────────────────


class WorkspaceMember(Base):
    """Участник workspace с поддержкой soft-delete.

    Поля:
        id: автоинкрементный PK
        workspace_id: FK -> workspace.id (CASCADE), NOT NULL
        telegram_user_id: Telegram user ID (BigInteger, NOT NULL)
        telegram_username: Telegram username (nullable), до 255 символов
        telegram_first_name: имя в Telegram (nullable), до 255 символов
        is_active: активен ли участник (soft-delete, default True)
        joined_at: дата присоединения (timezone-aware, server_default)
        left_at: дата выхода (nullable, default None)

    Ограничения:
        UniqueConstraint: (workspace_id, telegram_user_id)

    Связи:
        workspace: обратная связь с Workspace
    """

    __tablename__ = "workspace_member"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "telegram_user_id",
            name="uq_workspace_member_workspace_user",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    telegram_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    telegram_first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    joined_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    left_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # --- Связи ---
    workspace: Mapped[Workspace] = relationship(back_populates="members")


# ── WorkspaceSettings (настройки workspace) ──────────────────────────────────


class WorkspaceSettings(Base):
    """Настройки workspace: таймзона и локаль.

    Поля:
        id: автоинкрементный PK
        workspace_id: FK -> workspace.id (CASCADE), UNIQUE, NOT NULL
        timezone: IANA-таймзона (default 'Europe/Moscow'), до 50 символов
        locale: локаль (default 'ru'), до 10 символов

    Связи:
        workspace: обратная связь с Workspace
    """

    __tablename__ = "workspace_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Europe/Moscow",
    )
    locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="ru",
    )

    # --- Связи ---
    workspace: Mapped[Workspace] = relationship(back_populates="settings")
