"""
FastAPI зависимости: сессия БД, текущий пользователь из JWT.

Предоставляет async generator для AsyncSession и функцию
аутентификации пользователя через JWT Bearer token.
"""

import logging
from collections.abc import AsyncGenerator

from backend.app.config import Settings
from backend.app.db.models.workspace import Workspace, WorkspaceMember
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
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> WorkspaceMember:
    """Извлекает текущего пользователя из JWT Bearer token.

    Аргументы:
        token: значение Authorization header
            (формат "Bearer <jwt>"), None если отсутствует
        workspace_id: значение X-Workspace-Id header, None если отсутствует
        session: AsyncSession для запроса к БД

    Возвращает:
        WorkspaceMember: авторизованный участник workspace

    Ошибки:
        HTTPException(401): если token/workspace_id отсутствуют, невалидны,
            JWT просрочен/битый, не содержит sub, или участник не найден в БД
    """
    if token is None:
        logger.warning("Запрос без Authorization header")
        raise HTTPException(status_code=401, detail="Токен не предоставлен")

    parsed_workspace_id = _parse_workspace_id_header(workspace_id)
    raw_token = _extract_bearer_token(token)
    user_id = _decode_jwt_subject(raw_token)
    member = await _fetch_workspace_member(
        session=session,
        workspace_id=parsed_workspace_id,
        user_id=user_id,
    )
    return member


def _parse_workspace_id_header(workspace_id: str | None) -> int:
    """Валидирует и приводит X-Workspace-Id к int.

    Аргументы:
        workspace_id: сырое значение X-Workspace-Id header

    Возвращает:
        int: идентификатор workspace

    Ошибки:
        HTTPException(401): если header отсутствует или не является целым числом
    """
    if workspace_id is None:
        logger.warning("Запрос без X-Workspace-Id header")
        raise HTTPException(status_code=401, detail="Workspace не указан")

    try:
        return int(workspace_id)
    except (TypeError, ValueError) as workspace_id_error:
        logger.warning("Некорректный X-Workspace-Id: %s", workspace_id)
        raise HTTPException(
            status_code=401,
            detail="Некорректный идентификатор workspace",
        ) from workspace_id_error


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


async def _fetch_workspace_member(
    session: AsyncSession,
    workspace_id: int,
    user_id: int,
) -> WorkspaceMember:
    """Ищет активный WorkspaceMember в БД по workspace_id и Telegram user ID.

    Аргументы:
        session: AsyncSession для запроса
        workspace_id: идентификатор workspace из X-Workspace-Id
        user_id: Telegram user ID (из JWT sub)

    Возвращает:
        WorkspaceMember: найденный участник workspace

    Ошибки:
        HTTPException(401): если пользователь не найден в БД
            или состоит в неактивном workspace
    """
    query = (
        select(WorkspaceMember)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.telegram_user_id == user_id,
            WorkspaceMember.is_active.is_(True),
            Workspace.is_active.is_(True),
        )
    )
    result = await session.execute(query)
    member = result.scalar_one_or_none()

    if member is None or _member_has_inactive_workspace(member):
        logger.warning(
            "Участник не найден: workspace_id=%d telegram_user_id=%d",
            workspace_id,
            user_id,
        )
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return member


def _member_has_inactive_workspace(member: WorkspaceMember) -> bool:
    """Проверяет, что у уже загруженного member.workspace не стоит is_active=False."""
    loaded_workspace = getattr(member, "__dict__", {}).get("workspace")
    if loaded_workspace is None:
        return False
    return getattr(loaded_workspace, "is_active", True) is False
