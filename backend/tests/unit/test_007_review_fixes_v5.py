"""
Тесты v5: Пять исправлений из code review.

Покрывает:
1. update_pet — blood_type и vet_contact убраны из whitelist и tool schema
2. get_feeding_history — ровно 7 календарных дней (days=6, а не days=7)
3. _build_pets_section — локализация (response_language как 4-й аргумент)
4. Canonical measurement units — "C"/"bpm"/"rpm" вместо "°C"/"уд/мин"/"вд/мин"
5. Полнота audit diff — vet_name/batch_number/notes для vaccination,
   frequency/end_date/notes/is_active для medication,
   food_type/end_date/notes для diet, portion_size для feeding
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.agent.tool_handlers import (
    _MEASUREMENT_UNIT_MAP,
    _PET_UPDATE_FIELD_WHITELIST,
    handle_tool_call,
)
from backend.app.agent.tools import get_tool_definitions
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
# Блок 1: update_pet — blood_type и vet_contact убраны
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpdatePetWithoutBloodTypeVetContact:
    """После фикса blood_type и vet_contact НЕ должны присутствовать
    ни в tool schema update_pet, ни в _PET_UPDATE_FIELD_WHITELIST.
    Они остаются только в update_emergency_profile."""

    def test_update_pet_tool_schema_no_blood_type_vet_contact(self) -> None:
        """Tool schema (tools.py) для update_pet НЕ содержит
        blood_type и vet_contact в properties и description."""
        tool = _get_tool_by_name("update_pet")
        assert tool is not None, "Инструмент update_pet не найден"
        props = tool["parameters"]["properties"]
        assert "blood_type" not in props, (
            "Tool schema update_pet не должна содержать blood_type в properties. "
            "blood_type перенесён в update_emergency_profile. "
            f"Текущие properties: {sorted(props.keys())}"
        )
        assert "vet_contact" not in props, (
            "Tool schema update_pet не должна содержать vet_contact в properties. "
            "vet_contact перенесён в update_emergency_profile. "
            f"Текущие properties: {sorted(props.keys())}"
        )
        description = tool["description"]
        assert "blood_type" not in description, (
            "Description update_pet не должен упоминать blood_type. "
            f"Текущее описание: {description!r}"
        )
        assert "vet_contact" not in description, (
            "Description update_pet не должен упоминать vet_contact. "
            f"Текущее описание: {description!r}"
        )

    def test_update_pet_whitelist_no_blood_type_vet_contact(self) -> None:
        """_PET_UPDATE_FIELD_WHITELIST в tool_handlers.py
        НЕ содержит blood_type и vet_contact."""
        assert "blood_type" not in _PET_UPDATE_FIELD_WHITELIST, (
            "_PET_UPDATE_FIELD_WHITELIST не должен содержать blood_type. "
            "blood_type перенесён в _EMERGENCY_UPDATE_FIELD_WHITELIST. "
            f"Текущий whitelist: {sorted(_PET_UPDATE_FIELD_WHITELIST)}"
        )
        assert "vet_contact" not in _PET_UPDATE_FIELD_WHITELIST, (
            "_PET_UPDATE_FIELD_WHITELIST не должен содержать vet_contact. "
            "vet_contact перенесён в _EMERGENCY_UPDATE_FIELD_WHITELIST. "
            f"Текущий whitelist: {sorted(_PET_UPDATE_FIELD_WHITELIST)}"
        )

    async def test_update_pet_handler_rejects_blood_type(self) -> None:
        """Вызов handle_tool_call с blood_type в arguments для update_pet
        возвращает сообщение об ошибке (не raise — handler ловит исключения)."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="update_pet",
                arguments={
                    "pet_name": "Луна",
                    "blood_type": "DEA 1.1+",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        # handle_tool_call ловит ValueError и возвращает error_occurred
        assert (
            "blood_type" in result
            or "ошибка" in result.lower()
            or "error" in result.lower()
        ), (
            "Handler update_pet должен отклонить blood_type. "
            f"Полученный ответ: {result!r}"
        )

    async def test_update_pet_handler_rejects_vet_contact(self) -> None:
        """Вызов handle_tool_call с vet_contact в arguments для update_pet
        возвращает сообщение об ошибке."""
        session = _make_mock_session()
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="update_pet",
                arguments={
                    "pet_name": "Луна",
                    "vet_contact": "+7-999-123-45-67",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        assert (
            "vet_contact" in result
            or "ошибка" in result.lower()
            or "error" in result.lower()
        ), (
            "Handler update_pet должен отклонить vet_contact. "
            f"Полученный ответ: {result!r}"
        )

    async def test_update_pet_handler_accepts_valid_fields(self) -> None:
        """Вызов handle_tool_call с breed, origin_story, chip_number
        успешно обновляет профиль питомца."""
        session = _make_mock_session()
        mock_update = AsyncMock(
            return_value=SimpleNamespace(
                id=1,
                name="Луна",
                species="dog",
                breed="Лабрадор",
                origin_story="Приют",
                chip_number="RU123456789",
            ),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new=mock_update,
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="update_pet",
                arguments={
                    "pet_name": "Луна",
                    "breed": "Лабрадор",
                    "origin_story": "Приют",
                    "chip_number": "RU123456789",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )
        # Ответ должен быть подтверждением обновления, а не ошибкой
        assert "ошибка" not in result.lower(), (
            "Handler update_pet должен успешно принять валидные поля "
            "breed, origin_story, chip_number. "
            f"Полученный ответ: {result!r}"
        )
        assert "error" not in result.lower(), (
            "Handler update_pet должен успешно принять валидные поля "
            "breed, origin_story, chip_number. "
            f"Полученный ответ: {result!r}"
        )
        mock_update.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Блок 2: get_feeding_history — ровно 7 календарных дней
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedingHistorySevenDayWindow:
    """Дефолтный период get_feeding_history — ровно 7 календарных дней
    (today - 6 дней включительно), а не today - 7 дней."""

    async def test_no_dates_uses_seven_calendar_days(self) -> None:
        """Без start_date/end_date: since_date = today - 6 дней.
        since_dt = combine(since_date, time.min, tz).
        7 календарных дней = today, today-1, ..., today-6."""
        session = _make_mock_session()
        mock_get_entries = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=mock_get_entries,
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
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs[1].get("since_dt")
        # Ожидаемая дата: 2026-03-17 - 6 дней = 2026-03-11
        expected_since_date = _TODAY - datetime.timedelta(days=6)
        actual_since_date = since_dt.date() if hasattr(since_dt, "date") else None
        assert actual_since_date == expected_since_date, (
            "Без start_date/end_date дефолтный since_date должен быть "
            f"today - 6 дней = {expected_since_date} "
            f"(7 календарных дней включительно). "
            f"Получено: {actual_since_date}. "
            "Текущий баг: используется days=7 вместо days=6."
        )

    async def test_only_end_date_uses_seven_calendar_days(self) -> None:
        """С end_date = 2026-03-15: since_date = 2026-03-15 - 6 = 2026-03-09.
        7 календарных дней = 15, 14, 13, 12, 11, 10, 9."""
        session = _make_mock_session()
        mock_get_entries = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=mock_get_entries,
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={
                    "pet_name": "Луна",
                    "end_date": "2026-03-15",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        mock_get_entries.assert_called_once()
        call_kwargs = mock_get_entries.call_args
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs[1].get("since_dt")
        # end_date = 2026-03-15 → since_date = 2026-03-15 - 6 = 2026-03-09
        expected_since_date = datetime.date(2026, 3, 9)
        actual_since_date = since_dt.date() if hasattr(since_dt, "date") else None
        assert actual_since_date == expected_since_date, (
            "С end_date=2026-03-15 since_date должен быть "
            f"end_date - 6 дней = {expected_since_date}. "
            f"Получено: {actual_since_date}. "
            "Текущий баг: используется days=7 вместо days=6."
        )

    async def test_explicit_start_date_not_overridden(self) -> None:
        """Если start_date указан явно (2026-03-01), он не должен
        корректироваться — используется как есть."""
        session = _make_mock_session()
        mock_get_entries = AsyncMock(return_value=[])
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.get_feeding_entries",
                new=mock_get_entries,
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="get_feeding_history",
                arguments={
                    "pet_name": "Луна",
                    "start_date": "2026-03-01",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        mock_get_entries.assert_called_once()
        call_kwargs = mock_get_entries.call_args
        since_dt = call_kwargs.kwargs.get("since_dt") or call_kwargs[1].get("since_dt")
        expected_since_date = datetime.date(2026, 3, 1)
        actual_since_date = since_dt.date() if hasattr(since_dt, "date") else None
        assert actual_since_date == expected_since_date, (
            f"Явно указанный start_date={expected_since_date} не должен "
            f"автокорректироваться. Получено: {actual_since_date}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Блок 3: _build_pets_section — локализация
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildPetsSectionLocalization:
    """После фикса _build_pets_section принимает response_language
    как 4-й аргумент и возвращает локализованные строки."""

    async def test_english_no_pets_message(self) -> None:
        """Пустой список питомцев с language='en' → строка на английском
        (не содержит кириллицы)."""
        from backend.app.agent.prompts import _build_pets_section

        session = AsyncMock(spec=AsyncSession)
        result = await _build_pets_section(
            session,
            [],
            _TODAY,
            "en",
        )
        # Проверяем отсутствие кириллицы
        has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in result)
        assert not has_cyrillic, (
            "_build_pets_section([], 'en') не должна содержать кириллицу. "
            f"Текущий результат: {result!r}. "
            "Баг: _build_pets_section не принимает response_language "
            "и всегда возвращает русские строки."
        )

    async def test_english_pet_line_no_russian(self) -> None:
        """Один питомец, язык en → строка содержит 'species:' (или аналог),
        НЕ содержит 'вид:'."""
        from backend.app.agent.prompts import _build_pets_section

        session = AsyncMock(spec=AsyncSession)
        pet = SimpleNamespace(id=1, name="Луна", species="dog")
        with patch(
            "backend.app.agent.prompts.health_service.get_medications",
            new=AsyncMock(return_value=[]),
        ):
            result = await _build_pets_section(
                session,
                [pet],
                _TODAY,
                "en",
            )
        assert "вид:" not in result, (
            "_build_pets_section с language='en' не должна содержать 'вид:'. "
            f"Текущий результат: {result!r}"
        )
        # Строка должна содержать английский аналог описания вида
        assert "species" in result.lower() or "dog" in result.lower(), (
            "_build_pets_section с language='en' должна содержать "
            "английский аналог описания вида ('species' или имя вида). "
            f"Текущий результат: {result!r}"
        )

    async def test_english_medication_line_no_russian(self) -> None:
        """Питомец с лекарством, язык en → строка содержит 'Medication'
        (или аналог), НЕ содержит 'Лекарство:' и 'дозировка:'."""
        from backend.app.agent.prompts import _build_pets_section

        session = AsyncMock(spec=AsyncSession)
        pet = SimpleNamespace(id=1, name="Луна", species="dog")
        med = SimpleNamespace(name="Антибиотик", dosage="500мг")
        with patch(
            "backend.app.agent.prompts.health_service.get_medications",
            new=AsyncMock(return_value=[med]),
        ):
            result = await _build_pets_section(
                session,
                [pet],
                _TODAY,
                "en",
            )
        assert "Лекарство:" not in result, (
            "_build_pets_section с language='en' не должна содержать "
            f"'Лекарство:'. Текущий результат: {result!r}"
        )
        assert "дозировка:" not in result, (
            "_build_pets_section с language='en' не должна содержать "
            f"'дозировка:'. Текущий результат: {result!r}"
        )

    async def test_russian_still_works(self) -> None:
        """Язык ru → содержит 'вид:', 'Лекарство:', 'дозировка:'
        (обратная совместимость)."""
        from backend.app.agent.prompts import _build_pets_section

        session = AsyncMock(spec=AsyncSession)
        pet = SimpleNamespace(id=1, name="Луна", species="dog")
        med = SimpleNamespace(name="Антибиотик", dosage="500мг")
        with patch(
            "backend.app.agent.prompts.health_service.get_medications",
            new=AsyncMock(return_value=[med]),
        ):
            result = await _build_pets_section(
                session,
                [pet],
                _TODAY,
                "ru",
            )
        assert "вид:" in result, (
            "_build_pets_section с language='ru' должна содержать 'вид:'. "
            f"Текущий результат: {result!r}"
        )
        assert "Лекарство:" in result, (
            "_build_pets_section с language='ru' должна содержать 'Лекарство:'. "
            f"Текущий результат: {result!r}"
        )
        assert "дозировка:" in result, (
            "_build_pets_section с language='ru' должна содержать 'дозировка:'. "
            f"Текущий результат: {result!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Блок 4: Canonical measurement units
# ═══════════════════════════════════════════════════════════════════════════════


class TestMeasurementCanonicalUnits:
    """_MEASUREMENT_UNIT_MAP должен содержать каноничные (language-agnostic)
    единицы для хранения в БД. Отображаемые единицы формируются
    при форматировании ответа пользователю через i18n."""

    def test_measurement_unit_map_canonical(self) -> None:
        """_MEASUREMENT_UNIT_MAP содержит значения 'C', 'bpm', 'rpm'
        (не '°C', не 'уд/мин', не 'вд/мин')."""
        assert _MEASUREMENT_UNIT_MAP.get("temperature") == "C", (
            "_MEASUREMENT_UNIT_MAP['temperature'] должен быть 'C' "
            "(каноничная единица для хранения). "
            f"Текущее значение: {_MEASUREMENT_UNIT_MAP.get('temperature')!r}. "
            "Баг: сейчас используется '°C' — локализованная единица."
        )
        assert _MEASUREMENT_UNIT_MAP.get("pulse") == "bpm", (
            "_MEASUREMENT_UNIT_MAP['pulse'] должен быть 'bpm' "
            "(каноничная единица для хранения). "
            f"Текущее значение: {_MEASUREMENT_UNIT_MAP.get('pulse')!r}. "
            "Баг: сейчас используется 'уд/мин' — русская единица."
        )
        assert _MEASUREMENT_UNIT_MAP.get("respiration") == "rpm", (
            "_MEASUREMENT_UNIT_MAP['respiration'] должен быть 'rpm' "
            "(каноничная единица для хранения). "
            f"Текущее значение: {_MEASUREMENT_UNIT_MAP.get('respiration')!r}. "
            "Баг: сейчас используется 'вд/мин' — русская единица."
        )

    async def test_add_measurement_stores_canonical_unit(self) -> None:
        """При записи temperature в сервис передаётся unit='C', не '°C'."""
        session = _make_mock_session()
        mock_add_measurement = AsyncMock(
            return_value=SimpleNamespace(
                id=1,
                measurement_type="temperature",
                value=Decimal("38.5"),
                unit="C",
                measured_at=_TODAY,
            ),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add_measurement,
            ),
        ):
            await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "temperature",
                    "value": 38.5,
                    "measured_at": "2026-03-17",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        mock_add_measurement.assert_called_once()
        call_kwargs = mock_add_measurement.call_args
        actual_unit = call_kwargs.kwargs.get("unit")
        assert actual_unit == "C", (
            "В сервис add_measurement должен передаваться каноничный unit='C'. "
            f"Передано: {actual_unit!r}. "
            "Баг: передаётся '°C' — локализованная единица из старого маппинга."
        )

    async def test_measurement_saved_message_ru_display_unit(self) -> None:
        """Ответ на ru для temperature содержит '°C' (display unit),
        не голый 'C'."""
        session = _make_mock_session()
        mock_add_measurement = AsyncMock(
            return_value=SimpleNamespace(
                id=1,
                measurement_type="temperature",
                value=Decimal("38.5"),
                unit="C",
                measured_at=_TODAY,
            ),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add_measurement,
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "temperature",
                    "value": 38.5,
                    "measured_at": "2026-03-17",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                response_language="ru",
                workspace_today=_TODAY,
            )
        # Ответ должен содержать «°C» — отображаемую единицу температуры
        assert "°C" in result, (
            "Ответ measurement_saved на русском должен содержать '°C' "
            f"(display unit). Получено: {result!r}"
        )

    async def test_measurement_saved_message_en_display_unit(self) -> None:
        """Ответ на en для temperature тоже содержит '°C'."""
        session = _make_mock_session()
        mock_add_measurement = AsyncMock(
            return_value=SimpleNamespace(
                id=1,
                measurement_type="temperature",
                value=Decimal("38.5"),
                unit="C",
                measured_at=_TODAY,
            ),
        )
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.add_measurement",
                new=mock_add_measurement,
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="add_measurement",
                arguments={
                    "pet_name": "Луна",
                    "measurement_type": "temperature",
                    "value": 38.5,
                    "measured_at": "2026-03-17",
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                response_language="en",
                workspace_today=_TODAY,
            )
        assert "°C" in result, (
            "Ответ measurement_saved на английском должен содержать '°C' "
            f"(display unit). Получено: {result!r}"
        )

    async def test_pulse_display_units_differ_by_language(self) -> None:
        """Ответ на ru для pulse содержит 'уд/мин',
        ответ на en содержит 'bpm'."""
        session = _make_mock_session()

        async def _call_add_pulse(language: str) -> str:
            """Вспомогательная функция: вызов add_measurement для pulse."""
            mock_add = AsyncMock(
                return_value=SimpleNamespace(
                    id=1,
                    measurement_type="pulse",
                    value=Decimal("80"),
                    unit="bpm",
                    measured_at=_TODAY,
                ),
            )
            with (
                patch(
                    "backend.app.agent.tool_handlers._resolve_pet",
                    new=AsyncMock(return_value=_PET_STUB),
                ),
                patch(
                    "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                    new=AsyncMock(return_value="Europe/Moscow"),
                ),
                patch(
                    "backend.app.agent.tool_handlers.health_service.add_measurement",
                    new=mock_add,
                ),
            ):
                return await handle_tool_call(
                    session=session,
                    tool_name="add_measurement",
                    arguments={
                        "pet_name": "Луна",
                        "measurement_type": "pulse",
                        "value": 80,
                        "measured_at": "2026-03-17",
                    },
                    user_id=_USER_ID,
                    workspace_id=_WORKSPACE_ID,
                    response_language=language,
                    workspace_today=_TODAY,
                )

        result_ru = await _call_add_pulse("ru")
        result_en = await _call_add_pulse("en")

        assert "уд/мин" in result_ru, (
            f"Ответ на ru для pulse должен содержать 'уд/мин'. Получено: {result_ru!r}"
        )
        assert "bpm" in result_en, (
            f"Ответ на en для pulse должен содержать 'bpm'. Получено: {result_en!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Блок 5: Полнота audit diff
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditDiffCompleteness:
    """Audit diff при создании записей должен содержать ВСЕ переданные поля,
    включая опциональные (vet_name, batch_number, notes, frequency и т.д.)."""

    async def test_add_vaccination_audit_includes_optional_fields(self) -> None:
        """add_vaccination с vet_name, batch_number, notes →
        audit diff содержит все три поля."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.scalar = AsyncMock(return_value=_WORKSPACE_ID)
        captured_diff: dict = {}

        async def _capture_log_health(
            session,
            entity_type,
            entity_id,
            pet_id,
            action,
            actor_id,
            diff_json,
        ):
            captured_diff.update(diff_json)

        def _make_vaccination(**kwargs):
            return SimpleNamespace(
                id=42,
                pet_id=kwargs.get("pet_id", 1),
                vaccine_name=kwargs.get("vaccine_name", ""),
                date=kwargs.get("date"),
                next_date=kwargs.get("next_date"),
                vet_name=kwargs.get("vet_name"),
                batch_number=kwargs.get("batch_number"),
                notes=kwargs.get("notes"),
                recorded_by=kwargs.get("recorded_by"),
            )

        from backend.app.services import health_service

        with (
            patch.object(
                health_service,
                "_require_recorded_by_in_kwargs",
                return_value=_USER_ID,
            ),
            patch.object(
                health_service,
                "_log_health_change",
                new=_capture_log_health,
            ),
            patch.object(
                health_service,
                "Vaccination",
                side_effect=_make_vaccination,
            ),
        ):
            await health_service.add_vaccination(
                session=mock_session,
                pet_id=1,
                vaccine_name="Нобивак",
                date=datetime.date(2026, 3, 17),
                recorded_by=_USER_ID,
                vet_name="Иванов А.А.",
                batch_number="LOT-2026-001",
                notes="Без побочных эффектов",
            )

        assert "vet_name" in captured_diff, (
            "Audit diff add_vaccination должен содержать 'vet_name'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "batch_number" in captured_diff, (
            "Audit diff add_vaccination должен содержать 'batch_number'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "notes" in captured_diff, (
            "Audit diff add_vaccination должен содержать 'notes'. "
            f"Текущий diff: {captured_diff}"
        )

    async def test_add_medication_audit_includes_optional_fields(self) -> None:
        """add_medication с frequency, end_date, notes, last_given_date →
        audit diff содержит frequency, end_date, notes, is_active."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.scalar = AsyncMock(return_value=_WORKSPACE_ID)
        captured_diff: dict = {}

        async def _capture_log_health(
            session,
            entity_type,
            entity_id,
            pet_id,
            action,
            actor_id,
            diff_json,
        ):
            captured_diff.update(diff_json)

        end_date = datetime.date(2026, 4, 15)

        def _make_medication(**kwargs):
            return SimpleNamespace(
                id=42,
                pet_id=kwargs.get("pet_id", 1),
                name=kwargs.get("name", ""),
                start_date=kwargs.get("start_date"),
                end_date=kwargs.get("end_date"),
                dosage=kwargs.get("dosage"),
                frequency=kwargs.get("frequency"),
                notes=kwargs.get("notes"),
                is_active=True,
                recorded_by=kwargs.get("recorded_by"),
            )

        from backend.app.services import health_service

        with (
            patch.object(
                health_service,
                "_require_recorded_by_in_kwargs",
                return_value=_USER_ID,
            ),
            patch.object(
                health_service,
                "_log_health_change",
                new=_capture_log_health,
            ),
            patch.object(
                health_service,
                "Medication",
                side_effect=_make_medication,
            ),
        ):
            await health_service.add_medication(
                session=mock_session,
                pet_id=1,
                name="Антибиотик",
                start_date=datetime.date(2026, 3, 1),
                today=_TODAY,
                dosage="500мг",
                frequency="2 раза в день",
                end_date=end_date,
                notes="Принимать после еды",
                last_given_date=datetime.date(2026, 3, 16),
                recorded_by=_USER_ID,
            )

        assert "frequency" in captured_diff, (
            "Audit diff add_medication должен содержать 'frequency'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "end_date" in captured_diff, (
            "Audit diff add_medication должен содержать 'end_date'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "notes" in captured_diff, (
            "Audit diff add_medication должен содержать 'notes'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "is_active" in captured_diff, (
            "Audit diff add_medication должен содержать 'is_active'. "
            f"Текущий diff: {captured_diff}"
        )

    async def test_add_diet_audit_includes_optional_fields(self) -> None:
        """add_diet_record с food_type, end_date, notes →
        audit diff содержит все три поля."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.scalar = AsyncMock(return_value=_WORKSPACE_ID)
        captured_diff: dict = {}

        async def _capture_log_diet(
            session,
            entity_id,
            action,
            actor_id,
            workspace_id,
            diff_json,
        ):
            captured_diff.update(diff_json)

        from backend.app.services import nutrition_service

        def _make_diet_record(**kwargs):
            return SimpleNamespace(
                id=42,
                pet_id=kwargs.get("pet_id", 1),
                food_brand=kwargs.get("food_brand", ""),
                start_date=kwargs.get("start_date"),
                food_type=kwargs.get("food_type"),
                end_date=kwargs.get("end_date"),
                notes=kwargs.get("notes"),
                recorded_by=kwargs.get("recorded_by"),
            )

        with (
            patch.object(
                nutrition_service,
                "_require_actor_id",
                return_value=_USER_ID,
            ),
            patch.object(
                nutrition_service,
                "_get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            patch.object(
                nutrition_service,
                "_get_open_diets",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                nutrition_service,
                "_log_diet_change",
                new=_capture_log_diet,
            ),
            patch.object(
                nutrition_service,
                "DietRecord",
                side_effect=_make_diet_record,
            ),
        ):
            await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Royal Canin",
                start_date=datetime.date(2026, 3, 1),
                recorded_by=_USER_ID,
                food_type="dry",
                end_date=datetime.date(2026, 6, 1),
                notes="Для взрослых собак",
            )

        assert "food_type" in captured_diff, (
            "Audit diff add_diet_record должен содержать 'food_type'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "end_date" in captured_diff, (
            "Audit diff add_diet_record должен содержать 'end_date'. "
            f"Текущий diff: {captured_diff}"
        )
        assert "notes" in captured_diff, (
            "Audit diff add_diet_record должен содержать 'notes'. "
            f"Текущий diff: {captured_diff}"
        )

    async def test_add_feeding_audit_includes_portion_size(self) -> None:
        """add_feeding_entry с portion_size →
        audit diff содержит portion_size."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.scalar = AsyncMock(return_value=_WORKSPACE_ID)
        captured_diff: dict = {}

        async def _capture_log_feeding(
            session,
            entity_id,
            action,
            actor_id,
            workspace_id,
            diff_json,
        ):
            captured_diff.update(diff_json)

        from backend.app.services import nutrition_service

        fed_at = datetime.datetime(
            2026,
            3,
            17,
            12,
            30,
            0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=3)),
        )

        def _make_feeding_entry(**kwargs):
            return SimpleNamespace(
                id=42,
                pet_id=kwargs.get("pet_id", 1),
                fed_at=kwargs.get("fed_at"),
                food_description=kwargs.get("food_description", ""),
                portion_size=kwargs.get("portion_size"),
                recorded_by=kwargs.get("recorded_by"),
            )

        with (
            patch.object(
                nutrition_service,
                "_require_actor_id",
                return_value=_USER_ID,
            ),
            patch.object(
                nutrition_service,
                "_get_workspace_id_for_pet",
                new=AsyncMock(return_value=_WORKSPACE_ID),
            ),
            patch.object(
                nutrition_service,
                "_require_timezone_aware_datetime",
                return_value=fed_at,
            ),
            patch.object(
                nutrition_service,
                "_log_feeding_change",
                new=_capture_log_feeding,
            ),
            patch.object(
                nutrition_service,
                "FeedingEntry",
                side_effect=_make_feeding_entry,
            ),
        ):
            await nutrition_service.add_feeding_entry(
                session=mock_session,
                pet_id=1,
                fed_at=fed_at,
                food_description="Сухой корм",
                recorded_by=_USER_ID,
                portion_size="200г",
            )

        assert "portion_size" in captured_diff, (
            "Audit diff add_feeding_entry должен содержать 'portion_size'. "
            f"Текущий diff: {captured_diff}"
        )
