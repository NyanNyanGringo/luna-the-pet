"""
Тесты жизненного цикла backend.app.main.

Покрывает:
- Ветки startup/shutdown для dev/prod в lifespan
- Предупреждение в dev при заданном WEBHOOK_URL
- Безопасный shutdown, когда polling не был запущен
- Изменение уровня логирования при уже настроенном root logger
"""

import io
import logging
from collections.abc import Coroutine
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.app import main


class TestLifespanBehavior:
    """Проверяет dev/prod ветки startup/shutdown."""

    async def test_lifespan_dev_runs_polling_start_and_stop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """В dev-режиме вызываются _start_polling и _stop_polling."""
        monkeypatch.setattr(main.settings, "APP_ENV", "dev")

        with (
            patch.object(main, "_configure_logging") as mock_configure_logging,
            patch.object(main, "_start_polling", new=AsyncMock()) as mock_start_polling,
            patch.object(main, "_setup_webhook", new=AsyncMock()) as mock_setup_webhook,
            patch.object(main, "_stop_polling", new=AsyncMock()) as mock_stop_polling,
            patch.object(main.bot.session, "close", new=AsyncMock()) as mock_close,
        ):
            async with main.lifespan(main.app):
                pass

        mock_configure_logging.assert_called_once()
        mock_start_polling.assert_awaited_once()
        mock_setup_webhook.assert_not_awaited()
        mock_stop_polling.assert_awaited_once()
        mock_close.assert_awaited_once()

    async def test_lifespan_prod_runs_webhook_setup_without_polling_stop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """В prod-режиме вызывается _setup_webhook, polling не останавливается."""
        monkeypatch.setattr(main.settings, "APP_ENV", "prod")

        with (
            patch.object(main, "_configure_logging") as mock_configure_logging,
            patch.object(main, "_start_polling", new=AsyncMock()) as mock_start_polling,
            patch.object(main, "_setup_webhook", new=AsyncMock()) as mock_setup_webhook,
            patch.object(main, "_stop_polling", new=AsyncMock()) as mock_stop_polling,
            patch.object(main.bot.session, "close", new=AsyncMock()) as mock_close,
        ):
            async with main.lifespan(main.app):
                pass

        mock_configure_logging.assert_called_once()
        mock_start_polling.assert_not_awaited()
        mock_setup_webhook.assert_awaited_once()
        mock_stop_polling.assert_not_awaited()
        mock_close.assert_awaited_once()

    async def test_lifespan_dev_closes_session_when_stop_polling_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """В dev shutdown закрывает сессию даже при ошибке _stop_polling."""
        monkeypatch.setattr(main.settings, "APP_ENV", "dev")
        stop_polling_error = RuntimeError("unexpected stop failure")

        with (
            patch.object(main, "_configure_logging"),
            patch.object(main, "_start_polling", new=AsyncMock()),
            patch.object(
                main,
                "_stop_polling",
                new=AsyncMock(side_effect=stop_polling_error),
            ) as mock_stop_polling,
            patch.object(main.bot.session, "close", new=AsyncMock()) as mock_close,
            pytest.raises(RuntimeError, match="unexpected stop failure"),
        ):
            async with main.lifespan(main.app):
                pass

        mock_stop_polling.assert_awaited_once()
        mock_close.assert_awaited_once()


