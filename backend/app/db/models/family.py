"""
Модели семейного домохозяйства: Family, FamilyMember, FamilySettings,
FamilyInvite, OAuthCredential и M2M-таблица family_pet.

Family — singleton домохозяйства, к которому привязаны все остальные сущности.
FamilyMember.id — Telegram user ID (BigInteger, НЕ autoincrement).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from backend.app.db.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from backend.app.db.models.pet import Pet


# ── M2M ассоциативная таблица: участник <-> питомец ──────────────────────────

family_pet = Table(
    "family_pet",
    Base.metadata,
    Column(
        "family_member_id",
        BigInteger,
        ForeignKey("family_member.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "pet_id",
        Integer,
        ForeignKey("pet.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ── Family (singleton домохозяйства) ────────────────────────────────────────


class Family(Base):
    """Домохозяйство (singleton). Корневая сущность для всех связей.

    Поля:
        id: автоинкрементный PK
        singleton_key: константный ключ singleton (всегда True, UNIQUE)
        created_at: дата создания (timezone-aware, server_default)

    Связи:
        members: список участников семьи
        pets: список питомцев семьи
        settings: настройки семьи (one-to-one)
        invites: список инвайтов
        oauth_credentials: OAuth-токены
    """

    __tablename__ = "family"
    __table_args__ = (UniqueConstraint("singleton_key", name="uq_family_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    singleton_key: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # --- Связи ---
    members: Mapped[list[FamilyMember]] = relationship(
        back_populates="family",
    )
    pets: Mapped[list[Pet]] = relationship(
        back_populates="family",
    )
    settings: Mapped[FamilySettings | None] = relationship(
        back_populates="family",
        uselist=False,
    )
    invites: Mapped[list[FamilyInvite]] = relationship(
        back_populates="family",
    )
    oauth_credentials: Mapped[list[OAuthCredential]] = relationship(
        back_populates="family",
    )


# ── FamilyMember (участник семьи) ───────────────────────────────────────────


class FamilyMember(Base):
    """Участник семьи. PK — Telegram user ID (BigInteger, НЕ autoincrement).

    Поля:
        id: Telegram user ID (BigInteger PK)
        first_name: имя из Telegram, NOT NULL, до 100 символов
        username: Telegram username, nullable, до 100 символов
        is_authorized: авторизован ли пользователь (default True)
        created_at: дата добавления (timezone-aware, server_default)
        family_id: FK -> family.id

    Связи:
        family: обратная связь с Family
        pets: M2M через family_pet
    """

    __tablename__ = "family_member"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    first_name: Mapped[str] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    is_authorized: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("family.id", ondelete="CASCADE"),
    )

    # --- Связи ---
    family: Mapped[Family] = relationship(back_populates="members")
    pets: Mapped[list[Pet]] = relationship(
        secondary=family_pet,
        back_populates="members",
    )


# ── FamilySettings (настройки семьи) ────────────────────────────────────────


class FamilySettings(Base):
    """Настройки семьи: таймзона и локаль дат.

    Поля:
        id: автоинкрементный PK
        family_id: FK -> family.id, unique (one-to-one)
        timezone: IANA-таймзона (default "UTC")
        date_locale: локаль дат (nullable)

    Связи:
        family: обратная связь с Family
    """

    __tablename__ = "family_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("family.id", ondelete="CASCADE"),
        unique=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="UTC",
    )
    date_locale: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )

    # --- Связи ---
    family: Mapped[Family] = relationship(back_populates="settings")


# ── FamilyInvite (инвайт / одноразовый код) ─────────────────────────────────


class FamilyInvite(Base):
    """Инвайт для присоединения к семье.

    Поля:
        id: автоинкрементный PK
        family_id: FK -> family.id
        invite_code: уникальный код приглашения, NOT NULL
        created_by: FK -> family_member.id (кто создал)
        expires_at: срок действия (timezone-aware), NOT NULL
        revoked_at: дата отзыва (nullable)
        used_by: FK -> family_member.id (кто использовал, nullable)
        used_at: дата использования (nullable)
        status: текущий статус (default "active")

    Связи:
        family: обратная связь с Family
    """

    __tablename__ = "family_invite"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("family.id", ondelete="CASCADE"),
    )
    invite_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("family_member.id", ondelete="CASCADE"),
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    used_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("family_member.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
    )

    # --- Связи ---
    family: Mapped[Family] = relationship(back_populates="invites")


# ── OAuthCredential (OAuth-токены) ───────────────────────────────────────────


class OAuthCredential(Base):
    """Зашифрованные OAuth-токены для внешних провайдеров (OpenAI и др.).

    Поля:
        id: автоинкрементный PK
        family_id: FK -> family.id
        provider: имя провайдера (default "openai")
        access_token_enc: зашифрованный access token, NOT NULL
        refresh_token_enc: зашифрованный refresh token, NOT NULL
        expires_at: срок действия access token (timezone-aware)
        status: текущий статус (default "active")
        created_at: дата создания (timezone-aware, server_default)
        updated_at: дата последнего обновления (timezone-aware, nullable)

    Ограничения:
        UniqueConstraint: (family_id, provider) — один токен на провайдера

    Связи:
        family: обратная связь с Family
    """

    __tablename__ = "oauth_credential"

    __table_args__ = (UniqueConstraint("family_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("family.id", ondelete="CASCADE"),
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        default="openai",
    )
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # --- Связи ---
    family: Mapped[Family] = relationship(
        back_populates="oauth_credentials",
    )
