"""
Тесты для Phase 6 (US4) — сервисы, инструменты, обработчики и i18n
для 5 новых сущностей: Measurement, VetVisit, MoodLog, HeatCycle, Document.

Покрывает:
1. T016: Сервисные методы в health_service.py (8 методов)
2. T017: Сервис document_service.py (2 метода)
3. T018: Определения 10 новых инструментов в tools.py
4. T019: Обработчики 10 новых инструментов в tool_handlers.py
5. T020: i18n-сообщения для 5 сущностей (ru/en)

Тесты написаны ДО реализации — ожидается, что они упадут при первом запуске.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.agent.i18n import _MESSAGES, get_message
from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.agent.tools import get_tool_definitions
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции и фикстуры
# ═══════════════════════════════════════════════════════════════════════════════


def _get_tool_names() -> set[str]:
    """Возвращает множество имён всех зарегистрированных инструментов."""
    return {tool["name"] for tool in get_tool_definitions()}


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
    mock_result.scalar_one_or_none.return_value = SimpleNamespace(
        id=1,
        name="Луна",
        species="dog",
        workspace_id=1,
        is_active=True,
    )
    session.execute = AsyncMock(return_value=mock_result)
    return session


_WORKSPACE_ID = 1
_USER_ID = 100500
_PET_STUB = SimpleNamespace(
    id=1,
    name="Луна",
    species="dog",
    workspace_id=_WORKSPACE_ID,
    is_active=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# T018: Определения инструментов (tools.py) — 10 новых инструментов
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddMeasurementToolDefinition:
    """Проверки определения инструмента add_measurement."""

    def test_tool_exists(self) -> None:
        """Инструмент add_measurement присутствует в списке."""
        assert "add_measurement" in _get_tool_names()

    def test_type_is_function(self) -> None:
        """add_measurement имеет type='function'."""
        tool = _get_tool_by_name("add_measurement")
        assert tool is not None
        assert tool["type"] == "function"

    def test_required_params(self) -> None:
        """add_measurement требует pet_name, measurement_type, value, measured_at."""
        tool = _get_tool_by_name("add_measurement")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {
            "pet_name",
            "measurement_type",
            "value",
            "measured_at",
        }

    def test_value_type_is_number(self) -> None:
        """Параметр value имеет тип number."""
        tool = _get_tool_by_name("add_measurement")
        assert tool is not None
        assert tool["parameters"]["properties"]["value"]["type"] == "number"


class TestGetMeasurementsToolDefinition:
    """Проверки определения инструмента get_measurements."""

    def test_tool_exists(self) -> None:
        """Инструмент get_measurements присутствует в списке."""
        assert "get_measurements" in _get_tool_names()

    def test_required_params(self) -> None:
        """get_measurements требует только pet_name."""
        tool = _get_tool_by_name("get_measurements")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {"pet_name"}

    def test_has_measurement_type_optional(self) -> None:
        """get_measurements содержит опциональный measurement_type."""
        tool = _get_tool_by_name("get_measurements")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "measurement_type" in props
        assert "measurement_type" not in tool["parameters"]["required"]

    def test_has_limit_optional(self) -> None:
        """get_measurements содержит опциональный limit."""
        tool = _get_tool_by_name("get_measurements")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "limit" in props
        assert "limit" not in tool["parameters"]["required"]


class TestAddVetVisitToolDefinition:
    """Проверки определения инструмента add_vet_visit."""

    def test_tool_exists(self) -> None:
        """Инструмент add_vet_visit присутствует в списке."""
        assert "add_vet_visit" in _get_tool_names()

    def test_required_params(self) -> None:
        """add_vet_visit требует pet_name, reason, visit_date."""
        tool = _get_tool_by_name("add_vet_visit")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {
            "pet_name",
            "reason",
            "visit_date",
        }

    def test_has_optional_params(self) -> None:
        """add_vet_visit содержит опциональные status, clinic, notes."""
        tool = _get_tool_by_name("add_vet_visit")
        assert tool is not None
        props = tool["parameters"]["properties"]
        for param in ("status", "clinic", "notes"):
            assert param in props
            assert param not in tool["parameters"]["required"]


class TestGetVetVisitsToolDefinition:
    """Проверки определения инструмента get_vet_visits."""

    def test_tool_exists(self) -> None:
        """Инструмент get_vet_visits присутствует в списке."""
        assert "get_vet_visits" in _get_tool_names()

    def test_required_params(self) -> None:
        """get_vet_visits требует только pet_name."""
        tool = _get_tool_by_name("get_vet_visits")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {"pet_name"}

    def test_has_status_optional(self) -> None:
        """get_vet_visits содержит опциональный status."""
        tool = _get_tool_by_name("get_vet_visits")
        assert tool is not None
        assert "status" in tool["parameters"]["properties"]
        assert "status" not in tool["parameters"]["required"]


class TestAddMoodLogToolDefinition:
    """Проверки определения инструмента add_mood_log."""

    def test_tool_exists(self) -> None:
        """Инструмент add_mood_log присутствует в списке."""
        assert "add_mood_log" in _get_tool_names()

    def test_required_params(self) -> None:
        """add_mood_log требует pet_name, mood, appetite, log_date."""
        tool = _get_tool_by_name("add_mood_log")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {
            "pet_name",
            "mood",
            "appetite",
            "log_date",
        }

    def test_has_notes_optional(self) -> None:
        """add_mood_log содержит опциональный notes."""
        tool = _get_tool_by_name("add_mood_log")
        assert tool is not None
        assert "notes" in tool["parameters"]["properties"]
        assert "notes" not in tool["parameters"]["required"]


class TestGetMoodLogsToolDefinition:
    """Проверки определения инструмента get_mood_logs."""

    def test_tool_exists(self) -> None:
        """Инструмент get_mood_logs присутствует в списке."""
        assert "get_mood_logs" in _get_tool_names()

    def test_required_params(self) -> None:
        """get_mood_logs требует только pet_name."""
        tool = _get_tool_by_name("get_mood_logs")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {"pet_name"}

    def test_has_limit_optional(self) -> None:
        """get_mood_logs содержит опциональный limit."""
        tool = _get_tool_by_name("get_mood_logs")
        assert tool is not None
        assert "limit" in tool["parameters"]["properties"]
        assert "limit" not in tool["parameters"]["required"]


class TestAddHeatCycleToolDefinition:
    """Проверки определения инструмента add_heat_cycle."""

    def test_tool_exists(self) -> None:
        """Инструмент add_heat_cycle присутствует в списке."""
        assert "add_heat_cycle" in _get_tool_names()

    def test_required_params(self) -> None:
        """add_heat_cycle требует pet_name, start_date."""
        tool = _get_tool_by_name("add_heat_cycle")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {
            "pet_name",
            "start_date",
        }

    def test_has_optional_params(self) -> None:
        """add_heat_cycle содержит опциональные end_date, notes."""
        tool = _get_tool_by_name("add_heat_cycle")
        assert tool is not None
        props = tool["parameters"]["properties"]
        for param in ("end_date", "notes"):
            assert param in props
            assert param not in tool["parameters"]["required"]


class TestGetHeatCyclesToolDefinition:
    """Проверки определения инструмента get_heat_cycles."""

    def test_tool_exists(self) -> None:
        """Инструмент get_heat_cycles присутствует в списке."""
        assert "get_heat_cycles" in _get_tool_names()

    def test_required_params(self) -> None:
        """get_heat_cycles требует только pet_name."""
        tool = _get_tool_by_name("get_heat_cycles")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {"pet_name"}


# ═══════════════════════════════════════════════════════════════════════════════
# T019: Обработчики add-инструментов (tool_handlers.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleAddMeasurement:
    """Проверки обработчика add_measurement."""

    async def test_dispatches_correctly(self) -> None:
        """handle_tool_call маршрутизирует add_measurement к обработчику."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            measurement_type="temperature",
            value=Decimal("38.5"),
            unit="°C",
            measured_at=datetime.date(2026, 3, 10),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=AsyncMock(return_value=mock_record),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "temperature",
                    "value": 38.5,
                    "measured_at": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_resolves_pet_and_calls_service(self) -> None:
        """Обработчик резолвит питомца и вызывает health_service.add_measurement."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            measurement_type="temperature",
            value=Decimal("38.5"),
            unit="°C",
            measured_at=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "temperature",
                    "value": 38.5,
                    "measured_at": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["pet_id"] == _PET_STUB.id
        assert call_kwargs["measurement_type"] == "temperature"
        assert call_kwargs["measured_at"] == datetime.date(2026, 3, 10)
        assert call_kwargs["recorded_by"] == _USER_ID

    async def test_auto_detects_unit_temperature(self) -> None:
        """Для temperature в сервис передаётся каноничная единица 'C'."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            measurement_type="temperature",
            value=Decimal("38.5"),
            unit="C",
            measured_at=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "temperature",
                    "value": 38.5,
                    "measured_at": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["unit"] == "C"

    async def test_auto_detects_unit_pulse(self) -> None:
        """Для pulse в сервис передаётся каноничная единица 'bpm'."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            measurement_type="pulse",
            value=Decimal("80"),
            unit="bpm",
            measured_at=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "pulse",
                    "value": 80,
                    "measured_at": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["unit"] == "bpm"

    async def test_auto_detects_unit_respiration(self) -> None:
        """Для respiration в сервис передаётся каноничная единица 'rpm'."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            measurement_type="respiration",
            value=Decimal("20"),
            unit="rpm",
            measured_at=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "respiration",
                    "value": 20,
                    "measured_at": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["unit"] == "rpm"


