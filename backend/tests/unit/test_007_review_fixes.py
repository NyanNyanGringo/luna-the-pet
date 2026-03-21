"""
Тесты для 5 исправлений агентских инструментов (красная фаза TDD).

Покрывает:
1. Лекарства: фильтрация по end_date при active_only=True
2. Диеты: запрет перекрытия при явном end_date
3. Кормления: start_date/end_date вместо days
4. Измерения: start_date/end_date фильтрация
5. Заметки: дефолтный limit=10

Тесты написаны ДО реализации — ожидается, что большинство упадут.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.agent.tools import get_tool_definitions
from backend.app.services import health_service, nutrition_service
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции и константы
# ═══════════════════════════════════════════════════════════════════════════════

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


def _get_tool_by_name(name: str) -> dict | None:
    """Возвращает определение инструмента по имени или None."""
    for tool in get_tool_definitions():
        if tool["name"] == name:
            return tool
    return None


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
# 1. Лекарства: активность по end_date
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicationEndDateFiltering:
    """Проверки фильтрации лекарств по end_date при active_only=True."""

    async def test_expired_medication_excluded_when_active_only(self) -> None:
        """Просроченный препарат (end_date < today, is_active=True) НЕ возвращается."""
        # Подготовка: get_medications должен принимать today и фильтровать по нему
        mock_get_medications = AsyncMock(return_value=[])
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=mock_get_medications,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна", "active_only": True},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        # Handler должен передавать today в сервис
        mock_get_medications.assert_called_once()
        call_kwargs = mock_get_medications.call_args
        assert call_kwargs.kwargs.get("today") == _TODAY or (
            len(call_kwargs.args) > 3 and call_kwargs.args[3] == _TODAY
        ), "Handler должен передавать workspace_today в сервис get_medications"

    async def test_service_get_medications_accepts_today_parameter(self) -> None:
        """Сигнатура get_medications принимает параметр today."""
        import inspect

        sig = inspect.signature(health_service.get_medications)
        param_names = list(sig.parameters.keys())
        assert "today" in param_names, (
            "get_medications должен принимать параметр today "
            f"для фильтрации по дате. Текущие параметры: {param_names}"
        )

    async def test_medication_without_end_date_returned_when_active(self) -> None:
        """Препарат без end_date (is_active=True) возвращается при active_only=True.

        Сервис не должен исключать лекарства без end_date —
        это бессрочные назначения.
        """
        # Этот тест проверяет логику на уровне сервиса:
        # Лекарство с is_active=True и end_date=None должно пройти фильтр.
        # Мы проверяем через handler, что результат содержит такое лекарство.
        med_no_end = SimpleNamespace(
            name="Витамин D",
            dosage="1 таб",
            frequency="1 раз в день",
            start_date=datetime.date(2026, 1, 1),
            end_date=None,
            is_active=True,
            notes=None,
        )
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=[med_no_end]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна", "active_only": True},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        assert "Витамин D" in result

    async def test_medication_with_future_end_date_returned(self) -> None:
        """Препарат с end_date >= today возвращается при active_only=True."""
        med_future = SimpleNamespace(
            name="Антибиотик",
            dosage="500 мг",
            frequency="2 раза в день",
            start_date=datetime.date(2026, 3, 10),
            end_date=datetime.date(2026, 3, 20),  # > today (2026-03-17)
            is_active=True,
            notes=None,
        )
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=[med_future]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна", "active_only": True},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        assert "Антибиотик" in result

    async def test_all_medications_returned_when_not_active_only(self) -> None:
        """При active_only=False возвращаются все лекарства, включая просроченные."""
        mock_get_medications = AsyncMock(return_value=[])
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=mock_get_medications,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна", "active_only": False},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_medications.assert_called_once()
        call_kwargs = mock_get_medications.call_args
        assert call_kwargs.kwargs.get("active_only") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Диеты: запрет перекрытия при явном end_date
# ═══════════════════════════════════════════════════════════════════════════════


class TestDietOverlapWithExplicitEndDate:
    """Проверки запрета пересечения диет при явном end_date."""

    async def test_new_diet_with_explicit_end_date_overlapping_raises(self) -> None:
        """Новая диета с явным end_date, пересекающая открытую текущую → ValueError.

        Сценарий: открытая диета с start_date=2026-03-01, end_date=None.
        Новая диета: start_date=2026-03-10, end_date=2026-03-20.
        Интервалы пересекаются → ValueError.
        """
        # Мокаем открытую диету
        open_diet = SimpleNamespace(
            id=1,
            pet_id=1,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 3, 1),
            end_date=None,
            recorded_by=_USER_ID,
        )
        mock_session = AsyncMock(spec=AsyncSession)

        # _get_open_diets возвращает открытую диету
        with (
            patch(
                "backend.app.services.nutrition_service._get_open_diets",
                new=AsyncMock(return_value=[open_diet]),
            ),
            patch(
                "backend.app.services.nutrition_service._get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            pytest.raises(ValueError, match="перес|overlap|хроно"),
        ):
            await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Hill's",
                start_date=datetime.date(2026, 3, 10),
                recorded_by=_USER_ID,
                end_date=datetime.date(2026, 3, 20),
            )

    async def test_historical_diet_with_explicit_end_date_before_current_ok(
        self,
    ) -> None:
        """Историческая диета (до start_date текущей) с end_date — не ошибка.

        Сценарий: открытая диета с start_date=2026-03-01, end_date=None.
        Новая: start_date=2026-02-01, end_date=2026-02-15 (полностью ДО текущей).
        """
        open_diet = SimpleNamespace(
            id=1,
            pet_id=1,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 3, 1),
            end_date=None,
            recorded_by=_USER_ID,
        )
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.flush = AsyncMock()
        mock_session.add = MagicMock()

        with (
            patch(
                "backend.app.services.nutrition_service._get_open_diets",
                new=AsyncMock(return_value=[open_diet]),
            ),
            patch(
                "backend.app.services.nutrition_service._get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            patch(
                "backend.app.services.nutrition_service._log_diet_change",
                new=AsyncMock(),
            ),
        ):
            # Не должно бросить ValueError
            result = await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Старый корм",
                start_date=datetime.date(2026, 2, 1),
                recorded_by=_USER_ID,
                end_date=datetime.date(2026, 2, 15),
            )
            assert result is not None

    async def test_new_open_diet_auto_closes_current(self) -> None:
        """Новая открытая диета (без end_date) автоматически закрывает текущую.

        Это существующее поведение — убеждаемся, что оно сохранится.
        """
        open_diet = SimpleNamespace(
            id=1,
            pet_id=1,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 3, 1),
            end_date=None,
            recorded_by=_USER_ID,
        )
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.flush = AsyncMock()
        mock_session.add = MagicMock()

        with (
            patch(
                "backend.app.services.nutrition_service._get_open_diets",
                new=AsyncMock(return_value=[open_diet]),
            ),
            patch(
                "backend.app.services.nutrition_service._get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            patch(
                "backend.app.services.nutrition_service._close_open_diet",
                new=AsyncMock(),
            ) as mock_close,
            patch(
                "backend.app.services.nutrition_service._log_diet_change",
                new=AsyncMock(),
            ),
        ):
            await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Новый корм",
                start_date=datetime.date(2026, 3, 15),
                recorded_by=_USER_ID,
                # Без end_date — открытая диета
            )
            # Текущая диета должна быть автозакрыта
            mock_close.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Кормления: start_date/end_date вместо days
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedingHistoryDateRange:
    """Проверки замены days на start_date/end_date в get_feeding_history."""

    # --- Тесты tool schema ---

    def test_days_parameter_absent_in_schema(self) -> None:
        """Параметр days ОТСУТСТВУЕТ в schema get_feeding_history."""
        tool = _get_tool_by_name("get_feeding_history")
        assert tool is not None, "Инструмент get_feeding_history не найден"
        properties = tool["parameters"]["properties"]
        assert "days" not in properties, (
            "Параметр 'days' должен быть удалён из schema get_feeding_history. "
            "Вместо него — start_date и end_date."
        )

    def test_start_date_present_in_schema(self) -> None:
        """Параметр start_date ПРИСУТСТВУЕТ в schema get_feeding_history."""
        tool = _get_tool_by_name("get_feeding_history")
        assert tool is not None
        properties = tool["parameters"]["properties"]
        assert "start_date" in properties, (
            "Параметр 'start_date' должен быть в schema get_feeding_history"
        )

    def test_end_date_present_in_schema(self) -> None:
        """Параметр end_date ПРИСУТСТВУЕТ в schema get_feeding_history."""
        tool = _get_tool_by_name("get_feeding_history")
        assert tool is not None
        properties = tool["parameters"]["properties"]
        assert "end_date" in properties, (
            "Параметр 'end_date' должен быть в schema get_feeding_history"
        )

    # --- Тесты handler ---

    async def test_default_7_days_when_no_dates(self) -> None:
        """Без start_date/end_date → дефолт последние 7 дней от workspace_today."""
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
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_entries.assert_called_once()
        call_kwargs = mock_get_entries.call_args
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs.args[2]
        # since_dt должен соответствовать _TODAY - 6 дней (7 календарных дней)
        expected_since_date = _TODAY - datetime.timedelta(days=6)
        assert since_dt.date() == expected_since_date, (
            f"Дефолтный since_dt должен быть за 6 дней до workspace_today "
            f"(7 календарных дней включительно). "
            f"Ожидалось: {expected_since_date}, получено: {since_dt.date()}"
        )

    async def test_with_start_date_only(self) -> None:
        """С start_date → since_dt = начало дня start_date."""
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
                arguments={"pet_name": "Луна", "start_date": "2026-03-10"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_entries.assert_called_once()
        call_kwargs = mock_get_entries.call_args
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs.args[2]
        assert since_dt.date() == datetime.date(2026, 3, 10), (
            "since_dt должен быть на дату start_date"
        )

    async def test_with_start_and_end_date(self) -> None:
        """С start_date + end_date → since_dt и until_dt задаются обоими."""
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
        call_kwargs = mock_get_entries.call_args
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs.args[2]
        assert since_dt.date() == datetime.date(2026, 3, 1)
        # Проверяем until_dt — должен быть конец дня end_date
        until_dt = call_kwargs.kwargs.get("until_dt")
        assert until_dt is not None, (
            "Handler должен передавать until_dt в сервис при наличии end_date"
        )
        assert until_dt.date() == datetime.date(2026, 3, 15), (
            "until_dt должен соответствовать end_date"
        )

    async def test_with_end_date_only(self) -> None:
        """С end_date без start_date → since_dt = end_date - 7 дней."""
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
                arguments={"pet_name": "Луна", "end_date": "2026-03-15"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_entries.assert_called_once()
        call_kwargs = mock_get_entries.call_args
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs.args[2]
        # since_dt = end_date - 6 дней (7 календарных дней) = 2026-03-09
        expected_since_date = datetime.date(2026, 3, 15) - datetime.timedelta(days=6)
        assert since_dt.date() == expected_since_date, (
            f"При end_date без start_date since_dt = end_date - 6 дней "
            f"(7 календарных дней включительно). "
            f"Ожидалось: {expected_since_date}, получено: {since_dt.date()}"
        )
        # until_dt = конец дня end_date
        until_dt = call_kwargs.kwargs.get("until_dt")
        assert until_dt is not None, (
            "Handler должен передавать until_dt при наличии end_date"
        )
        assert until_dt.date() == datetime.date(2026, 3, 15)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Измерения: start_date/end_date
# ═══════════════════════════════════════════════════════════════════════════════


class TestMeasurementsDateRange:
    """Проверки добавления start_date/end_date в get_measurements."""

    # --- Тесты tool schema ---

    def test_start_date_present_in_measurements_schema(self) -> None:
        """Параметр start_date ПРИСУТСТВУЕТ в schema get_measurements."""
        tool = _get_tool_by_name("get_measurements")
        assert tool is not None, "Инструмент get_measurements не найден"
        properties = tool["parameters"]["properties"]
        assert "start_date" in properties, (
            "Параметр 'start_date' должен быть в schema get_measurements"
        )

    def test_end_date_present_in_measurements_schema(self) -> None:
        """Параметр end_date ПРИСУТСТВУЕТ в schema get_measurements."""
        tool = _get_tool_by_name("get_measurements")
        assert tool is not None
        properties = tool["parameters"]["properties"]
        assert "end_date" in properties, (
            "Параметр 'end_date' должен быть в schema get_measurements"
        )

    # --- Тесты handler ---

    async def test_handler_without_dates_calls_service_without_dates(self) -> None:
        """Без периода → вызов сервиса без start_date/end_date."""
        mock_get_measurements = AsyncMock(return_value=[])
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_measurements",
                new=mock_get_measurements,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_measurements",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_measurements.assert_called_once()
        call_kwargs = mock_get_measurements.call_args.kwargs
        # Без дат — не должны быть переданы
        assert call_kwargs.get("start_date") is None
        assert call_kwargs.get("end_date") is None

    async def test_handler_with_dates_passes_to_service(self) -> None:
        """С start_date + end_date → handler передаёт их в сервис."""
        mock_get_measurements = AsyncMock(return_value=[])
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_measurements",
                new=mock_get_measurements,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_measurements",
                arguments={
                    "pet_name": "Луна",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        mock_get_measurements.assert_called_once()
        call_kwargs = mock_get_measurements.call_args.kwargs
        assert call_kwargs.get("start_date") == datetime.date(2026, 3, 1), (
            "Handler должен передавать start_date в сервис get_measurements"
        )
        assert call_kwargs.get("end_date") == datetime.date(2026, 3, 15), (
            "Handler должен передавать end_date в сервис get_measurements"
        )

    async def test_handler_parses_dates_via_parse_date_field(self) -> None:
        """Handler парсит даты через _parse_date_field."""
        mock_get_measurements = AsyncMock(return_value=[])
        mock_parse_date = MagicMock(
            side_effect=lambda raw, **kw: datetime.date(2026, 3, 1)
        )
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_measurements",
                new=mock_get_measurements,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
            patch(
                "backend.app.agent.tool_handlers._parse_date_field",
                new=mock_parse_date,
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_measurements",
                arguments={
                    "pet_name": "Луна",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        # _parse_date_field должен быть вызван для обоих дат
        assert mock_parse_date.call_count >= 2, (
            "_parse_date_field должен быть вызван для start_date и end_date"
        )

    async def test_service_get_measurements_accepts_date_parameters(self) -> None:
        """Сигнатура get_measurements принимает start_date и end_date."""
        import inspect

        sig = inspect.signature(health_service.get_measurements)
        param_names = list(sig.parameters.keys())
        assert "start_date" in param_names, (
            f"get_measurements должен принимать start_date. Текущие: {param_names}"
        )
        assert "end_date" in param_names, (
            f"get_measurements должен принимать end_date. Текущие: {param_names}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Заметки: дефолтный limit = 10
# ═══════════════════════════════════════════════════════════════════════════════


class TestNotesDefaultLimit:
    """Проверки дефолтного limit=10 для заметок."""

    async def test_handler_default_limit_is_10(self) -> None:
        """Handler без limit → вызывает сервис с limit=10."""
        mock_get_notes = AsyncMock(return_value=[])
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_notes",
                new=mock_get_notes,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_notes",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_get_notes.assert_called_once()
        call_kwargs = mock_get_notes.call_args
        # limit должен быть 10, а не 20
        limit_value = call_kwargs.kwargs.get("limit")
        if limit_value is None:
            # Может быть передан позиционно
            args = call_kwargs.args
            # session, pet_id, limit
            limit_value = args[2] if len(args) > 2 else None
        assert limit_value == 10, (
            f"Handler должен передавать limit=10 по умолчанию. Получено: {limit_value}"
        )

    def test_service_default_limit_is_10(self) -> None:
        """Сервис get_notes имеет дефолтный limit=10."""
        import inspect

        sig = inspect.signature(health_service.get_notes)
        limit_param = sig.parameters.get("limit")
        assert limit_param is not None, "get_notes должен иметь параметр limit"
        assert limit_param.default == 10, (
            f"Дефолтный limit в get_notes должен быть 10. "
            f"Текущее значение: {limit_param.default}"
        )
