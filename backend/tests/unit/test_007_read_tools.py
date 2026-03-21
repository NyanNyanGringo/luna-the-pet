"""
Тесты для Phase 2 (US1) — инструменты чтения существующих данных питомца.

Покрывает:
1. Определения 6 новых read-инструментов в tools.py
2. Маршрутизацию handle_tool_call к обработчикам read-инструментов
3. Поведение каждого обработчика (резолв питомца, вызов сервиса, форматирование)
4. i18n-сообщения для read-инструментов (ru/en)
5. Сервисный метод get_weight_history с параметром limit

Тесты написаны ДО реализации — ожидается, что они упадут при первом запуске.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.agent.i18n import _MESSAGES, get_message
from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.agent.tools import get_tool_definitions
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции и фикстуры
# ═══════════════════════════════════════════════════════════════════════════════

_READ_TOOL_NAMES = {
    "get_weight_history",
    "get_vaccinations",
    "get_medications",
    "get_notes",
    "get_feeding_history",
    "get_current_diet",
}


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
    # begin_nested() должен возвращать async context manager
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__ = AsyncMock(return_value=None)
    nested_ctx.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested.return_value = nested_ctx
    # execute() должен возвращать результат с scalar_one_or_none()
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
# 1. Определения инструментов (tools.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadToolDefinitions:
    """Проверки наличия 6 read-инструментов в get_tool_definitions()."""

    def test_get_weight_history_tool_exists(self) -> None:
        """Инструмент get_weight_history присутствует в списке."""
        assert "get_weight_history" in _get_tool_names()

    def test_get_vaccinations_tool_exists(self) -> None:
        """Инструмент get_vaccinations присутствует в списке."""
        assert "get_vaccinations" in _get_tool_names()

    def test_get_medications_tool_exists(self) -> None:
        """Инструмент get_medications присутствует в списке."""
        assert "get_medications" in _get_tool_names()

    def test_get_notes_tool_exists(self) -> None:
        """Инструмент get_notes присутствует в списке."""
        assert "get_notes" in _get_tool_names()

    def test_get_feeding_history_tool_exists(self) -> None:
        """Инструмент get_feeding_history присутствует в списке."""
        assert "get_feeding_history" in _get_tool_names()

    def test_get_current_diet_tool_exists(self) -> None:
        """Инструмент get_current_diet присутствует в списке."""
        assert "get_current_diet" in _get_tool_names()

    def test_all_read_tools_present(self) -> None:
        """Все 6 read-инструментов присутствуют в get_tool_definitions()."""
        tool_names = _get_tool_names()
        missing = _READ_TOOL_NAMES - tool_names
        assert not missing, f"Отсутствуют инструменты: {missing}"

    def test_get_weight_history_has_pet_name_required(self) -> None:
        """get_weight_history требует обязательный параметр pet_name."""
        tool = _get_tool_by_name("get_weight_history")
        assert tool is not None
        assert "pet_name" in tool["parameters"]["required"]

    def test_get_weight_history_has_limit_parameter(self) -> None:
        """get_weight_history имеет опциональный параметр limit."""
        tool = _get_tool_by_name("get_weight_history")
        assert tool is not None
        assert "limit" in tool["parameters"]["properties"]

    def test_get_notes_has_limit_parameter(self) -> None:
        """get_notes имеет опциональный параметр limit."""
        tool = _get_tool_by_name("get_notes")
        assert tool is not None
        assert "limit" in tool["parameters"]["properties"]

    def test_get_medications_has_active_only_parameter(self) -> None:
        """get_medications имеет опциональный параметр active_only."""
        tool = _get_tool_by_name("get_medications")
        assert tool is not None
        assert "active_only" in tool["parameters"]["properties"]

    def test_get_feeding_history_has_period_parameters(self) -> None:
        """get_feeding_history имеет опциональные параметры start_date/end_date."""
        tool = _get_tool_by_name("get_feeding_history")
        assert tool is not None
        properties = tool["parameters"]["properties"]
        assert "start_date" in properties
        assert "end_date" in properties
        assert "days" not in properties

    def test_all_read_tools_are_function_type(self) -> None:
        """Все read-инструменты имеют type='function'."""
        for tool_name in _READ_TOOL_NAMES:
            tool = _get_tool_by_name(tool_name)
            assert tool is not None, f"Инструмент {tool_name} не найден"
            assert tool["type"] == "function", (
                f"{tool_name}: type={tool['type']}, ожидается 'function'"
            )

    def test_all_read_tools_require_pet_name(self) -> None:
        """Все read-инструменты требуют обязательный параметр pet_name."""
        for tool_name in _READ_TOOL_NAMES:
            tool = _get_tool_by_name(tool_name)
            assert tool is not None, f"Инструмент {tool_name} не найден"
            assert "pet_name" in tool["parameters"]["required"], (
                f"Инструмент {tool_name} не требует pet_name"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Маршрутизация handle_tool_call (tool_handlers.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadToolRouting:
    """Проверки маршрутизации handle_tool_call к обработчикам read-инструментов."""

    async def test_get_weight_history_dispatches(self) -> None:
        """handle_tool_call маршрутизирует get_weight_history к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_weight_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_weight_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Результат — строка (не сообщение об ошибке unknown_tool)
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_get_vaccinations_dispatches(self) -> None:
        """handle_tool_call маршрутизирует get_vaccinations к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_vaccinations",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_vaccinations",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_get_medications_dispatches(self) -> None:
        """handle_tool_call маршрутизирует get_medications к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_get_notes_dispatches(self) -> None:
        """handle_tool_call маршрутизирует get_notes к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_notes",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_notes",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_get_feeding_history_dispatches(self) -> None:
        """handle_tool_call маршрутизирует get_feeding_history к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_get_current_diet_dispatches(self) -> None:
        """handle_tool_call маршрутизирует get_current_diet к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_current_diet",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_current_diet",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Поведение обработчиков — get_weight_history
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetWeightHistory:
    """Проверки обработчика get_weight_history."""

    async def test_calls_resolve_pet(self) -> None:
        """Обработчик вызывает _resolve_pet для поиска питомца."""
        session = _make_mock_session()
        resolve_mock = AsyncMock(return_value=_PET_STUB)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=resolve_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_weight_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_weight_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        resolve_mock.assert_called_once()
        call_args = resolve_mock.call_args
        found_name = call_args[1].get(
            "pet_name",
            call_args[0][2] if len(call_args[0]) > 2 else None,
        )
        assert found_name == "Луна" or "Луна" in str(call_args)

    async def test_calls_service_get_weight_history(self) -> None:
        """Обработчик вызывает health_service.get_weight_history."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_weight_history",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_weight_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        service_mock.assert_called_once()

    async def test_returns_formatted_text_with_records(self) -> None:
        """При наличии записей возвращает форматированный текст с данными."""
        session = _make_mock_session()
        weight_records = [
            SimpleNamespace(
                weight_kg=Decimal("28.50"),
                measured_at=datetime.date(2026, 3, 15),
            ),
            SimpleNamespace(
                weight_kg=Decimal("28.20"),
                measured_at=datetime.date(2026, 3, 1),
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_weight_history",
                new=AsyncMock(return_value=weight_records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_weight_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Результат содержит данные о весе
        assert "28.5" in result or "28.50" in result
        assert "28.2" in result or "28.20" in result

    async def test_returns_no_records_message_when_empty(self) -> None:
        """При пустом списке записей возвращает сообщение 'нет записей'."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_weight_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_weight_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Результат — непустая строка (сообщение «нет записей»)
        assert isinstance(result, str)
        assert len(result) > 0
        # Не содержит трейсбэков или ошибок
        assert "Traceback" not in result

    async def test_passes_limit_to_service(self) -> None:
        """Обработчик передаёт параметр limit в сервисный метод."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_weight_history",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_weight_history",
                arguments={"pet_name": "Луна", "limit": 5},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Проверяем, что limit передан в вызов сервиса
        call_kwargs = service_mock.call_args
        assert call_kwargs is not None
        # limit может быть передан как позиционный или именованный аргумент
        all_args_str = str(call_kwargs)
        assert "5" in all_args_str or "limit" in all_args_str


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Поведение обработчиков — get_vaccinations
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetVaccinations:
    """Проверки обработчика get_vaccinations."""

    async def test_calls_service_get_vaccinations(self) -> None:
        """Обработчик вызывает health_service.get_vaccinations."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_vaccinations",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_vaccinations",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        service_mock.assert_called_once()

    async def test_returns_formatted_text_with_records(self) -> None:
        """При наличии записей возвращает текст с данными о вакцинации."""
        session = _make_mock_session()
        vaccinations = [
            SimpleNamespace(
                vaccine_name="Nobivac DHPPi",
                date=datetime.date(2026, 1, 15),
                next_date=datetime.date(2027, 1, 15),
                vet_name="Доктор Иванов",
                batch_number="AB123",
                notes=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_vaccinations",
                new=AsyncMock(return_value=vaccinations),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_vaccinations",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "Nobivac DHPPi" in result

    async def test_returns_no_records_message_when_empty(self) -> None:
        """При пустом списке вакцинаций возвращает сообщение 'нет записей'."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_vaccinations",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_vaccinations",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Поведение обработчиков — get_medications
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetMedications:
    """Проверки обработчика get_medications."""

    async def test_calls_service_get_medications(self) -> None:
        """Обработчик вызывает health_service.get_medications."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        service_mock.assert_called_once()

    async def test_passes_active_only_to_service(self) -> None:
        """Обработчик передаёт параметр active_only в сервисный метод."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=service_mock,
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
            )
        call_kwargs = service_mock.call_args
        assert call_kwargs is not None
        all_args_str = str(call_kwargs)
        assert "True" in all_args_str or "active_only" in all_args_str

    async def test_returns_formatted_text_with_records(self) -> None:
        """При наличии лекарств возвращает текст с данными."""
        session = _make_mock_session()
        medications = [
            SimpleNamespace(
                name="Апоквел",
                dosage="16 мг",
                start_date=datetime.date(2026, 3, 1),
                end_date=None,
                is_active=True,
                frequency=None,
                notes=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=medications),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "Апоквел" in result

    async def test_returns_no_records_message_when_empty(self) -> None:
        """При пустом списке лекарств возвращает сообщение 'нет записей'."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Поведение обработчиков — get_notes
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetNotes:
    """Проверки обработчика get_notes."""

    async def test_calls_service_get_notes(self) -> None:
        """Обработчик вызывает health_service.get_notes."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_notes",
                new=service_mock,
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
        service_mock.assert_called_once()

    async def test_returns_formatted_text_with_records(self) -> None:
        """При наличии заметок возвращает текст с содержимым."""
        session = _make_mock_session()
        notes = [
            SimpleNamespace(
                content="Луна сегодня грустная, мало ела",
                created_at=datetime.datetime(2026, 3, 15, 10, 0, 0),
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_notes",
                new=AsyncMock(return_value=notes),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_notes",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "грустная" in result or "мало ела" in result

    async def test_returns_no_records_message_when_empty(self) -> None:
        """При пустом списке заметок возвращает сообщение 'нет записей'."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_notes",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_notes",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_passes_limit_to_service(self) -> None:
        """Обработчик передаёт параметр limit в health_service.get_notes."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_notes",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_notes",
                arguments={"pet_name": "Луна", "limit": 3},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = service_mock.call_args
        assert call_kwargs is not None
        all_args_str = str(call_kwargs)
        assert "3" in all_args_str


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Поведение обработчиков — get_feeding_history
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetFeedingHistory:
    """Проверки обработчика get_feeding_history."""

    async def test_calls_service_get_feeding_entries(self) -> None:
        """Обработчик вызывает nutrition_service.get_feeding_entries."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        service_mock.assert_called_once()

    async def test_returns_formatted_text_with_records(self) -> None:
        """При наличии записей кормления возвращает текст с данными."""
        session = _make_mock_session()
        import zoneinfo

        tz = zoneinfo.ZoneInfo("UTC")
        entries = [
            SimpleNamespace(
                food_description="Сухой корм Royal Canin",
                fed_at=datetime.datetime(2026, 3, 15, 8, 0, 0, tzinfo=tz),
                portion_size=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "Royal Canin" in result

    async def test_returns_no_records_message_when_empty(self) -> None:
        """При пустом списке кормлений возвращает сообщение 'нет записей'."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Поведение обработчиков — get_current_diet
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetCurrentDiet:
    """Проверки обработчика get_current_diet."""

    async def test_calls_service_get_current_diet(self) -> None:
        """Обработчик вызывает nutrition_service.get_current_diet."""
        session = _make_mock_session()
        service_mock = AsyncMock(return_value=None)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_current_diet",
                new=service_mock,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_current_diet",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        service_mock.assert_called_once()

    async def test_returns_formatted_text_with_diet(self) -> None:
        """При наличии текущей диеты возвращает текст с данными."""
        session = _make_mock_session()
        diet = SimpleNamespace(
            food_brand="Royal Canin Medium Adult",
            food_type=None,
            start_date=datetime.date(2026, 2, 1),
            end_date=None,
            notes=None,
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_current_diet",
                new=AsyncMock(return_value=diet),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_current_diet",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "Royal Canin" in result

    async def test_returns_no_diet_message_when_none(self) -> None:
        """При отсутствии текущей диеты возвращает сообщение 'нет диеты'."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_current_diet",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_current_diet",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert len(result) > 0
        # Не должно быть ошибки
        assert "Traceback" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# 4. i18n-сообщения для read-инструментов
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadToolI18nMessages:
    """Проверки наличия i18n-сообщений для read-инструментов."""

    # Ключи сообщений «нет записей» для каждого read-инструмента
    _NO_RECORDS_KEYS: ClassVar[list[str]] = [
        "no_weight_records",
        "no_vaccinations",
        "no_medications",
        "no_notes",
        "no_feeding_entries",
        "no_current_diet",
    ]

    def test_no_weight_records_key_exists_ru(self) -> None:
        """Ключ no_weight_records существует в ru-сообщениях."""
        assert "no_weight_records" in _MESSAGES["ru"]

    def test_no_weight_records_key_exists_en(self) -> None:
        """Ключ no_weight_records существует в en-сообщениях."""
        assert "no_weight_records" in _MESSAGES["en"]

    def test_no_vaccinations_key_exists_ru(self) -> None:
        """Ключ no_vaccinations существует в ru-сообщениях."""
        assert "no_vaccinations" in _MESSAGES["ru"]

    def test_no_vaccinations_key_exists_en(self) -> None:
        """Ключ no_vaccinations существует в en-сообщениях."""
        assert "no_vaccinations" in _MESSAGES["en"]

    def test_no_medications_key_exists_ru(self) -> None:
        """Ключ no_medications существует в ru-сообщениях."""
        assert "no_medications" in _MESSAGES["ru"]

    def test_no_medications_key_exists_en(self) -> None:
        """Ключ no_medications существует в en-сообщениях."""
        assert "no_medications" in _MESSAGES["en"]

    def test_no_notes_key_exists_ru(self) -> None:
        """Ключ no_notes существует в ru-сообщениях."""
        assert "no_notes" in _MESSAGES["ru"]

    def test_no_notes_key_exists_en(self) -> None:
        """Ключ no_notes существует в en-сообщениях."""
        assert "no_notes" in _MESSAGES["en"]

    def test_no_feeding_entries_key_exists_ru(self) -> None:
        """Ключ no_feeding_entries существует в ru-сообщениях."""
        assert "no_feeding_entries" in _MESSAGES["ru"]

    def test_no_feeding_entries_key_exists_en(self) -> None:
        """Ключ no_feeding_entries существует в en-сообщениях."""
        assert "no_feeding_entries" in _MESSAGES["en"]

    def test_no_current_diet_key_exists_ru(self) -> None:
        """Ключ no_current_diet существует в ru-сообщениях."""
        assert "no_current_diet" in _MESSAGES["ru"]

    def test_no_current_diet_key_exists_en(self) -> None:
        """Ключ no_current_diet существует в en-сообщениях."""
        assert "no_current_diet" in _MESSAGES["en"]

    def test_all_no_records_keys_have_both_languages(self) -> None:
        """Все ключи «нет записей» присутствуют в обоих языках."""
        for key in self._NO_RECORDS_KEYS:
            assert key in _MESSAGES["ru"], f"Ключ {key} отсутствует в ru"
            assert key in _MESSAGES["en"], f"Ключ {key} отсутствует в en"

    def test_get_message_returns_ru_no_records(self) -> None:
        """get_message возвращает непустую строку для ключей «нет записей» (ru)."""
        for key in self._NO_RECORDS_KEYS:
            result = get_message(key, language="ru")
            assert isinstance(result, str), f"Ключ {key} не возвращает строку"
            assert result != key, f"Ключ {key} не найден в шаблонах (вернул сам себя)"
            assert len(result) > 0, f"Ключ {key} возвращает пустую строку"

    def test_get_message_returns_en_no_records(self) -> None:
        """get_message возвращает непустую строку для ключей «нет записей» (en)."""
        for key in self._NO_RECORDS_KEYS:
            result = get_message(key, language="en")
            assert isinstance(result, str), f"Ключ {key} не возвращает строку"
            assert result != key, f"Ключ {key} не найден в шаблонах (вернул сам себя)"
            assert len(result) > 0, f"Ключ {key} возвращает пустую строку"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Сервисный метод get_weight_history с параметром limit
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetWeightHistoryServiceWithLimit:
    """Проверки сервисного метода get_weight_history с параметром limit.

    Тесты проверяют, что сигнатура get_weight_history принимает limit
    и возвращает ограниченное количество записей.
    Используют реальную БД (db_session из conftest.py).
    """

    async def test_get_weight_history_accepts_limit_parameter(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_weight_history принимает параметр limit."""
        from backend.app.db.models.pet import Pet
        from backend.app.db.models.workspace import Workspace
        from backend.app.services.health_service import (
            add_weight,
            get_weight_history,
        )

        # Создаём workspace и питомца
        workspace = Workspace(
            telegram_chat_id=-1001234567890,
            title="Test Weight History Workspace",
        )
        db_session.add(workspace)
        await db_session.flush()

        pet = Pet(
            workspace_id=workspace.id,
            name="Луна",
            species="dog",
        )
        db_session.add(pet)
        await db_session.flush()

        # Добавляем 5 записей о весе
        for i in range(5):
            await add_weight(
                session=db_session,
                pet_id=pet.id,
                weight_kg=Decimal(f"2{i}.00"),
                measured_at=datetime.date(2026, 3, 10 + i),
                recorded_by=_USER_ID,
            )

        # Запрашиваем с limit=3
        records = await get_weight_history(
            session=db_session,
            pet_id=pet.id,
            limit=3,
        )
        assert len(records) == 3

    async def test_get_weight_history_default_limit(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_weight_history без limit возвращает записи с limit по умолчанию (10)."""
        from backend.app.db.models.pet import Pet
        from backend.app.db.models.workspace import Workspace
        from backend.app.services.health_service import (
            add_weight,
            get_weight_history,
        )

        # Создаём workspace и питомца
        workspace = Workspace(
            telegram_chat_id=-1001234567891,
            title="Test Default Limit Workspace",
        )
        db_session.add(workspace)
        await db_session.flush()

        pet = Pet(
            workspace_id=workspace.id,
            name="Бобик",
            species="dog",
        )
        db_session.add(pet)
        await db_session.flush()

        # Добавляем 15 записей о весе
        for i in range(15):
            await add_weight(
                session=db_session,
                pet_id=pet.id,
                weight_kg=Decimal(f"2{i % 10}.00"),
                measured_at=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
                recorded_by=_USER_ID,
            )

        # Запрашиваем без limit — должен вернуть не более 10
        records = await get_weight_history(
            session=db_session,
            pet_id=pet.id,
        )
        assert len(records) == 10

    async def test_get_weight_history_sorted_desc(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_weight_history возвращает записи от новых к старым."""
        from backend.app.db.models.pet import Pet
        from backend.app.db.models.workspace import Workspace
        from backend.app.services.health_service import (
            add_weight,
            get_weight_history,
        )

        workspace = Workspace(
            telegram_chat_id=-1001234567892,
            title="Test Sort Workspace",
        )
        db_session.add(workspace)
        await db_session.flush()

        pet = Pet(
            workspace_id=workspace.id,
            name="Рекс",
            species="dog",
        )
        db_session.add(pet)
        await db_session.flush()

        # Добавляем записи в хронологическом порядке
        dates = [
            datetime.date(2026, 1, 1),
            datetime.date(2026, 2, 1),
            datetime.date(2026, 3, 1),
        ]
        for d in dates:
            await add_weight(
                session=db_session,
                pet_id=pet.id,
                weight_kg=Decimal("25.00"),
                measured_at=d,
                recorded_by=_USER_ID,
            )

        records = await get_weight_history(
            session=db_session,
            pet_id=pet.id,
            limit=10,
        )
        # Первая запись — самая новая
        assert records[0].measured_at == datetime.date(2026, 3, 1)
        assert records[-1].measured_at == datetime.date(2026, 1, 1)
