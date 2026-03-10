"""
Тесты bootstrap-логики unit-окружения.

Проверяет устойчивость helper-функции _ensure_session_env_and_preimport()
к внешнему окружению, включая APP_ENV=prod.
"""

import os

import pytest
from backend.tests.unit import conftest as unit_conftest


class TestUnitBootstrap:
    """Контракты bootstrap для unit-тестов."""

    def test_bootstrap_overrides_external_prod_app_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Внешний APP_ENV=prod не должен пробрасываться в unit-bootstrap."""
        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.delenv("WEBHOOK_URL", raising=False)

        unit_conftest._ensure_session_env_and_preimport()
        assert os.environ["APP_ENV"] == "dev"
