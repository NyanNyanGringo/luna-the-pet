"""
Модели здоровья питомца: WeightRecord, Vaccination, MedicalRecord,
Medication, Note и EmergencyProfile.

Все модели связаны с Pet через pet_id FK. Поле recorded_by хранит
Telegram user ID автора без внешнего ключа.
EmergencyProfile имеет UNIQUE constraint на pet_id (один профиль на питомца).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from backend.app.db.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class WeightRecord(Base):
    """Запись о весе питомца.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        weight_kg: вес в килограммах (Numeric 5,2), NOT NULL
        measured_at: дата измерения, NOT NULL
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_weight_record_pet_measured: (pet_id, measured_at)
    """

    __tablename__ = "weight_record"

    __table_args__ = (Index("ix_weight_record_pet_measured", "pet_id", "measured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    measured_at: Mapped[datetime.date] = mapped_column(Date)
    recorded_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Vaccination(Base):
    """Запись о вакцинации питомца.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        vaccine_name: название вакцины, NOT NULL, до 200 символов
        date: дата вакцинации, NOT NULL
        next_date: дата следующей вакцинации (nullable)
        vet_name: имя ветеринара / клиники (nullable), до 200 символов
        batch_number: номер партии вакцины (nullable), до 100 символов
        notes: дополнительные заметки (nullable)
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_vaccination_pet_date: (pet_id, date)
        ix_vaccination_pet_next_date: (pet_id, next_date)
    """

    __tablename__ = "vaccination"

    __table_args__ = (
        Index("ix_vaccination_pet_date", "pet_id", "date"),
        Index("ix_vaccination_pet_next_date", "pet_id", "next_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    vaccine_name: Mapped[str] = mapped_column(String(200))
    date: Mapped[datetime.date] = mapped_column(Date)
    next_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    vet_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default=None,
    )
    batch_number: Mapped[str | None] = mapped_column(
        String(100),
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


class MedicalRecord(Base):
    """Медицинская запись питомца (болезни, осмотры, операции).

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        record_type: тип записи (illness/checkup/surgery/...), NOT NULL, до 50 символов
        title: заголовок записи, NOT NULL, до 300 символов
        description: подробное описание (nullable)
        date: дата события, NOT NULL
        resolved_date: дата разрешения / выздоровления (nullable)
        vet_name: имя ветеринара / клиники (nullable), до 200 символов
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_medical_record_pet_type: (pet_id, record_type)
        ix_medical_record_pet_date: (pet_id, date)
    """

    __tablename__ = "medical_record"

    __table_args__ = (
        Index("ix_medical_record_pet_type", "pet_id", "record_type"),
        Index("ix_medical_record_pet_date", "pet_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    record_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    date: Mapped[datetime.date] = mapped_column(Date)
    resolved_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    vet_name: Mapped[str | None] = mapped_column(
        String(200),
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


class Medication(Base):
    """Лекарство / препарат питомца.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        name: название препарата, NOT NULL, до 200 символов
        dosage: дозировка (nullable), до 100 символов
        frequency: частота приёма текстом (nullable), до 100 символов
        frequency_days: частота приёма в днях (nullable)
        start_date: дата начала приёма, NOT NULL
        end_date: дата окончания приёма (nullable)
        last_given_date: дата последнего приёма (nullable)
        is_active: активен ли препарат (default True)
        notes: дополнительные заметки (nullable)
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_medication_pet_active: (pet_id, is_active)
    """

    __tablename__ = "medication"

    __table_args__ = (Index("ix_medication_pet_active", "pet_id", "is_active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(200))
    dosage: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    frequency: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    frequency_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    start_date: Mapped[datetime.date] = mapped_column(Date)
    end_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    last_given_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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


class Note(Base):
    """Произвольная заметка о питомце.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        content: текст заметки, NOT NULL
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_note_pet_created: (pet_id, created_at)
    """

    __tablename__ = "note"

    __table_args__ = (Index("ix_note_pet_created", "pet_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    content: Mapped[str] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class EmergencyProfile(Base):
    """Экстренный профиль питомца (один на питомца).

    Содержит критически важную информацию для экстренных ситуаций:
    аллергии, хронические заболевания, контакт ветеринара и т.д.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE, UNIQUE (один профиль на питомца)
        allergies: список аллергий (nullable)
        chronic_conditions: хронические заболевания (nullable)
        vet_contact: контакт ветеринара (nullable)
        blood_type: группа крови (nullable), до 20 символов
        rabies_vaccination_date: дата прививки от бешенства (nullable)
        latest_weight_snapshot: последний известный вес (nullable), Numeric(5,2)
    """

    __tablename__ = "emergency_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
        unique=True,
    )
    allergies: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    chronic_conditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    vet_contact: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    blood_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )
    rabies_vaccination_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    latest_weight_snapshot: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        default=None,
    )
