"""
Тесты для Phase 5 (US3) — инструменты записи и чтения медицинских записей.

Покрывает:
1. Определения 2 новых инструментов в tools.py (add_medical_record, get_medical_records)
2. Обработчики в tool_handlers.py (резолв питомца, парсинг дат, вызов сервиса,
   форматирование ответа, i18n)
3. i18n-сообщения medical_record_saved, no_medical_records (ru/en)

Тесты написаны ДО реализации — ожидается, что они упадут при первом запуске.
"""

from __future__ import annotations

import datetime
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
# 1. Определения инструментов (tools.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddMedicalRecordToolDefinition:
    """Проверки определения инструмента add_medical_record."""

    def test_tool_exists(self) -> None:
        """Инструмент add_medical_record присутствует в списке."""
        assert "add_medical_record" in _get_tool_names()

    def test_type_is_function(self) -> None:
        """add_medical_record имеет type='function'."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        assert tool["type"] == "function"

    def test_has_pet_name_required(self) -> None:
        """add_medical_record требует обязательный параметр pet_name."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        assert "pet_name" in tool["parameters"]["required"]
        assert tool["parameters"]["properties"]["pet_name"]["type"] == "string"

    def test_has_record_type_required(self) -> None:
        """add_medical_record требует обязательный параметр record_type."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        assert "record_type" in tool["parameters"]["required"]
        assert tool["parameters"]["properties"]["record_type"]["type"] == "string"

    def test_has_title_required(self) -> None:
        """add_medical_record требует обязательный параметр title."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        assert "title" in tool["parameters"]["required"]
        assert tool["parameters"]["properties"]["title"]["type"] == "string"

    def test_has_date_required(self) -> None:
        """add_medical_record требует обязательный параметр date."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        assert "date" in tool["parameters"]["required"]
        assert tool["parameters"]["properties"]["date"]["type"] == "string"

    def test_has_description_optional(self) -> None:
        """add_medical_record содержит опциональный параметр description."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "description" in props
        assert props["description"]["type"] == "string"
        assert "description" not in tool["parameters"]["required"]

    def test_has_resolved_date_optional(self) -> None:
        """add_medical_record содержит опциональный параметр resolved_date."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "resolved_date" in props
        assert props["resolved_date"]["type"] == "string"
        assert "resolved_date" not in tool["parameters"]["required"]

    def test_has_vet_name_optional(self) -> None:
        """add_medical_record содержит опциональный параметр vet_name."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "vet_name" in props
        assert props["vet_name"]["type"] == "string"
        assert "vet_name" not in tool["parameters"]["required"]

    def test_required_count(self) -> None:
        """add_medical_record имеет ровно 4 обязательных параметра."""
        tool = _get_tool_by_name("add_medical_record")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {
            "pet_name",
            "record_type",
            "title",
            "date",
        }