class TestPollingLifecycle:
    """Проверяет запуск и остановку polling в main.py."""

    async def test_start_polling_logs_warning_in_dev_when_webhook_url_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_start_polling логирует warning, если WEBHOOK_URL задан в dev."""
        monkeypatch.setattr(main.settings, "APP_ENV", "dev")
        monkeypatch.setattr(
            main.settings,
            "WEBHOOK_URL",
            "https://dev.example.com/webhook",
        )
        monkeypatch.setattr(main, "_polling_task", None)

        fake_polling_task = MagicMock()
        started_polling_coroutines: list[Coroutine[None, None, None]] = []

        def fake_create_task(
            polling_coroutine: Coroutine[None, None, None],
        ) -> MagicMock:
            started_polling_coroutines.append(polling_coroutine)
            return fake_polling_task

        with (
            patch.object(main.logger, "warning") as mock_warning,
            patch.object(
                main.bot, "delete_webhook", new=AsyncMock()
            ) as mock_delete_webhook,
            patch.object(
                main.dp, "start_polling", new=AsyncMock()
            ) as mock_start_polling,
            patch.object(
                main.dp,
                "resolve_used_update_types",
                return_value=["message"],
            ),
            patch(
                "backend.app.main.asyncio.create_task",
                side_effect=fake_create_task,
            ) as mock_create_task,
        ):
            await main._start_polling()

        mock_warning.assert_called_once()
        mock_delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
        mock_start_polling.assert_called_once_with(
            main.bot,
            handle_signals=False,
            close_bot_session=False,
            allowed_updates=["message"],
        )
        mock_create_task.assert_called_once()
        assert main._polling_task is fake_polling_task
        for polling_coroutine in started_polling_coroutines:
            polling_coroutine.close()

    async def test_stop_polling_does_not_fail_when_polling_not_started(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_stop_polling безопасен, даже если polling не запущен."""
        monkeypatch.setattr(main, "_polling_task", None)

        with patch.object(
            main.dp,
            "stop_polling",
            new=AsyncMock(side_effect=RuntimeError("Polling is not started")),
        ):
            await main._stop_polling()


class TestAllowedUpdates:
    """Проверяет передачу allowed_updates при запуске polling и webhook."""

    async def test_polling_passes_allowed_updates(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_start_polling передаёт allowed_updates в dp.start_polling."""
        monkeypatch.setattr(main.settings, "APP_ENV", "dev")
        monkeypatch.setattr(main.settings, "WEBHOOK_URL", None)
        monkeypatch.setattr(main, "_polling_task", None)

        fake_polling_task = MagicMock()
        started_polling_coroutines: list[Coroutine[None, None, None]] = []

        def fake_create_task(
            polling_coroutine: Coroutine[None, None, None],
        ) -> MagicMock:
            started_polling_coroutines.append(polling_coroutine)
            return fake_polling_task

        with (
            patch.object(main.bot, "delete_webhook", new=AsyncMock()),
            patch.object(
                main.dp, "start_polling", new=AsyncMock()
            ) as mock_start_polling,
            patch.object(
                main.dp,
                "resolve_used_update_types",
                return_value=["message", "callback_query"],
            ),
            patch(
                "backend.app.main.asyncio.create_task",
                side_effect=fake_create_task,
            ),
        ):
            await main._start_polling()

        # Проверяем, что start_polling вызван с allowed_updates
        mock_start_polling.assert_called_once()
        call_kwargs = mock_start_polling.call_args
        assert "allowed_updates" in call_kwargs.kwargs, (
            "dp.start_polling должен получать параметр allowed_updates"
        )

        for polling_coroutine in started_polling_coroutines:
            polling_coroutine.close()

    async def test_webhook_passes_allowed_updates(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_setup_webhook передаёт allowed_updates в bot.set_webhook."""
        monkeypatch.setattr(main.settings, "APP_ENV", "prod")
        monkeypatch.setattr(main.settings, "WEBHOOK_URL", "https://example.com/webhook")
        monkeypatch.setattr(main.settings, "WEBHOOK_SECRET", "test-secret")

        with (
            patch.object(main.bot, "set_webhook", new=AsyncMock()) as mock_set_webhook,
            patch.object(
                main.dp,
                "resolve_used_update_types",
                return_value=["message", "callback_query"],
            ),
        ):
            await main._setup_webhook()

        # Проверяем, что set_webhook вызван с allowed_updates
        mock_set_webhook.assert_awaited_once()
        call_kwargs = mock_set_webhook.call_args
        assert "allowed_updates" in call_kwargs.kwargs, (
            "bot.set_webhook должен получать параметр allowed_updates"
        )


class TestLoggingConfiguration:
    """Проверяет контракт настройки root logger."""

    def test_configure_logging_updates_root_level_when_handlers_exist(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_configure_logging должен менять level даже при существующих handlers."""
        root_logger = logging.getLogger()
        original_level = root_logger.level
        test_handler = logging.StreamHandler(io.StringIO())

        root_logger.addHandler(test_handler)
        root_logger.setLevel(logging.WARNING)
        monkeypatch.setattr(main.settings, "APP_ENV", "dev")

        try:
            main._configure_logging()
            assert root_logger.level == logging.DEBUG
        finally:
            root_logger.removeHandler(test_handler)
            root_logger.setLevel(original_level)
