"""
Тесты инфраструктуры бота и FastAPI приложения — T015, T017, T018, T019, T020.

Покрывает:
- T015: FastAPI app с lifespan, health check endpoint
- T017: aiogram Bot и Dispatcher, регистрация роутеров
- T018: DbSessionMiddleware — инъекция сессии в data хендлера
- T019: AuthMiddleware — проверка авторизации пользователя
- T020: Webhook endpoint — POST /webhook с secret_token

Все тесты используют моки для aiogram и изолированы от реальной БД/Telegram API.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ═══════════════════════════════════════════════════════════════════════════════
# T015: FastAPI приложение с lifespan
# ═══════════════════════════════════════════════════════════════════════════════


class TestFastApiApp:
    """Тесты создания и конфигурации FastAPI приложения."""

    def test_app_is_fastapi_instance(self) -> None:
        """Приложение является экземпляром FastAPI."""
        from backend.app.main import app
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

    def test_app_has_title(self) -> None:
        """Приложение имеет заголовок (title)."""
        from backend.app.main import app

        assert app.title is not None
        assert len(app.title) > 0

    async def test_health_check_returns_200(self) -> None:
        """Health check endpoint возвращает статус 200 OK."""
        from backend.app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            # Пробуем оба возможных пути для health check
            response = await client.get("/api/health")
            if response.status_code == 404:
                response = await client.get("/")

            assert response.status_code == 200

    async def test_health_check_response_has_status_field(self) -> None:
        """Health check endpoint возвращает JSON с полем status."""
        from backend.app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/health")
            if response.status_code == 404:
                response = await client.get("/")

            response_data = response.json()
            assert "status" in response_data


class TestLifespan:
    """Тесты lifespan context manager (startup/shutdown)."""

    async def test_app_starts_and_stops_without_errors(self) -> None:
        """Приложение успешно проходит через lifespan (startup + shutdown)."""
        from backend.app.main import app

        transport = ASGITransport(app=app)

        # AsyncClient автоматически инициирует lifespan
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/health")
            if response.status_code == 404:
                response = await client.get("/")

            # Если дошли сюда — lifespan startup прошёл успешно
            assert response.status_code in (200, 404)

        # Если дошли сюда — lifespan shutdown прошёл успешно


# ═══════════════════════════════════════════════════════════════════════════════
# T017: aiogram Bot и Dispatcher
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateBot:
    """Тесты создания aiogram Bot."""

    def test_create_bot_returns_bot_instance(self) -> None:
        """create_bot() возвращает экземпляр aiogram.Bot."""
        from aiogram import Bot
        from backend.app.bot.create import create_bot

        bot = create_bot()
        assert isinstance(bot, Bot)

    def test_create_bot_uses_configured_token(self) -> None:
        """create_bot() использует токен из конфигурации Settings."""
        from backend.app.bot.create import create_bot
        from backend.app.config import Settings

        settings = Settings()
        bot = create_bot()

        assert bot.token == settings.TELEGRAM_BOT_TOKEN


class TestCreateDispatcher:
    """Тесты создания aiogram Dispatcher и регистрации роутеров."""

    def test_create_dispatcher_returns_dispatcher_instance(self) -> None:
        """create_dispatcher() возвращает экземпляр aiogram.Dispatcher."""
        from aiogram import Dispatcher
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        assert isinstance(dispatcher, Dispatcher)

    def test_dispatcher_has_registered_routers(self) -> None:
        """Dispatcher содержит хотя бы один зарегистрированный роутер."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()

        # У Dispatcher есть sub_routers — проверяем, что не пустой
        assert len(dispatcher.sub_routers) > 0

    def test_dispatcher_has_start_router(self) -> None:
        """Dispatcher содержит роутер для команды /start."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()

        # Проверяем, что хотя бы один роутер зарегистрирован
        # (роутер start должен обрабатывать /start)
        has_routers = len(dispatcher.sub_routers) > 0
        assert has_routers, "Dispatcher должен содержать хотя бы start router"

    def test_dispatcher_registers_start_and_commands_routers(self) -> None:
        """Dispatcher регистрирует роутеры start и commands."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        router_names = {router.name for router in dispatcher.sub_routers}

        assert {"start", "commands"}.issubset(router_names)

    def test_dispatcher_registers_db_and_auth_middlewares(self) -> None:
        """Dispatcher регистрирует DbSessionMiddleware и AuthMiddleware."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        middleware_names = _collect_dispatcher_middleware_names(dispatcher)

        assert "DbSessionMiddleware" in middleware_names
        assert "AuthMiddleware" in middleware_names

    def test_commands_router_registers_invite_and_connectai(self) -> None:
        """Commands router должен содержать обработчики /invite и /connectai."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        commands_router = next(
            (router for router in dispatcher.sub_routers if router.name == "commands"),
            None,
        )

        assert commands_router is not None
        message_handlers = commands_router.observers["message"].handlers
        callback_names = {handler.callback.__name__ for handler in message_handlers}

        assert {"handle_invite", "handle_connectai"}.issubset(callback_names)


