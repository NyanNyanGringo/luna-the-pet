"""
Тесты FastAPI зависимостей (backend.app.api.deps) — T016.

Проверяет:
- get_db() — async generator, возвращает AsyncSession, закрывает после использования
- get_current_user() — декодирует JWT из Authorization header, возвращает FamilyMember
- get_current_user() с невалидным/просроченным JWT -> HTTPException 401

Все тесты используют моки — реальная БД и JWT-инфраструктура не требуются.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.params import Depends as DependsParam
from fastapi.params import Header as HeaderParam
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# T016: get_db — async generator для получения сессии БД
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetDb:
    """Тесты зависимости get_db() — async generator для AsyncSession."""

    async def test_get_db_returns_async_session(self) -> None:
        """get_db() выдаёт объект, совместимый с AsyncSession."""
        from backend.app.api.deps import get_db

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.api.deps.async_session_maker",
            return_value=mock_session,
        ):
            session_generator = get_db()
            session = await session_generator.__anext__()

            assert session is mock_session

    async def test_get_db_closes_session_after_use(self) -> None:
        """get_db() закрывает сессию после завершения генератора."""
        from backend.app.api.deps import get_db

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.api.deps.async_session_maker",
            return_value=mock_session,
        ):
            session_generator = get_db()
            await session_generator.__anext__()

            # Завершаем генератор — сессия должна закрыться
            with pytest.raises(StopAsyncIteration):
                await session_generator.__anext__()

            mock_session.close.assert_awaited_once()

    async def test_get_db_closes_session_on_exception(self) -> None:
        """get_db() закрывает сессию даже при исключении в хендлере."""
        from backend.app.api.deps import get_db

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.api.deps.async_session_maker",
            return_value=mock_session,
        ):
            session_generator = get_db()
            await session_generator.__anext__()

            # Бросаем исключение внутрь генератора (имитация ошибки в хендлере)
            with pytest.raises(ValueError, match="тестовая ошибка"):
                await session_generator.athrow(ValueError("тестовая ошибка"))

            mock_session.close.assert_awaited_once()

    async def test_get_db_is_async_generator(self) -> None:
        """get_db() является async generator function."""
        import inspect

        from backend.app.api.deps import get_db

        assert inspect.isasyncgenfunction(get_db)


# ═══════════════════════════════════════════════════════════════════════════════
# T016: get_current_user — извлечение пользователя из JWT
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetCurrentUser:
    """Тесты зависимости get_current_user() — авторизация через JWT."""

    async def test_valid_jwt_returns_family_member(self) -> None:
        """Валидный JWT в Authorization header возвращает FamilyMember."""
        from backend.app.api.deps import get_current_user
        from backend.app.db.models.family import FamilyMember

        telegram_user_id = 123456789
        mock_session = AsyncMock(spec=AsyncSession)

        # Мокируем FamilyMember, который вернёт БД
        mock_member = MagicMock(spec=FamilyMember)
        mock_member.id = telegram_user_id
        mock_member.first_name = "Тест"
        mock_member.is_authorized = True

        # Мокируем результат запроса к БД
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_member
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Патчим декодирование JWT — возвращаем payload с user_id
        with patch(
            "backend.app.api.deps.jwt.decode",
            return_value={"sub": str(telegram_user_id)},
        ):
            result = await get_current_user(
                token=f"Bearer valid-jwt-token",  # noqa: F541
                session=mock_session,
            )

        assert result is mock_member

    async def test_missing_authorization_header_raises_401(self) -> None:
        """Отсутствие Authorization header вызывает HTTPException 401."""
        from backend.app.api.deps import get_current_user

        mock_session = AsyncMock(spec=AsyncSession)

        with pytest.raises(HTTPException) as exception_info:
            await get_current_user(token=None, session=mock_session)

        assert exception_info.value.status_code == 401

    async def test_invalid_jwt_raises_401(self) -> None:
        """Невалидный JWT (не декодируется) вызывает HTTPException 401."""
        from backend.app.api.deps import get_current_user

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.api.deps.jwt.decode",
            side_effect=Exception("Invalid token"),
        ):
            with pytest.raises(HTTPException) as exception_info:
                await get_current_user(
                    token="Bearer invalid-token",
                    session=mock_session,
                )

            assert exception_info.value.status_code == 401

    async def test_expired_jwt_raises_401(self) -> None:
        """Просроченный JWT вызывает HTTPException 401."""
        from backend.app.api.deps import get_current_user
        from jose.exceptions import ExpiredSignatureError

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.api.deps.jwt.decode",
            side_effect=ExpiredSignatureError("Token expired"),
        ):
            with pytest.raises(HTTPException) as exception_info:
                await get_current_user(
                    token="Bearer expired-token",
                    session=mock_session,
                )

            assert exception_info.value.status_code == 401

    async def test_jwt_with_nonexistent_user_raises_401(self) -> None:
        """JWT с user_id несуществующего пользователя вызывает HTTPException 401."""
        from backend.app.api.deps import get_current_user

        mock_session = AsyncMock(spec=AsyncSession)

        # БД возвращает None — пользователь не найден
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "backend.app.api.deps.jwt.decode",
            return_value={"sub": "999999999"},
        ):
            with pytest.raises(HTTPException) as exception_info:
                await get_current_user(
                    token="Bearer valid-but-no-user",
                    session=mock_session,
                )

            assert exception_info.value.status_code == 401

    async def test_jwt_without_sub_claim_raises_401(self) -> None:
        """JWT без поля sub в payload вызывает HTTPException 401."""
        from backend.app.api.deps import get_current_user

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.api.deps.jwt.decode",
            return_value={"exp": 9999999999},  # нет "sub"
        ):
            with pytest.raises(HTTPException) as exception_info:
                await get_current_user(
                    token="Bearer no-sub-token",
                    session=mock_session,
                )

            assert exception_info.value.status_code == 401


class TestGetCurrentUserDependencyContract:
    """Регрессии DI-контракта get_current_user для FastAPI."""

    def test_get_current_user_uses_header_and_depends_in_signature(self) -> None:
        """Сигнатура должна объявлять token=Header(...) и session=Depends(get_db)."""
        import inspect

        from backend.app.api.deps import get_current_user

        signature = inspect.signature(get_current_user)
        token_parameter = signature.parameters["token"]
        session_parameter = signature.parameters["session"]

        assert isinstance(token_parameter.default, HeaderParam)
        assert isinstance(session_parameter.default, DependsParam)

    def test_get_current_user_can_be_used_as_fastapi_dependency(self) -> None:
        """Depends(get_current_user) должен монтироваться без FastAPIError."""
        from backend.app.api.deps import get_current_user

        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected_route(
            current_user: Any = Depends(get_current_user),
        ) -> dict[str, int | None]:
            return {"user_id": getattr(current_user, "id", None)}

        assert len(test_app.routes) > 0