class TestGetMedicalRecordsToolDefinition:
    """Проверки определения инструмента get_medical_records."""

    def test_tool_exists(self) -> None:
        """Инструмент get_medical_records присутствует в списке."""
        assert "get_medical_records" in _get_tool_names()

    def test_type_is_function(self) -> None:
        """get_medical_records имеет type='function'."""
        tool = _get_tool_by_name("get_medical_records")
        assert tool is not None
        assert tool["type"] == "function"

    def test_has_pet_name_required(self) -> None:
        """get_medical_records требует обязательный параметр pet_name."""
        tool = _get_tool_by_name("get_medical_records")
        assert tool is not None
        assert "pet_name" in tool["parameters"]["required"]
        assert tool["parameters"]["properties"]["pet_name"]["type"] == "string"

    def test_has_record_type_optional(self) -> None:
        """get_medical_records содержит опциональный параметр record_type."""
        tool = _get_tool_by_name("get_medical_records")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "record_type" in props
        assert props["record_type"]["type"] == "string"
        assert "record_type" not in tool["parameters"]["required"]

    def test_required_count(self) -> None:
        """get_medical_records имеет ровно 1 обязательный параметр."""
        tool = _get_tool_by_name("get_medical_records")
        assert tool is not None
        assert set(tool["parameters"]["required"]) == {"pet_name"}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Обработчик add_medical_record (tool_handlers.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleAddMedicalRecord:
    """Проверки обработчика add_medical_record."""

    async def test_dispatches_correctly(self) -> None:
        """handle_tool_call маршрутизирует add_medical_record к обработчику."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="illness",
            title="Отит",
            date=datetime.date(2026, 3, 10),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=AsyncMock(return_value=mock_record),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "illness",
                    "title": "Отит",
                    "date": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_resolves_pet_and_calls_service(self) -> None:
        """Обработчик резолвит питомца и вызывает health_service.add_medical_record."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="checkup",
            title="Плановый осмотр",
            date=datetime.date(2026, 3, 15),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "checkup",
                    "title": "Плановый осмотр",
                    "date": "2026-03-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args
        assert call_kwargs.kwargs.get("pet_id") == _PET_STUB.id
        assert call_kwargs.kwargs.get("record_type") == "checkup"
        assert call_kwargs.kwargs.get("title") == "Плановый осмотр"
        assert call_kwargs.kwargs.get("date") == datetime.date(2026, 3, 15)
        assert call_kwargs.kwargs.get("recorded_by") == _USER_ID

    async def test_parses_date_field(self) -> None:
        """date парсится через _parse_date_field в datetime.date."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="surgery",
            title="Кастрация",
            date=datetime.date(2026, 1, 20),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "surgery",
                    "title": "Кастрация",
                    "date": "2026-01-20",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert isinstance(call_kwargs["date"], datetime.date)
        assert call_kwargs["date"] == datetime.date(2026, 1, 20)

    async def test_passes_optional_description(self) -> None:
        """Обработчик передаёт опциональный description в сервис."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="illness",
            title="Отит",
            date=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "illness",
                    "title": "Отит",
                    "date": "2026-03-10",
                    "description": "Воспаление среднего уха",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs.get("description") == "Воспаление среднего уха"

    async def test_passes_optional_resolved_date(self) -> None:
        """Обработчик парсит и передаёт resolved_date как datetime.date."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="illness",
            title="Отит",
            date=datetime.date(2026, 3, 10),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "illness",
                    "title": "Отит",
                    "date": "2026-03-10",
                    "resolved_date": "2026-03-20",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert isinstance(call_kwargs.get("resolved_date"), datetime.date)
        assert call_kwargs["resolved_date"] == datetime.date(2026, 3, 20)

    async def test_passes_optional_vet_name(self) -> None:
        """Обработчик передаёт опциональный vet_name в сервис."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="checkup",
            title="Осмотр",
            date=datetime.date(2026, 3, 15),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "checkup",
                    "title": "Осмотр",
                    "date": "2026-03-15",
                    "vet_name": "Доктор Айболит",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs.get("vet_name") == "Доктор Айболит"

    async def test_without_optional_params(self) -> None:
        """Вызов без опциональных параметров работает корректно."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="illness",
            title="Аллергия",
            date=datetime.date(2026, 2, 1),
        )
        mock_add = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=mock_add,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "illness",
                    "title": "Аллергия",
                    "date": "2026-02-01",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args.kwargs
        assert "description" not in call_kwargs
        assert "resolved_date" not in call_kwargs
        assert "vet_name" not in call_kwargs

    async def test_returns_i18n_message(self) -> None:
        """Обработчик возвращает локализованное сообщение medical_record_saved."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            record_type="illness",
            title="Отит",
            date=datetime.date(2026, 3, 10),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medical_record",
                new=AsyncMock(return_value=mock_record),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_medical_record",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "illness",
                    "title": "Отит",
                    "date": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Проверяем, что в ответе содержится заголовок и тип записи
        assert "Отит" in result
        assert "illness" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Обработчик get_medical_records (tool_handlers.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetMedicalRecords:
    """Проверки обработчика get_medical_records."""

    async def test_dispatches_correctly(self) -> None:
        """handle_tool_call маршрутизирует get_medical_records к обработчику."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        assert result != get_message("unknown_tool")

    async def test_returns_no_records_message(self) -> None:
        """При пустом списке возвращает i18n сообщение no_medical_records."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        expected = get_message("no_medical_records", language="ru")
        assert result == expected

    async def test_formats_records_with_bullet(self) -> None:
        """Записи форматируются в формате «bullet» с типом, заголовком и датой."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                record_type="illness",
                title="Отит",
                date=datetime.date(2026, 3, 10),
                description=None,
                vet_name=None,
                resolved_date=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Формат: "• [illness] Отит (2026-03-10)"
        assert "•" in result
        assert "[illness]" in result
        assert "Отит" in result
        assert "2026-03-10" in result

    async def test_formats_record_with_description(self) -> None:
        """Запись с description включает описание в ответе."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                record_type="checkup",
                title="Плановый осмотр",
                date=datetime.date(2026, 3, 15),
                description="Всё в норме",
                vet_name=None,
                resolved_date=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "Всё в норме" in result

    async def test_formats_record_with_vet_name(self) -> None:
        """Запись с vet_name включает имя ветеринара в ответе."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                record_type="surgery",
                title="Операция",
                date=datetime.date(2026, 2, 1),
                description=None,
                vet_name="Доктор Айболит",
                resolved_date=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "Доктор Айболит" in result

    async def test_formats_record_with_resolved_date(self) -> None:
        """Запись с resolved_date включает дату разрешения в ответе."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                record_type="illness",
                title="Отит",
                date=datetime.date(2026, 3, 10),
                description=None,
                vet_name=None,
                resolved_date=datetime.date(2026, 3, 20),
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert "2026-03-20" in result

    async def test_passes_record_type_filter(self) -> None:
        """Обработчик передаёт опциональный record_type в сервис."""
        session = _make_mock_session()
        mock_get = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=mock_get,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={
                    "pet_name": "Луна",
                    "record_type": "illness",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("record_type") == "illness"

    async def test_without_record_type_filter(self) -> None:
        """Вызов без record_type не передаёт фильтр в сервис."""
        session = _make_mock_session()
        mock_get = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=mock_get,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args.kwargs
        # record_type не указан — None по умолчанию
        assert call_kwargs.get("record_type") is None

    async def test_multiple_records_formatting(self) -> None:
        """Несколько записей форматируются каждая на отдельной строке."""
        session = _make_mock_session()
        records = [
            SimpleNamespace(
                record_type="illness",
                title="Отит",
                date=datetime.date(2026, 3, 10),
                description=None,
                vet_name=None,
                resolved_date=None,
            ),
            SimpleNamespace(
                record_type="checkup",
                title="Осмотр",
                date=datetime.date(2026, 2, 15),
                description=None,
                vet_name=None,
                resolved_date=None,
            ),
        ]
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medical_records",
                new=AsyncMock(return_value=records),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medical_records",
                arguments={"pet_name": "Луна"},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert "Отит" in lines[0]
        assert "Осмотр" in lines[1]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. i18n сообщения (i18n.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicalRecordsI18n:
    """Проверки i18n ключей для медицинских записей."""

    def test_medical_record_saved_ru_exists(self) -> None:
        """Ключ medical_record_saved существует в русских сообщениях."""
        assert "medical_record_saved" in _MESSAGES["ru"]

    def test_medical_record_saved_en_exists(self) -> None:
        """Ключ medical_record_saved существует в английских сообщениях."""
        assert "medical_record_saved" in _MESSAGES["en"]

    def test_no_medical_records_ru_exists(self) -> None:
        """Ключ no_medical_records существует в русских сообщениях."""
        assert "no_medical_records" in _MESSAGES["ru"]

    def test_no_medical_records_en_exists(self) -> None:
        """Ключ no_medical_records существует в английских сообщениях."""
        assert "no_medical_records" in _MESSAGES["en"]

    def test_medical_record_saved_ru_format(self) -> None:
        """Русский шаблон medical_record_saved форматируется."""
        result = get_message(
            "medical_record_saved",
            language="ru",
            title="Отит",
            record_type="illness",
            date=datetime.date(2026, 3, 10),
        )
        assert "Отит" in result
        assert "illness" in result
        assert "2026-03-10" in result

    def test_medical_record_saved_en_format(self) -> None:
        """Английский шаблон medical_record_saved форматируется."""
        result = get_message(
            "medical_record_saved",
            language="en",
            title="Otitis",
            record_type="illness",
            date=datetime.date(2026, 3, 10),
        )
        assert "Otitis" in result
        assert "illness" in result
        assert "2026-03-10" in result

    def test_no_medical_records_ru_value(self) -> None:
        """Русское сообщение no_medical_records содержит нужный текст."""
        result = get_message("no_medical_records", language="ru")
        assert "Медицинских записей не найдено" in result

    def test_no_medical_records_en_value(self) -> None:
        """Английское сообщение no_medical_records содержит нужный текст."""
        result = get_message("no_medical_records", language="en")
        assert "No medical records found" in result
