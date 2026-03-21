"""
Модель документов питомца: Document.

Document хранит ссылку на медицинский документ питомца (справки, результаты
анализов, рентген-снимки и т.д.).
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


class Document(Base):
    """Ссылка на медицинский документ питомца.

    Поля:
        id: автоинкрементный PK
        pet_id: FK -> pet.id, NOT NULL, CASCADE
        document_type: тип документа, NOT NULL, до 100 символов
        url: ссылка на документ, NOT NULL, до 2048 символов
        issued_date: дата выдачи документа (nullable)
        description: описание документа (nullable)
        recorded_by: Telegram user ID (кто записал, nullable)
        created_at: дата создания (timezone-aware, server_default)

    Индексы:
        ix_document_pet_type: (pet_id, document_type)
    """

    __tablename__ = "document"

    __table_args__ = (Index("ix_document_pet_type", "pet_id", "document_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(
        ForeignKey("pet.id", ondelete="CASCADE"),
    )
    document_type: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    issued_date: Mapped[datetime.date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )
    description: Mapped[str | None] = mapped_column(
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
