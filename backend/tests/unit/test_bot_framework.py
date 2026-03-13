"""Тесты инфраструктуры бота: роутинг, middleware, webhook."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient


class TestCreateDispatcher:
    """Тесты сборки Dispatcher и router-архитектуры."""

    def test_dispatcher_has_private_and_group_root_routers(self) -> None:
        """В Dispatcher зарегистрированы только корневые private/group роутеры."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        root_router_names = {router.name for router in dispatcher.sub_routers}
        assert root_router_names == {"private", "group"}

    def test_private_router_contains_start_child(self) -> None:
        """Private router содержит child-router start."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        private_router = next(r for r in dispatcher.sub_routers if r.name == "private")
        private_child_names = {router.name for router in private_router.sub_routers}
        assert "start" in private_child_names

    def test_group_router_contains_runtime_children(self) -> None:
        """Group router содержит commands/message/group_events."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        group_router = next(r for r in dispatcher.sub_routers if r.name == "group")
        group_child_names = {router.name for router in group_router.sub_routers}
        assert {"commands", "message", "group_events"}.issubset(group_child_names)

    def test_middlewares_registered_on_expected_levels(self) -> None:
        """DbSession ставится на update, AuthMiddleware — на group.message."""
        from backend.app.bot.create import create_dispatcher

        dispatcher = create_dispatcher()
        update_outer = dispatcher.update.outer_middleware._middlewares
        update_outer_names = {type(middleware).__name__ for middleware in update_outer}
        assert "DbSessionMiddleware" in update_outer_names

        group_router = next(r for r in dispatcher.sub_routers if r.name == "group")
        group_outer = group_router.message.outer_middleware._middlewares
        group_outer_names = {type(middleware).__name__ for middleware in group_outer}
        assert "AuthMiddleware" in group_outer_names


class TestGroupHelpHandler:
    """Тесты /help в группе — контракт требует поддержку в обоих контекстах."""

    def test_help_handler_registered_in_commands_router(self) -> None:
        """handle_group_help зарегистрирован в commands router (для group)."""
        from backend.app.bot.handlers.commands import (
            create_commands_router,
            handle_group_help,
        )

        router = create_commands_router()
        handler_callbacks = [h.callback for h in router.message.handlers]
        assert handle_group_help in handler_callbacks

    async def test_group_help_responds_with_help_text(self) -> None:
        """В группе /help отвечает стандартной справкой."""
        from backend.app.bot.handlers.commands import handle_group_help
        from backend.app.bot.handlers.constants import HELP_GROUP_TEXT

        message = MagicMock()
        message.answer = AsyncMock()

        await handle_group_help(message)

        message.answer.assert_awaited_once_with(HELP_GROUP_TEXT)

    def test_help_group_text_constant_exists(self) -> None:
        """Константа HELP_GROUP_TEXT определена в constants.py."""
        from backend.app.bot.handlers.constants import HELP_GROUP_TEXT

        assert isinstance(HELP_GROUP_TEXT, str)
        assert len(HELP_GROUP_TEXT) > 0

    def test_help_group_text_contains_commands(self) -> None:
        """HELP_GROUP_TEXT содержит описание доступных команд."""
        from backend.app.bot.handlers.constants import HELP_GROUP_TEXT

        assert "/help" in HELP_GROUP_TEXT
        assert "/invite" in HELP_GROUP_TEXT


class TestAuthMiddleware:
    """Тесты workspace-aware AuthMiddleware."""

    def _make_group_event(self, user_id: int = 100500) -> MagicMock:
        """Создаёт mock group message event с from_user/chat/answer."""
        event = MagicMock()
        event.from_user = MagicMock(
            id=user_id,
            username="tester",
            first_name="Тестер",
        )
        event.chat = MagicMock(id=-1001234567890, type="group")
        event.answer = AsyncMock()
        return event

    async def test_non_group_event_passes_without_workspace_lookup(self) -> None:
        """Событие не из группы проходит middleware без блокировки."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock()
        event = MagicMock()
        event.from_user = MagicMock(id=1)
        event.chat = MagicMock(id=1, type="private")

        await middleware(handler, event, {"session": AsyncMock()})
        handler.assert_awaited_once()

    async def test_group_event_without_workspace_is_rejected(self) -> None:
        """Если workspace не найден, handler не вызывается и отправляется отказ."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock()
        event = self._make_group_event()
        session = AsyncMock()

        with patch(
            "backend.app.bot.middlewares.auth.workspace_service.get_workspace_by_chat_id",
            new=AsyncMock(return_value=None),
        ):
            await middleware(handler, event, {"session": session})

        handler.assert_not_awaited()
        event.answer.assert_awaited_once()

    async def test_group_event_injects_workspace_and_member(self) -> None:
        """Для активного workspace middleware прокидывает workspace/member в data."""
        from backend.app.bot.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock()
        event = self._make_group_event(user_id=42)
        session = AsyncMock()
        workspace = MagicMock(id=77, is_active=True)
        member = MagicMock(workspace_id=77, telegram_user_id=42)
        data: dict[str, Any] = {"session": session}

        with (
            patch(
                "backend.app.bot.middlewares.auth.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=workspace),
            ),
            patch(
                "backend.app.bot.middlewares.auth.workspace_service.add_or_reactivate_member",
                new=AsyncMock(return_value=member),
            ),
        ):
            await middleware(handler, event, data)

        handler.assert_awaited_once()
        assert data["workspace"] is workspace
        assert data["member"] is member


class TestWebhookEndpoint:
    """Тесты endpoint /webhook."""

    async def test_webhook_rejects_invalid_secret(self) -> None:
        """Невалидный secret возвращает 403."""
        from backend.app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/webhook",
                json=_make_start_update(),
                headers={"X-Telegram-Bot-Api-Secret-Token": "invalid"},
            )
        assert response.status_code == 403

    async def test_start_update_processed_without_internal_exception(self) -> None:
        """Private /start update через webhook завершается 200/ok."""
        from backend.app import main

        transport = ASGITransport(app=main.app)
        with (
            patch.object(main.settings, "WEBHOOK_SECRET", "test-secret"),
            patch.object(main.bot, "session", new=AsyncMock(return_value=MagicMock())),
            patch.object(main.logger, "exception") as logger_exception,
            patch(
                "backend.app.bot.middlewares.db.async_session_maker",
                return_value=AsyncMock(),
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
        logger_exception.assert_not_called()


def _make_start_update() -> dict[str, object]:
    """Возвращает минимальный Telegram Update с private /start."""
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
