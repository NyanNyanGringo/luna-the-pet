"""
Тесты для Phase 3 (US2) — расширение полей существующих write-инструментов.

Покрывает:
1. Новые опциональные параметры в определениях 5 инструментов (tools.py)
2. Передачу новых параметров в сервисные методы через обработчики (tool_handlers.py)
3. Парсинг дат через _parse_date_field для date-полей
4. Расширение _PET_UPDATE_FIELD_WHITELIST
5. Обратную совместимость (старые вызовы без новых параметров работают)

Тесты написаны ДО реализации — ожидается, что они упадут при первом запуске.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.agent.tool_handlers import (
    _PET_UPDATE_FIELD_WHITELIST,
    handle_tool_call,
)
from backend.app.agent.tools import get_tool_definitions
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции и фикстуры
# ═══════════════════════════════════════════════════════════════════════════════


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
# 1. Определения инструментов — новые опциональные параметры (tools.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddVaccinationToolExtension:
    """Проверки новых параметров в определении add_vaccination."""

    def test_has_next_date_parameter(self) -> None:
        """add_vaccination содержит опциональный параметр next_date."""
        tool = _get_tool_by_name("add_vaccination")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "next_date" in props
        assert props["next_date"]["type"] == "string"

    def test_has_vet_name_parameter(self) -> None:
        """add_vaccination содержит опциональный параметр vet_name."""
        tool = _get_tool_by_name("add_vaccination")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "vet_name" in props
        assert props["vet_name"]["type"] == "string"

    def test_has_batch_number_parameter(self) -> None:
        """add_vaccination содержит опциональный параметр batch_number."""
        tool = _get_tool_by_name("add_vaccination")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "batch_number" in props
        assert props["batch_number"]["type"] == "string"

    def test_has_notes_parameter(self) -> None:
        """add_vaccination содержит опциональный параметр notes."""
        tool = _get_tool_by_name("add_vaccination")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "notes" in props
        assert props["notes"]["type"] == "string"

    def test_new_params_are_not_required(self) -> None:
        """Новые параметры add_vaccination не входят в required."""
        tool = _get_tool_by_name("add_vaccination")
        assert tool is not None
        required = tool["parameters"]["required"]
        for param in ("next_date", "vet_name", "batch_number", "notes"):
            assert param not in required, (
                f"Параметр {param} не должен быть обязательным"
            )

    def test_original_required_params_preserved(self) -> None:
        """Исходные обязательные параметры add_vaccination сохранены."""
        tool = _get_tool_by_name("add_vaccination")
        assert tool is not None
        required = set(tool["parameters"]["required"])
        assert {"pet_name", "vaccine_name", "date"} <= required


class TestAddMedicationToolExtension:
    """Проверки новых параметров в определении add_medication."""

    def test_has_frequency_parameter(self) -> None:
        """add_medication содержит опциональный параметр frequency."""
        tool = _get_tool_by_name("add_medication")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "frequency" in props
        assert props["frequency"]["type"] == "string"

    def test_has_end_date_parameter(self) -> None:
        """add_medication содержит опциональный параметр end_date."""
        tool = _get_tool_by_name("add_medication")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "end_date" in props
        assert props["end_date"]["type"] == "string"

    def test_has_last_given_date_parameter(self) -> None:
        """add_medication содержит опциональный параметр last_given_date."""
        tool = _get_tool_by_name("add_medication")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "last_given_date" in props
        assert props["last_given_date"]["type"] == "string"

    def test_has_notes_parameter(self) -> None:
        """add_medication содержит опциональный параметр notes."""
        tool = _get_tool_by_name("add_medication")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "notes" in props
        assert props["notes"]["type"] == "string"

    def test_new_params_are_not_required(self) -> None:
        """Новые параметры add_medication не входят в required."""
        tool = _get_tool_by_name("add_medication")
        assert tool is not None
        required = tool["parameters"]["required"]
        for param in ("frequency", "end_date", "last_given_date", "notes"):
            assert param not in required, (
                f"Параметр {param} не должен быть обязательным"
            )

    def test_original_required_params_preserved(self) -> None:
        """Исходные обязательные параметры add_medication сохранены."""
        tool = _get_tool_by_name("add_medication")
        assert tool is not None
        required = set(tool["parameters"]["required"])
        assert {"pet_name", "name", "start_date"} <= required


class TestAddDietToolExtension:
    """Проверки новых параметров в определении add_diet."""

    def test_has_food_type_parameter(self) -> None:
        """add_diet содержит опциональный параметр food_type."""
        tool = _get_tool_by_name("add_diet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "food_type" in props
        assert props["food_type"]["type"] == "string"

    def test_has_end_date_parameter(self) -> None:
        """add_diet содержит опциональный параметр end_date."""
        tool = _get_tool_by_name("add_diet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "end_date" in props
        assert props["end_date"]["type"] == "string"

    def test_has_notes_parameter(self) -> None:
        """add_diet содержит опциональный параметр notes."""
        tool = _get_tool_by_name("add_diet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "notes" in props
        assert props["notes"]["type"] == "string"

    def test_new_params_are_not_required(self) -> None:
        """Новые параметры add_diet не входят в required."""
        tool = _get_tool_by_name("add_diet")
        assert tool is not None
        required = tool["parameters"]["required"]
        for param in ("food_type", "end_date", "notes"):
            assert param not in required, (
                f"Параметр {param} не должен быть обязательным"
            )

    def test_original_required_params_preserved(self) -> None:
        """Исходные обязательные параметры add_diet сохранены."""
        tool = _get_tool_by_name("add_diet")
        assert tool is not None
        required = set(tool["parameters"]["required"])
        assert {"pet_name", "food_brand", "start_date"} <= required


class TestAddFeedingToolExtension:
    """Проверки нового параметра в определении add_feeding."""

    def test_has_portion_size_parameter(self) -> None:
        """add_feeding содержит опциональный параметр portion_size."""
        tool = _get_tool_by_name("add_feeding")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "portion_size" in props
        assert props["portion_size"]["type"] == "string"

    def test_portion_size_is_not_required(self) -> None:
        """portion_size не входит в required для add_feeding."""
        tool = _get_tool_by_name("add_feeding")
        assert tool is not None
        required = tool["parameters"]["required"]
        assert "portion_size" not in required

    def test_original_required_params_preserved(self) -> None:
        """Исходные обязательные параметры add_feeding сохранены."""
        tool = _get_tool_by_name("add_feeding")
        assert tool is not None
        required = set(tool["parameters"]["required"])
        assert {"pet_name", "food_description", "fed_at"} <= required


class TestUpdatePetToolExtension:
    """Проверки новых параметров в определении update_pet."""

    def test_has_origin_story_parameter(self) -> None:
        """update_pet содержит опциональный параметр origin_story."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "origin_story" in props
        assert props["origin_story"]["type"] == "string"

    def test_no_blood_type_parameter(self) -> None:
        """update_pet НЕ содержит blood_type (перенесён в emergency_profile)."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "blood_type" not in props

    def test_has_chip_number_parameter(self) -> None:
        """update_pet содержит опциональный параметр chip_number."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "chip_number" in props
        assert props["chip_number"]["type"] == "string"

    def test_no_vet_contact_parameter(self) -> None:
        """update_pet НЕ содержит vet_contact (перенесён в emergency_profile)."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "vet_contact" not in props

    def test_new_params_are_not_required(self) -> None:
        """Новые параметры update_pet не входят в required."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None
        required = tool["parameters"]["required"]
        for param in ("origin_story", "chip_number"):
            assert param not in required, (
                f"Параметр {param} не должен быть обязательным"
            )

    def test_description_lists_new_fields(self) -> None:
        """Описание update_pet перечисляет допустимые поля
        (без blood_type и vet_contact — они в emergency_profile)."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None
        description = tool["description"]
        for field in ("origin_story", "chip_number"):
            assert field in description, f"Описание update_pet не содержит поле {field}"
        for removed_field in ("blood_type", "vet_contact"):
            assert removed_field not in description, (
                f"Описание update_pet не должно содержать {removed_field}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _PET_UPDATE_FIELD_WHITELIST (tool_handlers.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPetUpdateFieldWhitelist:
    """Проверки расширения _PET_UPDATE_FIELD_WHITELIST."""

    def test_contains_origin_story(self) -> None:
        """Whitelist содержит origin_story."""
        assert "origin_story" in _PET_UPDATE_FIELD_WHITELIST

    def test_no_blood_type(self) -> None:
        """Whitelist НЕ содержит blood_type (перенесён в emergency_profile)."""
        assert "blood_type" not in _PET_UPDATE_FIELD_WHITELIST

    def test_contains_chip_number(self) -> None:
        """Whitelist содержит chip_number."""
        assert "chip_number" in _PET_UPDATE_FIELD_WHITELIST

    def test_no_vet_contact(self) -> None:
        """Whitelist НЕ содержит vet_contact (перенесён в emergency_profile)."""
        assert "vet_contact" not in _PET_UPDATE_FIELD_WHITELIST

    def test_original_fields_preserved(self) -> None:
        """Исходные поля whitelist сохранены."""
        original = {"breed", "birth_date", "gender", "is_neutered"}
        assert original <= _PET_UPDATE_FIELD_WHITELIST


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Обработчики — передача новых параметров в сервисные методы
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddVaccinationHandlerExtension:
    """Проверки передачи новых параметров в health_service.add_vaccination."""

    async def test_passes_all_new_params(self) -> None:
        """Обработчик передаёт next_date, vet_name, batch_number, notes."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            vaccine_name="Нобивак",
            date=datetime.date(2026, 3, 10),
        )
        mock_add_vaccination = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_vaccination",
                new=mock_add_vaccination,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_vaccination",
                arguments={
                    "pet_name": "Луна",
                    "vaccine_name": "Нобивак",
                    "date": "2026-03-10",
                    "next_date": "2027-03-10",
                    "vet_name": "Доктор Айболит",
                    "batch_number": "AB123",
                    "notes": "Перенесла хорошо",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add_vaccination.assert_called_once()
        call_kwargs = mock_add_vaccination.call_args
        # next_date должна быть распарсена в datetime.date
        assert call_kwargs.kwargs.get("next_date") == datetime.date(2027, 3, 10)
        assert call_kwargs.kwargs.get("vet_name") == "Доктор Айболит"
        assert call_kwargs.kwargs.get("batch_number") == "AB123"
        assert call_kwargs.kwargs.get("notes") == "Перенесла хорошо"

    async def test_backward_compatible_without_new_params(self) -> None:
        """Вызов без новых параметров работает как раньше."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            vaccine_name="Нобивак",
            date=datetime.date(2026, 3, 10),
        )
        mock_add_vaccination = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_vaccination",
                new=mock_add_vaccination,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_vaccination",
                arguments={
                    "pet_name": "Луна",
                    "vaccine_name": "Нобивак",
                    "date": "2026-03-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        # Вызов прошёл без ошибок, вернулась строка-подтверждение
        assert isinstance(result, str)
        mock_add_vaccination.assert_called_once()
        # Новые параметры не переданы
        call_kwargs = mock_add_vaccination.call_args.kwargs
        assert "next_date" not in call_kwargs
        assert "vet_name" not in call_kwargs
        assert "batch_number" not in call_kwargs
        assert "notes" not in call_kwargs

    async def test_next_date_parsed_as_date(self) -> None:
        """next_date парсится через _parse_date_field и передаётся как date."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            vaccine_name="Рабикс",
            date=datetime.date(2026, 1, 15),
        )
        mock_add_vaccination = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_vaccination",
                new=mock_add_vaccination,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_vaccination",
                arguments={
                    "pet_name": "Луна",
                    "vaccine_name": "Рабикс",
                    "date": "2026-01-15",
                    "next_date": "2027-01-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add_vaccination.call_args.kwargs
        next_date = call_kwargs.get("next_date")
        assert isinstance(next_date, datetime.date)
        assert next_date == datetime.date(2027, 1, 15)


class TestAddMedicationHandlerExtension:
    """Проверки передачи новых параметров в health_service.add_medication."""

    async def test_passes_all_new_params(self) -> None:
        """Обработчик передаёт frequency, end_date, last_given_date, notes."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            name="Апоквел",
            start_date=datetime.date(2026, 3, 1),
        )
        mock_add_medication = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medication",
                new=mock_add_medication,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medication",
                arguments={
                    "pet_name": "Луна",
                    "name": "Апоквел",
                    "start_date": "2026-03-01",
                    "dosage": "16 мг",
                    "frequency": "2 раза в день",
                    "end_date": "2026-04-01",
                    "last_given_date": "2026-03-15",
                    "notes": "Принимать с едой",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add_medication.assert_called_once()
        call_kwargs = mock_add_medication.call_args.kwargs
        assert call_kwargs.get("frequency") == "2 раза в день"
        assert call_kwargs.get("end_date") == datetime.date(2026, 4, 1)
        assert call_kwargs.get("last_given_date") == datetime.date(2026, 3, 15)
        assert call_kwargs.get("notes") == "Принимать с едой"

    async def test_backward_compatible_without_new_params(self) -> None:
        """Вызов без новых параметров работает как раньше."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            name="Апоквел",
            start_date=datetime.date(2026, 3, 1),
        )
        mock_add_medication = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medication",
                new=mock_add_medication,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_medication",
                arguments={
                    "pet_name": "Луна",
                    "name": "Апоквел",
                    "start_date": "2026-03-01",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        mock_add_medication.assert_called_once()
        call_kwargs = mock_add_medication.call_args.kwargs
        assert "frequency" not in call_kwargs
        assert "end_date" not in call_kwargs
        assert "last_given_date" not in call_kwargs
        assert "notes" not in call_kwargs

    async def test_end_date_parsed_as_date(self) -> None:
        """end_date парсится через _parse_date_field."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            name="Синулокс",
            start_date=datetime.date(2026, 2, 1),
        )
        mock_add_medication = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medication",
                new=mock_add_medication,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medication",
                arguments={
                    "pet_name": "Луна",
                    "name": "Синулокс",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-14",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add_medication.call_args.kwargs
        assert isinstance(call_kwargs.get("end_date"), datetime.date)
        assert call_kwargs["end_date"] == datetime.date(2026, 2, 14)

    async def test_last_given_date_parsed_as_date(self) -> None:
        """last_given_date парсится через _parse_date_field."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            name="Синулокс",
            start_date=datetime.date(2026, 2, 1),
        )
        mock_add_medication = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_medication",
                new=mock_add_medication,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_medication",
                arguments={
                    "pet_name": "Луна",
                    "name": "Синулокс",
                    "start_date": "2026-02-01",
                    "last_given_date": "2026-02-10",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add_medication.call_args.kwargs
        assert isinstance(call_kwargs.get("last_given_date"), datetime.date)
        assert call_kwargs["last_given_date"] == datetime.date(2026, 2, 10)


class TestAddDietHandlerExtension:
    """Проверки передачи новых параметров в nutrition_service.add_diet_record."""

    async def test_passes_all_new_params(self) -> None:
        """Обработчик передаёт food_type, end_date, notes."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 3, 1),
        )
        mock_add_diet = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_diet_record",
                new=mock_add_diet,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_diet",
                arguments={
                    "pet_name": "Луна",
                    "food_brand": "Royal Canin",
                    "start_date": "2026-03-01",
                    "food_type": "dry",
                    "end_date": "2026-06-01",
                    "notes": "Гипоаллергенный",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add_diet.assert_called_once()
        call_kwargs = mock_add_diet.call_args.kwargs
        assert call_kwargs.get("food_type") == "dry"
        assert call_kwargs.get("end_date") == datetime.date(2026, 6, 1)
        assert call_kwargs.get("notes") == "Гипоаллергенный"

    async def test_backward_compatible_without_new_params(self) -> None:
        """Вызов без новых параметров работает как раньше."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 3, 1),
        )
        mock_add_diet = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_diet_record",
                new=mock_add_diet,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_diet",
                arguments={
                    "pet_name": "Луна",
                    "food_brand": "Royal Canin",
                    "start_date": "2026-03-01",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        mock_add_diet.assert_called_once()
        call_kwargs = mock_add_diet.call_args.kwargs
        assert "food_type" not in call_kwargs
        assert "end_date" not in call_kwargs
        assert "notes" not in call_kwargs

    async def test_end_date_parsed_as_date(self) -> None:
        """end_date парсится через _parse_date_field."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            food_brand="Hills",
            start_date=datetime.date(2026, 1, 1),
        )
        mock_add_diet = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_diet_record",
                new=mock_add_diet,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_diet",
                arguments={
                    "pet_name": "Луна",
                    "food_brand": "Hills",
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-30",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        call_kwargs = mock_add_diet.call_args.kwargs
        assert isinstance(call_kwargs.get("end_date"), datetime.date)
        assert call_kwargs["end_date"] == datetime.date(2026, 6, 30)


class TestAddFeedingHandlerExtension:
    """Проверки передачи portion_size в nutrition_service.add_feeding_entry."""

    async def test_passes_portion_size(self) -> None:
        """Обработчик передаёт portion_size в сервис."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            food_description="Сухой корм",
        )
        mock_add_feeding = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_feeding_entry",
                new=mock_add_feeding,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_feeding",
                arguments={
                    "pet_name": "Луна",
                    "food_description": "Сухой корм",
                    "fed_at": "2026-03-10T08:00:00+03:00",
                    "portion_size": "200г",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_add_feeding.assert_called_once()
        call_kwargs = mock_add_feeding.call_args.kwargs
        assert call_kwargs.get("portion_size") == "200г"

    async def test_backward_compatible_without_portion_size(self) -> None:
        """Вызов без portion_size работает как раньше."""
        session = _make_mock_session()
        mock_record = SimpleNamespace(
            food_description="Сухой корм",
        )
        mock_add_feeding = AsyncMock(return_value=mock_record)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_feeding_entry",
                new=mock_add_feeding,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_feeding",
                arguments={
                    "pet_name": "Луна",
                    "food_description": "Сухой корм",
                    "fed_at": "2026-03-10T08:00:00+03:00",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        assert isinstance(result, str)
        mock_add_feeding.assert_called_once()
        call_kwargs = mock_add_feeding.call_args.kwargs
        assert "portion_size" not in call_kwargs


class TestUpdatePetHandlerExtension:
    """Проверки передачи новых полей через update_pet."""

    async def test_passes_origin_story(self) -> None:
        """update_pet передаёт origin_story в pet_service.update_pet."""
        session = _make_mock_session()
        mock_updated_pet = SimpleNamespace(name="Луна")
        mock_update = AsyncMock(return_value=mock_updated_pet)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new=mock_update,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="update_pet",
                arguments={
                    "pet_name": "Луна",
                    "origin_story": "Подобрали на улице",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs.get("origin_story") == "Подобрали на улице"

    async def test_passes_chip_number(self) -> None:
        """update_pet передаёт chip_number в pet_service.update_pet."""
        session = _make_mock_session()
        mock_updated_pet = SimpleNamespace(name="Луна")
        mock_update = AsyncMock(return_value=mock_updated_pet)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new=mock_update,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="update_pet",
                arguments={
                    "pet_name": "Луна",
                    "chip_number": "643094100123456",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs.get("chip_number") == "643094100123456"

    async def test_passes_multiple_new_fields(self) -> None:
        """update_pet принимает несколько допустимых полей одновременно
        (blood_type и vet_contact перенесены в emergency_profile)."""
        session = _make_mock_session()
        mock_updated_pet = SimpleNamespace(name="Луна")
        mock_update = AsyncMock(return_value=mock_updated_pet)
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new=mock_update,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="UTC"),
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="update_pet",
                arguments={
                    "pet_name": "Луна",
                    "origin_story": "Из приюта",
                    "chip_number": "643094100123456",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
            )
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs.get("origin_story") == "Из приюта"
        assert call_kwargs.get("chip_number") == "643094100123456"
