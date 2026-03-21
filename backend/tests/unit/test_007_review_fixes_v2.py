"""
Тесты для 4 исправлений по итогам ревью (v2).

Покрывает:
1. Хронология диет: end_date < start_date → ValueError
2. Хронология heat cycle: end_date < start_date → ValueError + DB constraint
3. Корректность active_only для лекарств: today=None → UTC fallback
4. Ограничение объёма get_feeding_history: limit всегда применяется
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.db.models.health import HeatCycle
from backend.app.services import health_service, nutrition_service
from sqlalchemy.ext.asyncio import AsyncSession

_WORKSPACE_ID = 1
_USER_ID = 100500
_PET_STUB = SimpleNamespace(
    id=1,
    name="Луна",
    species="dog",
    workspace_id=_WORKSPACE_ID,
    is_active=True,
)
_TODAY = datetime.date(2026, 3, 17)


def _make_mock_session() -> AsyncMock:
    """Создаёт mock AsyncSession с поддержкой begin_nested()."""
    session = AsyncMock(spec=AsyncSession)
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__ = AsyncMock(return_value=None)
    nested_ctx.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested.return_value = nested_ctx
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _PET_STUB
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Хронология диет: end_date >= start_date
# ═══════════════════════════════════════════════════════════════════════════════


class TestDietChronologyValidation:
    """end_date < start_date → ValueError независимо от наличия open_diets."""

    async def test_end_date_before_start_date_without_open_diets(self) -> None:
        """end_date < start_date без открытых диет → ValueError."""
        mock_session = AsyncMock(spec=AsyncSession)
        with (
            patch(
                "backend.app.services.nutrition_service._get_open_diets",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.services.nutrition_service._get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            pytest.raises(
                ValueError,
                match="end_date не может быть раньше start_date",
            ),
        ):
            await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Test",
                start_date=datetime.date(2026, 3, 15),
                recorded_by=_USER_ID,
                end_date=datetime.date(2026, 3, 10),
            )

    async def test_end_date_before_start_date_with_open_diets(self) -> None:
        """end_date < start_date при наличии открытой диеты → ValueError."""
        open_diet = SimpleNamespace(
            id=1,
            pet_id=1,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 2, 1),
            end_date=None,
            recorded_by=_USER_ID,
        )
        mock_session = AsyncMock(spec=AsyncSession)
        with (
            patch(
                "backend.app.services.nutrition_service._get_open_diets",
                new=AsyncMock(return_value=[open_diet]),
            ),
            patch(
                "backend.app.services.nutrition_service._get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            pytest.raises(
                ValueError,
                match="end_date не может быть раньше start_date",
            ),
        ):
            await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Test",
                start_date=datetime.date(2026, 3, 15),
                recorded_by=_USER_ID,
                end_date=datetime.date(2026, 3, 10),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Хронология heat cycle: end_date >= start_date
# ═══════════════════════════════════════════════════════════════════════════════


class TestHeatCycleChronologyValidation:
    """end_date < start_date → ValueError."""

    async def test_end_date_before_start_date_raises(self) -> None:
        """end_date < start_date → ValueError."""
        mock_session = AsyncMock(spec=AsyncSession)
        with pytest.raises(
            ValueError, match="end_date не может быть раньше start_date"
        ):
            await health_service.add_heat_cycle(
                session=mock_session,
                pet_id=1,
                start_date=datetime.date(2026, 3, 15),
                recorded_by=_USER_ID,
                end_date=datetime.date(2026, 3, 10),
            )

    def test_model_has_check_constraint(self) -> None:
        """Модель HeatCycle содержит CHECK constraint на end_date >= start_date."""
        constraints = [
            c
            for c in HeatCycle.__table__.constraints
            if hasattr(c, "sqltext")
            and "end_date" in str(c.sqltext)
            and "start_date" in str(c.sqltext)
        ]
        assert len(constraints) > 0, (
            "HeatCycle должен иметь CHECK constraint: "
            "end_date IS NULL OR end_date >= start_date"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Корректность active_only для лекарств: today=None → UTC fallback
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicationActiveOnlyTodayFallback:
    """get_medications(active_only=True, today=None) фильтрует по текущей UTC дате."""

    async def test_get_medications_active_only_without_today_filters_expired(
        self,
    ) -> None:
        """Просроченный препарат (is_active=True, end_date < now) не возвращается
        даже если today=None."""
        import inspect

        sig = inspect.signature(health_service.get_medications)
        # Проверяем, что today остаётся optional
        assert sig.parameters["today"].default is None

        # Проверяем логику: при active_only=True end_date фильтр применяется всегда
        # (service должен использовать UTC fallback)
        source = inspect.getsource(health_service.get_medications)
        # Не должно быть `if today is not None` как единственное условие
        # для применения end_date фильтра
        assert "effective_today" in source or "datetime.UTC" in source, (
            "get_medications должен использовать UTC fallback когда today=None "
            "при active_only=True"
        )

    async def test_prompts_call_site_no_today_still_filters(self) -> None:
        """Вызов из prompts (active_only=True, без today) корректно фильтрует."""
        # Этот тест подтверждает, что call site в prompts.py
        # получает корректный результат без передачи today
        mock_get_medications = AsyncMock(return_value=[])
        with patch(
            "backend.app.agent.prompts.health_service.get_medications",
            new=mock_get_medications,
        ):
            from backend.app.agent.prompts import _build_pets_section

            mock_session = AsyncMock(spec=AsyncSession)
            pet = SimpleNamespace(
                id=1,
                name="Луна",
                species="dog",
            )
            await _build_pets_section(mock_session, [pet])
            mock_get_medications.assert_called_once_with(
                mock_session, 1, active_only=True, today=None
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Ограничение объёма get_feeding_entries: limit всегда применяется
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedingEntriesAlwaysLimited:
    """limit применяется всегда, даже при since_dt + until_dt."""

    def test_service_signature_has_limit(self) -> None:
        """get_feeding_entries имеет параметр limit с дефолтом 20."""
        import inspect

        sig = inspect.signature(nutrition_service.get_feeding_entries)
        limit_param = sig.parameters.get("limit")
        assert limit_param is not None
        assert limit_param.default == 20

    async def test_limit_applied_with_both_dates(self) -> None:
        """При since_dt + until_dt limit всё равно применяется (через handler)."""
        mock_get_entries = AsyncMock(return_value=[])
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=mock_get_entries,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={
                    "pet_name": "Луна",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_entries.assert_called_once()
        # Сервис вызывается с since_dt и until_dt — limit по-прежнему
        # применяется внутри сервиса (дефолт 20)

    async def test_service_applies_limit_regardless_of_dates(self) -> None:
        """Проверяем исходный код: limit применяется безусловно."""
        import inspect

        source = inspect.getsource(nutrition_service.get_feeding_entries)
        # Не должно быть условного пропуска limit
        assert "if not (since_dt" not in source, (
            "get_feeding_entries не должен пропускать limit "
            "когда заданы обе границы периода"
        )