class TestHandleGetMeasurements:
    """Проверки обработчика get_measurements."""

    async def test_returns_no_records_message(self) -> None:
        """При пустом списке возвращает i18n сообщение no_measurements."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_measurements",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_measurements",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        expected = get_message("no_measurements", language="ru")
        assert result == expected

    async def test_formats_records_with_bullet(self) -> None:
        """Записи форматируются в формате bullet."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                measurement_type="temperature",
                value=Decimal("38.5"),
                unit="°C",
                measured_at=datetime.date(2026, 3, 10),
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_measurements",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_measurements",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "•" in result
        assert "38.5" in result
        assert "°C" in result

    async def test_passes_measurement_type_filter(self) -> None:
        """Обработчик передаёт measurement_type в сервис."""
        session = _make_mock_session()
        mock_get = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_measurements",
                new=mock_get,
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
                    "measurement_type": "pulse",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs.get("measurement_type") == "pulse"


class TestHandleAddVetVisit:
    """Проверки обработчика add_vet_visit."""

    async def test_dispatches_correctly(self) -> None:
        """handle_tool_call маршрутизирует add_vet_visit к обработчику."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            reason="Плановый осмотр",
            visit_date=datetime.date(2026, 3, 15),
            status="planned",
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_vet_visit",
                new=AsyncMock(return_value=mock_record),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_vet_visit",
                arguments={
                    "pet_name": "Луна",
                    "reason": "Плановый осмотр",
                    "visit_date": "2026-03-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_passes_optional_params(self) -> None:
        """Обработчик передаёт опциональные status, clinic, notes."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            reason="Вакцинация",
            visit_date=datetime.date(2026, 3, 15),
            status="planned",
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_vet_visit",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_vet_visit",
                arguments={
                    "pet_name": "Луна",
                    "reason": "Вакцинация",
                    "visit_date": "2026-03-15",
                    "status": "planned",
                    "clinic": "ВетКлиника",
                    "notes": "Взять паспорт",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs.get("status") == "planned"
        assert call_kwargs.get("clinic") == "ВетКлиника"
        assert call_kwargs.get("notes") == "Взять паспорт"


class TestHandleGetVetVisits:
    """Проверки обработчика get_vet_visits."""

    async def test_returns_no_records_message(self) -> None:
        """При пустом списке возвращает i18n сообщение no_vet_visits."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_vet_visits",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_vet_visits",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        expected = get_message("no_vet_visits", language="ru")
        assert result == expected

    async def test_formats_records_with_bullet(self) -> None:
        """Записи форматируются в формате bullet."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                reason="Осмотр",
                visit_date=datetime.date(2026, 3, 15),
                status="planned",
                clinic=None,
                notes=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_vet_visits",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_vet_visits",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "•" in result
        assert "Осмотр" in result
        assert "2026-03-15" in result


class TestHandleAddMoodLog:
    """Проверки обработчика add_mood_log."""

    async def test_dispatches_correctly(self) -> None:
        """handle_tool_call маршрутизирует add_mood_log к обработчику."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            mood="good",
            appetite="good",
            log_date=datetime.date(2026, 3, 10),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_mood_log",
                new=AsyncMock(return_value=mock_record),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_mood_log",
                arguments={
                    "pet_name": "Луна",
                    "mood": "good",
                    "appetite": "good",
                    "log_date": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_resolves_pet_and_calls_service(self) -> None:
        """Обработчик резолвит питомца и вызывает health_service.add_mood_log."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            mood="good",
            appetite="good",
            log_date=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_mood_log",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_mood_log",
                arguments={
                    "pet_name": "Луна",
                    "mood": "good",
                    "appetite": "good",
                    "log_date": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["pet_id"] == _PET_STUB.id
        assert call_kwargs["mood"] == "good"
        assert call_kwargs["appetite"] == "good"
        assert call_kwargs["log_date"] == datetime.date(2026, 3, 10)
        assert call_kwargs["recorded_by"] == _USER_ID


class TestHandleGetMoodLogs:
    """Проверки обработчика get_mood_logs."""

    async def test_returns_no_records_message(self) -> None:
        """При пустом списке возвращает i18n сообщение no_mood_logs."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_mood_logs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_mood_logs",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        expected = get_message("no_mood_logs", language="ru")
        assert result == expected

    async def test_formats_records_with_bullet(self) -> None:
        """Записи форматируются в формате bullet."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                mood="good",
                appetite="good",
                log_date=datetime.date(2026, 3, 10),
                notes=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_mood_logs",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_mood_logs",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "•" in result
        assert "good" in result
        assert "2026-03-10" in result


class TestHandleAddHeatCycle:
    """Проверки обработчика add_heat_cycle."""

    async def test_dispatches_correctly(self) -> None:
        """handle_tool_call маршрутизирует add_heat_cycle к обработчику."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            start_date=datetime.date(2026, 3, 1),
            end_date=None,
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_heat_cycle",
                new=AsyncMock(return_value=mock_record),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_heat_cycle",
                arguments={
                    "pet_name": "Луна",
                    "start_date": "2026-03-01",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_passes_optional_end_date(self) -> None:
        """Обработчик парсит и передаёт end_date."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            start_date=datetime.date(2026, 3, 1),
            end_date=datetime.date(2026, 3, 14),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_heat_cycle",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_heat_cycle",
                arguments={
                    "pet_name": "Луна",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-14",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs.get("end_date") == datetime.date(2026, 3, 14)


class TestHandleGetHeatCycles:
    """Проверки обработчика get_heat_cycles."""

    async def test_returns_no_records_message(self) -> None:
        """При пустом списке возвращает i18n сообщение no_heat_cycles."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_heat_cycles",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_heat_cycles",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        expected = get_message("no_heat_cycles", language="ru")
        assert result == expected

    async def test_formats_records_with_bullet(self) -> None:
        """Записи форматируются в формате bullet."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                start_date=datetime.date(2026, 3, 1),
                end_date=datetime.date(2026, 3, 14),
                notes=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_heat_cycles",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_heat_cycles",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "•" in result
        assert "2026-03-01" in result
        assert "2026-03-14" in result


# ═══════════════════════════════════════════════════════════════════════════════
# T020: i18n сообщения (i18n.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewEntityI18n:
    """Проверки i18n ключей для 5 новых сущностей."""

    # Measurement
    def test_measurement_saved_ru_exists(self) -> None:
        """Ключ measurement_saved существует в русских сообщениях."""
        assert "measurement_saved" in _MESSAGES["ru"]

    def test_measurement_saved_en_exists(self) -> None:
        """Ключ measurement_saved существует в английских сообщениях."""
        assert "measurement_saved" in _MESSAGES["en"]

    def test_no_measurements_ru_exists(self) -> None:
        """Ключ no_measurements существует в русских сообщениях."""
        assert "no_measurements" in _MESSAGES["ru"]

    def test_no_measurements_en_exists(self) -> None:
        """Ключ no_measurements существует в английских сообщениях."""
        assert "no_measurements" in _MESSAGES["en"]

    # VetVisit
    def test_vet_visit_saved_ru_exists(self) -> None:
        """Ключ vet_visit_saved существует в русских сообщениях."""
        assert "vet_visit_saved" in _MESSAGES["ru"]

    def test_vet_visit_saved_en_exists(self) -> None:
        """Ключ vet_visit_saved существует в английских сообщениях."""
        assert "vet_visit_saved" in _MESSAGES["en"]

    def test_no_vet_visits_ru_exists(self) -> None:
        """Ключ no_vet_visits существует в русских сообщениях."""
        assert "no_vet_visits" in _MESSAGES["ru"]

    def test_no_vet_visits_en_exists(self) -> None:
        """Ключ no_vet_visits существует в английских сообщениях."""
        assert "no_vet_visits" in _MESSAGES["en"]

    # MoodLog
    def test_mood_log_saved_ru_exists(self) -> None:
        """Ключ mood_log_saved существует в русских сообщениях."""
        assert "mood_log_saved" in _MESSAGES["ru"]

    def test_mood_log_saved_en_exists(self) -> None:
        """Ключ mood_log_saved существует в английских сообщениях."""
        assert "mood_log_saved" in _MESSAGES["en"]

    def test_no_mood_logs_ru_exists(self) -> None:
        """Ключ no_mood_logs существует в русских сообщениях."""
        assert "no_mood_logs" in _MESSAGES["ru"]

    def test_no_mood_logs_en_exists(self) -> None:
        """Ключ no_mood_logs существует в английских сообщениях."""
        assert "no_mood_logs" in _MESSAGES["en"]

    # HeatCycle
    def test_heat_cycle_saved_ru_exists(self) -> None:
        """Ключ heat_cycle_saved существует в русских сообщениях."""
        assert "heat_cycle_saved" in _MESSAGES["ru"]

    def test_heat_cycle_saved_en_exists(self) -> None:
        """Ключ heat_cycle_saved существует в английских сообщениях."""
        assert "heat_cycle_saved" in _MESSAGES["en"]

    def test_no_heat_cycles_ru_exists(self) -> None:
        """Ключ no_heat_cycles существует в русских сообщениях."""
        assert "no_heat_cycles" in _MESSAGES["ru"]

    def test_no_heat_cycles_en_exists(self) -> None:
        """Ключ no_heat_cycles существует в английских сообщениях."""
        assert "no_heat_cycles" in _MESSAGES["en"]

    # Форматирование шаблонов
    def test_measurement_saved_ru_format(self) -> None:
        """Русский шаблон measurement_saved форматируется корректно."""
        result = get_message(
            "measurement_saved",
            language="ru",
            measurement_type="temperature",
            value=Decimal("38.5"),
            unit="°C",
        )
        assert "38.5" in result

    def test_vet_visit_saved_ru_format(self) -> None:
        """Русский шаблон vet_visit_saved форматируется корректно."""
        result = get_message(
            "vet_visit_saved",
            language="ru",
            reason="Осмотр",
            visit_date=datetime.date(2026, 3, 15),
        )
        assert "Осмотр" in result

    def test_mood_log_saved_ru_format(self) -> None:
        """Русский шаблон mood_log_saved форматируется корректно."""
        result = get_message(
            "mood_log_saved",
            language="ru",
            mood="good",
            appetite="good",
        )
        assert "good" in result

    def test_heat_cycle_saved_ru_format(self) -> None:
        """Русский шаблон heat_cycle_saved форматируется корректно."""
        result = get_message(
            "heat_cycle_saved",
            language="ru",
            start_date=datetime.date(2026, 3, 1),
        )
        assert "2026-03-01" in result