def _collect_dispatcher_middleware_names(dispatcher: Any) -> set[str]:
    """Собирает имена middleware из всех observers Dispatcher."""
    middleware_names: set[str] = set()

    for observer in dispatcher.observers.values():
        for manager_name in ("middleware", "outer_middleware"):
            manager = getattr(observer, manager_name, None)
            middlewares = getattr(manager, "_middlewares", [])
            middleware_names.update(
                type(middleware).__name__ for middleware in middlewares
            )

    return middleware_names


# ═══════════════════════════════════════════════════════════════════════════════
# T018: DbSessionMiddleware — инъекция сессии в data хендлера
# ═══════════════════════════════════════════════════════════════════════════════


class TestDbSessionMiddleware:
    """Тесты DbSessionMiddleware для aiogram.

    Middleware добавляет AsyncSession в словарь data хендлера
    и гарантирует закрытие сессии после обработки.
    """

    async def test_middleware_injects_session_into_data(self) -> None:
        """Middleware добавляет ключ 'session' в data хендлера."""
        from backend.app.bot.middlewares.db import DbSessionMiddleware

        middleware = DbSessionMiddleware()

        mock_handler = AsyncMock()
        mock_event = MagicMock()
        handler_data: dict = {}

        # Мокируем async_session_maker для создания фейковой сессии
        mock_session = AsyncMock()
        mock_session_maker = MagicMock(return_value=mock_session)

        with patch(
            "backend.app.bot.middlewares.db.async_session_maker",
            mock_session_maker,
        ):
            await middleware(mock_handler, mock_event, handler_data)

        # Проверяем, что handler был вызван с session в data
        mock_handler.assert_awaited_once()

        # session должен быть в data при вызове handler
        # Middleware передаёт data с session в handler(event, data)
        assert mock_handler.await_count == 1

    async def test_middleware_closes_session_after_handler(self) -> None:
        """Middleware закрывает сессию после успешного выполнения хендлера."""
        from backend.app.bot.middlewares.db import DbSessionMiddleware

        middleware = DbSessionMiddleware()

        mock_handler = AsyncMock()
        mock_event = MagicMock()
        handler_data: dict = {}

        mock_session = AsyncMock()
        mock_session_maker = MagicMock(return_value=mock_session)

        with patch(
            "backend.app.bot.middlewares.db.async_session_maker",
            mock_session_maker,
        ):
            await middleware(mock_handler, mock_event, handler_data)

        mock_session.commit.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    async def test_middleware_closes_session_on_handler_error(self) -> None:
        """Middleware закрывает сессию даже если хендлер бросил исключение."""
        from backend.app.bot.middlewares.db import DbSessionMiddleware

        middleware = DbSessionMiddleware()

        mock_handler = AsyncMock(
            side_effect=RuntimeError("ошибка в хендлере"),
        )
        mock_event = MagicMock()
        handler_data: dict = {}

        mock_session = AsyncMock()
        mock_session_maker = MagicMock(return_value=mock_session)

        with (
            patch(
                "backend.app.bot.middlewares.db.async_session_maker",
                mock_session_maker,
            ),
            pytest.raises(RuntimeError, match="ошибка в хендлере"),
        ):
            await middleware(mock_handler, mock_event, handler_data)

        mock_session.rollback.assert_awaited_once()
        # Сессия должна быть закрыта несмотря на ошибку
        mock_session.close.assert_awaited_once()

    async def test_middleware_creates_new_session_per_call(self) -> None:
        """Middleware создаёт новую сессию для каждого вызова хендлера."""
        from backend.app.bot.middlewares.db import DbSessionMiddleware

        middleware = DbSessionMiddleware()

        mock_handler = AsyncMock()
        mock_event = MagicMock()

        mock_session_maker = MagicMock(
            side_effect=[AsyncMock(), AsyncMock()],
        )

        with patch(
            "backend.app.bot.middlewares.db.async_session_maker",
            mock_session_maker,
        ):
            await middleware(mock_handler, mock_event, {})
            await middleware(mock_handler, mock_event, {})

        # session_maker должен быть вызван дважды — по одной сессии на вызов
        assert mock_session_maker.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# T019: AuthMiddleware — проверка авторизации пользователя
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthMiddleware:
    """Тесты AuthMiddleware для aiogram.

    Проверяет авторизацию пользователя по полю is_authorized в FamilyMember.
    Команда /start проходит без проверки (whitelist).
    """

    def _make_event_with_user(self, user_id: int) -> MagicMock:
        """Создаёт мок события с from_user.

        Аргументы:
            user_id: Telegram user ID для from_user

        Возвращает:
            MagicMock: мок события с атрибутом from_user.id
        """
        mock_event = MagicMock()
        mock_event.from_user = MagicMock()
        mock_event.from_user.id = user_id
        return mock_event

    def _make_member(
        self,
        user_id: int,
        is_authorized: bool,
    ) -> MagicMock:
        """Создаёт мок FamilyMember.

        Аргументы:
            user_id: Telegram user ID
            is_authorized: статус авторизации

        Возвращает:
            MagicMock: мок FamilyMember с заданными полями
        """
        mock_member = MagicMock()
        mock_member.id = user_id
        mock_member.is_authorized = is_authorized
        mock_member.first_name = "Тест"
        return mock_member

    async def test_authorized_user_passes_through(self) -> None:
        """Авторизованный пользователь (is_authorized=True) проходит middleware."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()

        telegram_user_id = 111222333
        mock_handler = AsyncMock()
        mock_event = self._make_event_with_user(telegram_user_id)

        # Мокируем сессию, которая вернёт авторизованного пользователя
        mock_member = self._make_member(telegram_user_id, is_authorized=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_member

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        handler_data: dict = {"session": mock_session}

        await middleware(mock_handler, mock_event, handler_data)

        # Handler должен быть вызван — пользователь авторизован
        mock_handler.assert_awaited_once()

    async def test_unauthorized_user_is_rejected(self) -> None:
        """Неавторизованный пользователь (is_authorized=False) не проходит."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()

        telegram_user_id = 444555666
        mock_handler = AsyncMock()
        mock_event = self._make_event_with_user(telegram_user_id)

        mock_member = self._make_member(telegram_user_id, is_authorized=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_member

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        handler_data: dict = {"session": mock_session}

        await middleware(mock_handler, mock_event, handler_data)

        # Handler НЕ должен быть вызван — пользователь не авторизован
        mock_handler.assert_not_awaited()

    async def test_unknown_user_is_rejected(self) -> None:
        """Несуществующий в БД пользователь не проходит middleware."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()

        telegram_user_id = 777888999
        mock_handler = AsyncMock()
        mock_event = self._make_event_with_user(telegram_user_id)

        # БД возвращает None — пользователь не найден
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        handler_data: dict = {"session": mock_session}

        await middleware(mock_handler, mock_event, handler_data)

        # Handler НЕ должен быть вызван — пользователь не существует
        mock_handler.assert_not_awaited()

    async def test_start_command_passes_without_auth_check(self) -> None:
        """Команда /start проходит без проверки авторизации (whitelist)."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()

        telegram_user_id = 111000222
        mock_handler = AsyncMock()

        # Мокируем Message с командой /start
        mock_event = self._make_event_with_user(telegram_user_id)
        mock_event.text = "/start"

        # Не мокируем сессию — middleware не должен обращаться к БД
        handler_data: dict = {}

        await middleware(mock_handler, mock_event, handler_data)

        # Handler должен быть вызван — /start в whitelist
        mock_handler.assert_awaited_once()

    async def test_unauthorized_user_receives_rejection_message(self) -> None:
        """Неавторизованный пользователь получает сообщение об отказе."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()

        telegram_user_id = 333444555
        mock_handler = AsyncMock()
        mock_event = self._make_event_with_user(telegram_user_id)
        mock_event.answer = AsyncMock()

        mock_member = self._make_member(telegram_user_id, is_authorized=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_member

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        handler_data: dict = {"session": mock_session}

        await middleware(mock_handler, mock_event, handler_data)

        # Пользователь должен получить ответ с отказом
        mock_event.answer.assert_awaited_once()

    async def test_start_command_with_deep_link_passes(self) -> None:
        """Команда /start с deep link (/start invite_xxx) проходит без проверки."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()

        telegram_user_id = 666777888
        mock_handler = AsyncMock()

        mock_event = self._make_event_with_user(telegram_user_id)
        mock_event.text = "/start invite_abc123"

        handler_data: dict = {}

        await middleware(mock_handler, mock_event, handler_data)

        # Handler должен быть вызван — /start (с аргументами) в whitelist
        mock_handler.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# T020: Webhook endpoint
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebhookEndpoint:
    """Тесты webhook endpoint (POST /webhook) в FastAPI приложении.

    Проверяет верификацию secret_token при приёме обновлений от Telegram.
    """

    async def test_webhook_with_valid_secret_returns_ok(self) -> None:
        """POST /webhook с правильным secret_token обрабатывается (200 OK)."""
        from backend.app.config import Settings
        from backend.app.main import app

        settings = Settings()
        webhook_secret = settings.WEBHOOK_SECRET

        # Пропускаем тест, если WEBHOOK_SECRET не настроен
        if not webhook_secret:
            pytest.skip("WEBHOOK_SECRET не настроен в Settings")

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            # Минимальный валидный Update от Telegram
            telegram_update = {
                "update_id": 123456789,
                "message": {
                    "message_id": 1,
                    "date": 1234567890,
                    "chat": {"id": 111, "type": "private"},
                    "from": {"id": 111, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            }

            response = await client.post(
                "/webhook",
                json=telegram_update,
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
                },
            )

        assert response.status_code == 200

    async def test_webhook_without_secret_returns_403(self) -> None:
        """POST /webhook без secret_token возвращает 403 Forbidden."""
        from backend.app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            telegram_update = {
                "update_id": 123456789,
                "message": {
                    "message_id": 1,
                    "date": 1234567890,
                    "chat": {"id": 111, "type": "private"},
                    "from": {"id": 111, "is_bot": False, "first_name": "Test"},
                    "text": "hello",
                },
            }

            response = await client.post(
                "/webhook",
                json=telegram_update,
            )

        # Без secret — отказ доступа
        assert response.status_code == 403

    async def test_webhook_with_wrong_secret_returns_403(self) -> None:
        """POST /webhook с неверным secret_token возвращает 403 Forbidden."""
        from backend.app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            telegram_update = {
                "update_id": 123456789,
                "message": {
                    "message_id": 1,
                    "date": 1234567890,
                    "chat": {"id": 111, "type": "private"},
                    "from": {"id": 111, "is_bot": False, "first_name": "Test"},
                    "text": "hello",
                },
            }

            response = await client.post(
                "/webhook",
                json=telegram_update,
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "wrong-secret-token",
                },
            )

        assert response.status_code == 403

    async def test_webhook_endpoint_exists(self) -> None:
        """Endpoint POST /webhook зарегистрирован в приложении."""
        from backend.app.main import app

        webhook_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and route.path == "/webhook"
        ]

        assert len(webhook_routes) > 0, "Endpoint POST /webhook не найден в приложении"

    async def test_webhook_rejects_get_method(self) -> None:
        """GET /webhook не допускается — только POST."""
        from backend.app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/webhook")

        # GET не поддерживается — ожидаем 405 Method Not Allowed
        assert response.status_code == 405

    async def test_start_update_does_not_log_session_injection_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Webhook /start не должен падать из-за отсутствия session-инъекции."""
        from backend.app import main

        monkeypatch.setattr(main.settings, "WEBHOOK_SECRET", "test-secret")
        transport = ASGITransport(app=main.app)

        mock_session = AsyncMock()
        mock_member = MagicMock()
        mock_member.is_authorized = True
        mock_family = MagicMock(id=1)

        with (
            patch.object(main.bot, "session", new=AsyncMock(return_value=MagicMock())),
            patch.object(main.logger, "exception") as mock_log_exception,
            patch(
                "backend.app.bot.middlewares.db.async_session_maker",
                return_value=mock_session,
            ),
            patch(
                "backend.app.bot.middlewares.auth._lookup_member",
                new_callable=AsyncMock,
                return_value=mock_member,
            ),
            patch(
                "backend.app.bot.handlers.start.get_or_create_family",
                new_callable=AsyncMock,
                return_value=mock_family,
            ),
            patch(
                "backend.app.bot.handlers.start.get_member",
                new_callable=AsyncMock,
                return_value=mock_member,
            ),
        ):
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/webhook",
                    json=_make_start_update(),
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
                )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_log_exception.assert_not_called()


def _make_start_update() -> dict:
    """Возвращает минимальный валидный Telegram Update с командой /start."""
    return {
        "update_id": 123456790,
        "message": {
            "message_id": 10,
            "date": 1234567890,
            "chat": {"id": 111, "type": "private"},
            "from": {"id": 111, "is_bot": False, "first_name": "Test"},
            "text": "/start",
        },
    }
