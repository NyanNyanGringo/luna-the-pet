"""
Модели, пережившие переход на workspace-centric архитектуру.

Файл содержит только OAuthCredential и ConversationState.
Legacy-таблицы Family/FamilyMember/FamilySettings удалены из runtime ORM.
"""

from __future__ import annotations

import datetime

from backend.app.db.base import Base
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

# ── OAuthCredential (OAuth-токены) ───────────────────────────────────────────


class OAuthCredential(Base):
    """Зашифрованные OAuth-токены для внешних провайдеров (OpenAI и др.).

    Поля:
        id: автоинкрементный PK
        telegram_user_id: Telegram user ID владельца OAuth-токена
        provider: имя провайдера (default "openai")
        access_token_enc: зашифрованный access token, NOT NULL
        refresh_token_enc: зашифрованный refresh token, NOT NULL
        expires_at: срок действия access token (timezone-aware)
        status: текущий статус (default "active")
        created_at: дата создания (timezone-aware, server_default)
        updated_at: дата последнего обновления (timezone-aware, nullable)

    Ограничения:
        UniqueConstraint: (telegram_user_id, provider) — один токен провайдера
        на пользователя
    """

    __tablename__ = "oauth_credential"

    __table_args__ = (UniqueConstraint("telegram_user_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
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


# ── ConversationState (состояние диалога) ─────────────────────────────────


class ConversationState(Base):
    """Состояние диалога пользователя с ботом в контексте workspace.

    Хранит контекст текущей сессии: ID последнего ответа, счётчик ходов
    и краткое содержание. Привязан к паре (telegram_user_id, workspace_id).

    Поля:
        id: автоинкрементный PK
        telegram_user_id: Telegram user ID (BigInteger, NOT NULL)
        workspace_id: FK -> workspace.id, NOT NULL
        last_response_id: ID последнего ответа от LLM (nullable), до 200 символов
        turn_count: количество ходов в сессии (default 0)
        session_summary: краткое содержание сессии (nullable)
        updated_at: дата последнего обновления (timezone-aware, server_default)

    Ограничения:
        UniqueConstraint: (telegram_user_id, workspace_id)
    """

    __tablename__ = "conversation_state"

    __table_args__ = (
        UniqueConstraint(
            "telegram_user_id",
            "workspace_id",
            name="uq_conversation_state_user_workspace",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspace.id"),
        nullable=False,
    )
    last_response_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default=None,
    )
    turn_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    session_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        server_onupdate=func.now(),
    )
