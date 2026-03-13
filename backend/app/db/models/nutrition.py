"""
Модели питания питомца: DietRecord и FeedingEntry.

DietRecord хранит информацию о рационе (бренд корма, тип, период).
FeedingEntry фиксирует отдельные кормления с датой и порцией.
"""

from __future__ import annotations

import datetime

from backend.app.db.base import Base
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class DietRecord(Base):
    """Запись о диете / рационе питомца.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        food_brand: бренд корма, NOT NULL, до 200 символов
        food_type: тип корма (dry/wet/raw/...), nullable, до 50 символов
        start_date: дата начала рациона, NOT NULL
        end_date: дата окончания рациона (nullable)
        notes: дополнительные заметки (nullable)
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_diet_record_pet_end: (pet_id, end_date)
    """

    __tablename__ = "diet_record"

    __table_args__ = (Index("ix_diet_record_pet_end", "pet_id", "end_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    food_brand: Mapped[str] = mapped_column(String(200))
    food_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    start_date: Mapped[datetime.date] = mapped_column(Date)
    end_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    recorded_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class FeedingEntry(Base):
    """Запись об отдельном кормлении питомца.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        fed_at: дата и время кормления (timezone-aware), NOT NULL
        food_description: описание еды, NOT NULL, до 300 символов
        portion_size: размер порции (nullable), до 50 символов
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_feeding_entry_pet_fed: (pet_id, fed_at)
    """

    __tablename__ = "feeding_entry"

    __table_args__ = (Index("ix_feeding_entry_pet_fed", "pet_id", "fed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    fed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    food_description: Mapped[str] = mapped_column(String(300))
    portion_size: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    recorded_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
