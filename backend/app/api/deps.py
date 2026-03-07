"""
FastAPI зависимости: сессия БД, текущий пользователь из JWT.

Предоставляет async generator для AsyncSession и функцию
аутентификации пользователя через JWT Bearer token.
"""

import logging
from collections.abc import AsyncGenerator

from backend.app.config import Settings
from backend.app.db.models.family import FamilyMember
from backend.app.db.session import async_session_maker
from fastapi import Depends, Header, HTTPException
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Загружаем настройки один раз на уровне модуля
_settings = Settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async generator — создаёт и выдаёт AsyncSession, закрывает после использования.

    Возвращает:
        AsyncSession: сессия БД для текущего запроса

    Побочные эффекты:
        Сессия гарантированно закрывается в finally-блоке,
        даже если в хендлере произошла ошибка.
    """
    session = async_session_maker()
    try:
        yield session
    finally:
        await session.close()


async def get_current_user(
    token: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> FamilyMember:
    """Извлекает текущего пользователя из JWT Bearer token.

    Аргументы:
        token: значение Authorization header
            (формат "Bearer <jwt>"), None если отсутствует
        session: AsyncSession для запроса к БД

    Возвращает:
        FamilyMember: авторизованный участник семьи

    Ошибки:
        HTTPException(401): если token отсутствует, невалиден, просрочен,
            не содержит sub, или пользователь не найден в БД
    """
    if token is None:
        logger.warning("Запрос без Authorization header")
        raise HTTPException(status_code=401, detail="Токен не предоставлен")

    raw_token = _extract_bearer_token(token)
    user_id = _decode_jwt_subject(raw_token)
    member = await _fetch_family_member(session, user_id)
    return member


def _extract_bearer_token(authorization: str) -> str:
    """Извлекает JWT из строки 'Bearer <token>'.

    Аргументы:
        authorization: полное значение Authorization header

    Возвращает:
        str: JWT-токен без префикса Bearer

    Ошибки:
        HTTPException(401): если формат заголовка некорректен
    """
    parts = authorization.split(" ", maxsplit=1)
    if len(parts) != 2 or parts[0] != "Bearer":
        logger.warning("Некорректный формат Authorization header")
        raise HTTPException(status_code=401, detail="Некорректный формат токена")
    return parts[1]


def _decode_jwt_subject(token: str) -> int:
    """Декодирует JWT и извлекает user_id из claim 'sub'.

    Аргументы:
        token: JWT-строка для декодирования

    Возвращает:
        int: Telegram user ID из claim sub

    Ошибки:
        HTTPException(401): если JWT невалиден, просрочен или не содержит sub
    """
    try:
        payload = jwt.decode(token, _settings.JWT_SECRET, algorithms=["HS256"])
    except Exception as decode_error:
        logger.warning("Ошибка декодирования JWT: %s", decode_error)
        raise HTTPException(
            status_code=401,
            detail="Невалидный токен",
        ) from decode_error

    subject = payload.get("sub")
    if subject is None:
        logger.warning("JWT не содержит claim 'sub'")
        raise HTTPException(
            status_code=401,
            detail="Токен не содержит идентификатор пользователя",
        )

    try:
        return int(subject)
    except (TypeError, ValueError) as subject_error:
        raise HTTPException(
            status_code=401,
            detail="Некорректный идентификатор пользователя в токене",
        ) from subject_error


async def _fetch_family_member(session: AsyncSession, user_id: int) -> FamilyMember:
    """Ищет FamilyMember в БД по Telegram user ID.

    Аргументы:
        session: AsyncSession для запроса
        user_id: Telegram user ID (из JWT sub)

    Возвращает:
        FamilyMember: найденный участник семьи

    Ошибки:
        HTTPException(401): если пользователь не найден в БД
    """
    query = select(FamilyMember).where(FamilyMember.id == user_id)
    result = await session.execute(query)
    member = result.scalar_one_or_none()

    if member is None:
        logger.warning("Пользователь с ID %d не найден в БД", user_id)
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return member
