"""
Модель питомца (Pet) с полным набором полей профиля.

Поддерживает soft-delete через is_active (FR-007a).
Связан с Workspace (мультитенантная привязка).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from backend.app.db.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from backend.app.db.models.workspace import Workspace


class Pet(Base):
    """Питомец workspace.

    Поля:
        id: автоинкрементный PK
        name: имя питомца, NOT NULL, до 100 символов
        species: вид животного (dog/cat/other), NOT NULL
        breed: порода (nullable)
        birth_date: дата рождения (nullable)
        gender: пол (nullable)
        origin_story: история появления (nullable)
        blood_type: группа крови (nullable)
        chip_number: номер чипа (nullable)
        vet_contact: контакт ветклиники (nullable)
        is_neutered: кастрирован/стерилизован (default False)
        is_active: активен ли профиль, soft-delete (default True)
        workspace_id: FK -> workspace.id
        created_by: Telegram user ID создателя (nullable)
        created_at: дата создания (timezone-aware, server_default)

    Связи:
        workspace: обратная связь с Workspace
    """

    __tablename__ = "pet"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    species: Mapped[str] = mapped_column(String(50))
    breed: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    birth_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    gender: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        default=None,
    )
    origin_story: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    blood_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )
    chip_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    vet_contact: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    is_neutered: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # --- Связи ---
    workspace: Mapped[Workspace] = relationship(back_populates="pets")
