"""
Тесты v4: Medication is_active в доменном слое,
Tool schema enum-валидация.

Покрывает:
1. Medication — is_active=False при end_date в прошлом (доменный слой),
   группировка expired-препаратов в завершённые, консистентность active_only
2. Tool schema — наличие enum в add_measurement, add_vet_visit, add_mood_log;
   совпадение enum с whitelist-наборами в сервисах
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.agent.tools import get_tool_definitions
from backend.app.services import health_service
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
# Блок 1: Document — каноничные типы
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# Блок 1: Medication — инвариант is_active в доменном слое
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicationIsActiveInDomainLayer:
    """is_active должен вычисляться в сервисном слое (health_service),
    а не только в handler."""

    async def test_add_medication_service_sets_inactive_when_end_date_past(
        self,
    ) -> None:
        """Прямой вызов health_service.add_medication с end_date
        в прошлом → запись создаётся с is_active=False.

        Ожидается FAIL: сейчас логика is_active живёт в handler,
        а не в сервисе."""
        past_end = datetime.date(2026, 3, 10)  # до _TODAY (2026-03-17)
        mock_session = AsyncMock(spec=AsyncSession)
        # Перехватываем kwargs, переданные в конструктор Medication
        captured_kwargs: dict = {}

        def _capture_medication(**kwargs: object) -> SimpleNamespace:
            captured_kwargs.update(kwargs)
            return SimpleNamespace(
                id=1,
                pet_id=1,
                name="Антибиотик",
                dosage="500мг",
                start_date=datetime.date(2026, 3, 1),
                end_date=past_end,
                is_active=kwargs.get("is_active", True),
                recorded_by=_USER_ID,
            )

        with (
            patch(
                "backend.app.services.health_service._require_recorded_by_in_kwargs",
                return_value=_USER_ID,
            ),
            patch(
                "backend.app.services.health_service._log_health_change",
                new=AsyncMock(),
            ),
            patch(
                "backend.app.services.health_service.Medication",
                side_effect=_capture_medication,
            ),
        ):
            result = await health_service.add_medication(
                session=mock_session,
                pet_id=1,
                name="Антибиотик",
                start_date=datetime.date(2026, 3, 1),
                dosage="500мг",
                end_date=past_end,
                recorded_by=_USER_ID,
            )

        # Сервис должен самостоятельно выставить is_active=False,
        # когда end_date < текущая дата
        assert result.is_active is False, (
            "health_service.add_medication должен выставлять "
            "is_active=False, когда end_date в прошлом. "
            "Сейчас эта логика есть только в handler, а должна "
            "быть в доменном слое (сервисе)."
        )

    async def test_get_medications_grouped_expired_in_completed(self) -> None:
        """Препарат с is_active=True, но end_date в прошлом,
        должен попасть в завершённые при grouped-read."""
        session = _make_mock_session()
        # Препарат формально is_active=True, но end_date истёк
        expired_med = SimpleNamespace(
            name="Просроченный",
            dosage="100мг",
            frequency="1р/день",
            start_date=datetime.date(2026, 2, 1),
            end_date=datetime.date(2026, 3, 10),  # до _TODAY
            is_active=True,
            notes=None,
        )
        active_med = SimpleNamespace(
            name="Текущий",
            dosage="200мг",
            frequency="2р/день",
            start_date=datetime.date(2026, 3, 1),
            end_date=None,
            is_active=True,
            notes=None,
        )

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=[active_med, expired_med]),
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
        ):
            result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={
                    "pet_name": "Луна",
                    "active_only": False,
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        # Оба препарата должны быть в ответе
        assert "Просроченный" in result
        assert "Текущий" in result

        # Разбиваем на строки и ищем позиции препаратов относительно
        # секции-заголовка завершённых
        lines = result.strip().splitlines()
        # «Просроченный» (is_active=True, но end_date в прошлом)
        # не должен быть в секции активных — он по факту истёк
        expired_line_idx = None
        active_line_idx = None
        for i, line in enumerate(lines):
            if "Просроченный" in line:
                expired_line_idx = i
            if "Текущий" in line:
                active_line_idx = i

        assert expired_line_idx is not None
        assert active_line_idx is not None
        # «Текущий» должен быть раньше «Просроченного» (сначала активные,
        # потом завершённые)
        assert active_line_idx < expired_line_idx, (
            "Препарат с истёкшим end_date должен быть в секции "
            "завершённых (ниже активных), даже если is_active=True. "
            f"active_line={active_line_idx}, expired_line={expired_line_idx}. "
            f"Ответ:\n{result}"
        )

    async def test_get_medications_active_only_and_all_consistent(self) -> None:
        """active_only=True и обычный get_medications не противоречат:
        всё, что в active_only=True, должно быть подмножеством полного списка."""
        mock_active = AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="Витамин D",
                    dosage="1 таб",
                    frequency="1р/день",
                    start_date=datetime.date(2026, 3, 1),
                    end_date=None,
                    is_active=True,
                    notes=None,
                ),
            ],
        )
        mock_all = AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="Витамин D",
                    dosage="1 таб",
                    frequency="1р/день",
                    start_date=datetime.date(2026, 3, 1),
                    end_date=None,
                    is_active=True,
                    notes=None,
                ),
                SimpleNamespace(
                    name="Антибиотик",
                    dosage="500мг",
                    frequency="2р/день",
                    start_date=datetime.date(2026, 2, 1),
                    end_date=datetime.date(2026, 2, 14),
                    is_active=False,
                    notes=None,
                ),
            ],
        )

        session = _make_mock_session()

        # Первый вызов — active_only=True
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=mock_active,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
        ):
            active_result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна", "active_only": True},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        # Второй вызов — все лекарства
        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=mock_all,
            ),
            patch(
                "backend.app.agent.tool_handlers._resolve_workspace_timezone",
                new=AsyncMock(return_value="Europe/Moscow"),
            ),
        ):
            all_result = await handle_tool_call(
                session=session,
                tool_name="get_medications",
                arguments={"pet_name": "Луна", "active_only": False},
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        # Витамин D должен быть в обоих результатах
        assert "Витамин D" in active_result
        assert "Витамин D" in all_result
        # Антибиотик — только в полном списке
        assert "Антибиотик" not in active_result
        assert "Антибиотик" in all_result


# ═══════════════════════════════════════════════════════════════════════════════
# Блок 3: Tool schema — enum в JSON-схемах
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolSchemaEnums:
    """Проверяем наличие enum в tool definitions для типизированных полей."""

    def test_measurement_type_has_enum(self) -> None:
        """add_measurement tool definition содержит
        "enum": ["temperature", "pulse", "respiration"]
        для поля measurement_type."""
        tool = _get_tool_by_name("add_measurement")
        assert tool is not None, "Инструмент add_measurement не найден"
        props = tool["parameters"]["properties"]
        mt_prop = props.get("measurement_type", {})
        assert "enum" in mt_prop, (
            "Поле measurement_type в add_measurement должно содержать enum. "
            f"Текущее определение: {mt_prop!r}"
        )
        assert set(mt_prop["enum"]) == {"temperature", "pulse", "respiration"}, (
            "enum measurement_type должен содержать "
            "['temperature', 'pulse', 'respiration']. "
            f"Текущий enum: {mt_prop['enum']!r}"
        )

    def test_vet_visit_status_has_enum(self) -> None:
        """add_vet_visit tool definition содержит
        "enum": ["planned", "completed"] для поля status."""
        tool = _get_tool_by_name("add_vet_visit")
        assert tool is not None, "Инструмент add_vet_visit не найден"
        props = tool["parameters"]["properties"]
        status_prop = props.get("status", {})
        assert "enum" in status_prop, (
            "Поле status в add_vet_visit должно содержать enum. "
            f"Текущее определение: {status_prop!r}"
        )
        assert set(status_prop["enum"]) == {"planned", "completed"}, (
            "enum status должен содержать ['planned', 'completed']. "
            f"Текущий enum: {status_prop['enum']!r}"
        )

    def test_mood_has_enum(self) -> None:
        """add_mood_log tool definition содержит enum для поля mood."""
        tool = _get_tool_by_name("add_mood_log")
        assert tool is not None, "Инструмент add_mood_log не найден"
        props = tool["parameters"]["properties"]
        mood_prop = props.get("mood", {})
        assert "enum" in mood_prop, (
            "Поле mood в add_mood_log должно содержать enum. "
            f"Текущее определение: {mood_prop!r}"
        )
        assert set(mood_prop["enum"]) == {"excellent", "good", "normal", "poor"}, (
            "enum mood должен содержать "
            "['excellent', 'good', 'normal', 'poor']. "
            f"Текущий enum: {mood_prop['enum']!r}"
        )

    def test_appetite_has_enum(self) -> None:
        """add_mood_log tool definition содержит enum для поля appetite."""
        tool = _get_tool_by_name("add_mood_log")
        assert tool is not None, "Инструмент add_mood_log не найден"
        props = tool["parameters"]["properties"]
        appetite_prop = props.get("appetite", {})
        assert "enum" in appetite_prop, (
            "Поле appetite в add_mood_log должно содержать enum. "
            f"Текущее определение: {appetite_prop!r}"
        )
        assert set(appetite_prop["enum"]) == {"good", "reduced", "none"}, (
            "enum appetite должен содержать ['good', 'reduced', 'none']. "
            f"Текущий enum: {appetite_prop['enum']!r}"
        )

    def test_tool_enums_match_service_whitelists(self) -> None:
        """Все enum в tool definitions совпадают с наборами
        валидных значений в health_service и document_service."""
        # --- measurement_type ---
        tool_measurement = _get_tool_by_name("add_measurement")
        assert tool_measurement is not None
        mt_prop = tool_measurement["parameters"]["properties"]["measurement_type"]
        assert "enum" in mt_prop, (
            "add_measurement.measurement_type должен содержать enum"
        )
        assert set(mt_prop["enum"]) == health_service._VALID_MEASUREMENT_TYPES, (
            f"enum measurement_type {set(mt_prop['enum'])} "
            f"не совпадает с _VALID_MEASUREMENT_TYPES "
            f"{health_service._VALID_MEASUREMENT_TYPES}"
        )

        # --- vet_visit status ---
        tool_vet = _get_tool_by_name("add_vet_visit")
        assert tool_vet is not None
        status_prop = tool_vet["parameters"]["properties"]["status"]
        assert "enum" in status_prop, "add_vet_visit.status должен содержать enum"
        assert set(status_prop["enum"]) == health_service._VALID_VET_VISIT_STATUSES, (
            f"enum status {set(status_prop['enum'])} "
            f"не совпадает с _VALID_VET_VISIT_STATUSES "
            f"{health_service._VALID_VET_VISIT_STATUSES}"
        )

        # --- mood ---
        tool_mood = _get_tool_by_name("add_mood_log")
        assert tool_mood is not None
        mood_prop = tool_mood["parameters"]["properties"]["mood"]
        assert "enum" in mood_prop, "add_mood_log.mood должен содержать enum"
        assert set(mood_prop["enum"]) == health_service._VALID_MOODS, (
            f"enum mood {set(mood_prop['enum'])} "
            f"не совпадает с _VALID_MOODS {health_service._VALID_MOODS}"
        )

        # --- appetite ---
        appetite_prop = tool_mood["parameters"]["properties"]["appetite"]
        assert "enum" in appetite_prop, "add_mood_log.appetite должен содержать enum"
        assert set(appetite_prop["enum"]) == health_service._VALID_APPETITES, (
            f"enum appetite {set(appetite_prop['enum'])} "
            f"не совпадает с _VALID_APPETITES {health_service._VALID_APPETITES}"
        )
