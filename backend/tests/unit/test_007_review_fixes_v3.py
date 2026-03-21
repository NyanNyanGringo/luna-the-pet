"""
Тесты для 4 исправлений по итогам ревью (v3).

Покрывает:
1. Диета — автозакрытие предыдущей с end_date = new_start - 1 день
2. Медзапись — resolved_date >= date
3. get_medications — разделение на активные/завершённые
4. build_system_prompt — передача today в _build_pets_section
"""

from __future__ import annotations

import datetime
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.app.agent.tool_handlers import handle_tool_call
from backend.app.services import (
    health_service,
    nutrition_service,
)
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


# ═══════════════════════════════════════════════════════════════
# 1. Диета — автозакрытие с end_date = new_start_date - 1 день
# ═══════════════════════════════════════════════════════════════


class TestDietAutoCloseEndDate:
    """При создании новой открытой диеты старая закрывается
    с end_date = new_start_date - 1 день (без пересечения)."""

    async def test_diet_switch_closes_old_with_day_before_new_start(
        self,
    ) -> None:
        """Старая диета получает end_date на день раньше
        start_date новой диеты (2026-03-14, а не 2026-03-15)."""
        new_start = datetime.date(2026, 3, 15)
        expected_close = datetime.date(2026, 3, 14)

        open_diet = SimpleNamespace(
            id=10,
            pet_id=1,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 2, 1),
            end_date=None,
            recorded_by=_USER_ID,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_close = AsyncMock()

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
                new=mock_close,
            ),
            patch(
                "backend.app.services.nutrition_service._log_diet_change",
                new=AsyncMock(),
            ),
        ):
            await nutrition_service.add_diet_record(
                session=mock_session,
                pet_id=1,
                food_brand="Hills",
                start_date=new_start,
                recorded_by=_USER_ID,
            )

        # _close_open_diet должна быть вызвана с end_date
        # на день раньше start_date новой диеты
        mock_close.assert_called_once()
        call_kwargs = mock_close.call_args
        actual_end = call_kwargs.kwargs.get("end_date") or call_kwargs[1].get(
            "end_date"
        )
        assert actual_end == expected_close, (
            f"end_date должен быть {expected_close}, а не {actual_end}"
        )

    async def test_get_current_diet_no_overlap_on_switch_day(
        self,
    ) -> None:
        """В день начала новой диеты (2026-03-15)
        старая (end_date=2026-03-14) не возвращается
        как текущая."""
        switch_day = datetime.date(2026, 3, 15)
        old_end = datetime.date(2026, 3, 14)

        old_diet = SimpleNamespace(
            id=10,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 2, 1),
            end_date=old_end,
        )
        new_diet = SimpleNamespace(
            id=20,
            food_brand="Hills",
            start_date=switch_day,
            end_date=None,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        # Моделируем результат запроса с фильтром today
        # get_current_diet использует:
        #   start_date <= today AND
        #   (end_date IS NULL OR end_date >= today)
        # Старая диета: end_date=03-14 < today=03-15 → НЕ проходит
        # Новая диета: end_date IS NULL → проходит
        filtered = [new_diet]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = filtered
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await nutrition_service.get_current_diet(
            session=mock_session,
            pet_id=1,
            today=switch_day,
        )

        # Должна вернуться новая диета, а не старая
        assert result is not None
        assert result.food_brand == "Hills"
        # Старая диета не должна быть результатом
        assert result.food_brand != old_diet.food_brand


# ═══════════════════════════════════════════════════════════════
# 2. Медзапись — resolved_date >= date
# ═══════════════════════════════════════════════════════════════


class TestMedicalRecordResolvedDateValidation:
    """resolved_date не может быть раньше date."""

    async def test_medical_record_resolved_date_equal_to_date_ok(
        self,
    ) -> None:
        """resolved_date == date → запись создаётся без ошибки."""
        record_date = datetime.date(2026, 3, 10)
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.services.health_service._require_recorded_by_in_kwargs",
                return_value=_USER_ID,
            ),
            patch(
                "backend.app.services.health_service._log_health_change",
                new=AsyncMock(),
            ),
        ):
            result = await health_service.add_medical_record(
                session=mock_session,
                pet_id=1,
                record_type="illness",
                title="Отит",
                date=record_date,
                recorded_by=_USER_ID,
                resolved_date=record_date,
            )

        assert result is not None

    async def test_medical_record_resolved_date_after_date_ok(
        self,
    ) -> None:
        """resolved_date > date → запись создаётся без ошибки."""
        record_date = datetime.date(2026, 3, 10)
        resolved = datetime.date(2026, 3, 15)
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.services.health_service._require_recorded_by_in_kwargs",
                return_value=_USER_ID,
            ),
            patch(
                "backend.app.services.health_service._log_health_change",
                new=AsyncMock(),
            ),
        ):
            result = await health_service.add_medical_record(
                session=mock_session,
                pet_id=1,
                record_type="checkup",
                title="Осмотр",
                date=record_date,
                recorded_by=_USER_ID,
                resolved_date=resolved,
            )

        assert result is not None

    async def test_medical_record_resolved_date_before_date_raises(
        self,
    ) -> None:
        """resolved_date < date → ValueError о хронологии."""
        record_date = datetime.date(2026, 3, 15)
        resolved_before = datetime.date(2026, 3, 10)
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.services.health_service._require_recorded_by_in_kwargs",
                return_value=_USER_ID,
            ),
            patch(
                "backend.app.services.health_service._log_health_change",
                new=AsyncMock(),
            ),
            pytest.raises(ValueError, match="resolved_date"),
        ):
            await health_service.add_medical_record(
                session=mock_session,
                pet_id=1,
                record_type="illness",
                title="Отит",
                date=record_date,
                recorded_by=_USER_ID,
                resolved_date=resolved_before,
            )


# ═══════════════════════════════════════════════════════════════
# 3. get_medications — разделение активных/завершённых
# ═══════════════════════════════════════════════════════════════


class TestGetMedicationsGroupedResponse:
    """При active_only=False ответ должен группировать
    активные и завершённые лекарства в отдельные секции."""

    _ACTIVE_MED = SimpleNamespace(
        name="Апоквел",
        dosage="16мг",
        frequency="1р/день",
        start_date=datetime.date(2026, 3, 1),
        end_date=None,
        is_active=True,
    )
    _COMPLETED_MED = SimpleNamespace(
        name="Амоксициллин",
        dosage="250мг",
        frequency="2р/день",
        start_date=datetime.date(2026, 2, 1),
        end_date=datetime.date(2026, 2, 14),
        is_active=False,
    )

    async def test_get_medications_active_only_false_grouped(
        self,
    ) -> None:
        """При active_only=False ответ содержит оба лекарства
        с явным разделением на секции (активные/завершённые)."""
        session = _make_mock_session()
        meds = [self._ACTIVE_MED, self._COMPLETED_MED]

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=meds),
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

        # Оба лекарства должны быть в ответе
        assert "Апоквел" in result
        assert "Амоксициллин" in result

        # Должно быть явное разделение на секции:
        # отдельные строки-заголовки перед группами лекарств,
        # а не просто статус-метка внутри каждого пункта.
        # Ищем строки-заголовки вида «Активные ...» на
        # отдельной строке (не внутри пункта «•»).
        lines = result.strip().splitlines()
        section_headers = [
            ln for ln in lines if not ln.strip().startswith("•") and ln.strip()
        ]
        assert len(section_headers) >= 2, (
            "Ответ должен содержать минимум 2 строки-"
            "заголовка секций (активные + завершённые), "
            "а не плоский список. "
            f"Заголовки: {section_headers!r}. "
            f"Весь ответ:\n{result}"
        )

    async def test_get_medications_active_only_true_only_active(
        self,
    ) -> None:
        """При active_only=True возвращаются только активные."""
        session = _make_mock_session()
        active_only_meds = [self._ACTIVE_MED]

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new=AsyncMock(return_value=_PET_STUB),
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_medications",
                new=AsyncMock(return_value=active_only_meds),
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
                    "active_only": True,
                },
                user_id=_USER_ID,
                workspace_id=_WORKSPACE_ID,
                workspace_today=_TODAY,
            )

        assert "Апоквел" in result
        assert "Амоксициллин" not in result


# ═══════════════════════════════════════════════════════════════
# 4. build_system_prompt — today передаётся в get_medications
# ═══════════════════════════════════════════════════════════════


class TestBuildPetsSectionPassesToday:
    """_build_pets_section должна передавать today
    в get_medications вызов."""

    async def test_build_pets_section_passes_today(self) -> None:
        """_build_pets_section передаёт today=workspace_today
        в health_service.get_medications."""
        mock_get_meds = AsyncMock(return_value=[])
        workspace_today = datetime.date(2026, 3, 17)

        with patch(
            "backend.app.agent.prompts.health_service.get_medications",
            new=mock_get_meds,
        ):
            from backend.app.agent.prompts import (
                _build_pets_section,
            )

            mock_session = AsyncMock(spec=AsyncSession)
            pet = SimpleNamespace(id=1, name="Луна", species="dog")
            await _build_pets_section(mock_session, [pet], workspace_today)

        mock_get_meds.assert_called_once()
        call_kwargs = mock_get_meds.call_args
        # today должен быть передан явно
        actual_today = call_kwargs.kwargs.get("today") if call_kwargs.kwargs else None
        assert actual_today == workspace_today, (
            "_build_pets_section должна передавать today "
            f"в get_medications. Вызов: {call_kwargs}"
        )

    def test_english_prompt_fully_english(self) -> None:
        """_assemble_prompt с response_language='en' не содержит
        русских букв в каркасе промпта (кроме pets_section)."""
        from backend.app.agent.prompts import _assemble_prompt

        # pets_section может содержать русские имена — это ОК
        pets_section = "- Luna (species: dog)"
        result = _assemble_prompt(
            pets_section=pets_section,
            timezone="Europe/Moscow",
            response_language="en",
            workspace_today=_TODAY,
        )

        # Убираем pets_section из проверки
        scaffold = result.replace(pets_section, "")
        cyrillic = re.findall(r"[а-яА-ЯёЁ]+", scaffold)
        assert not cyrillic, (
            "Английский промпт не должен содержать "
            f"русских букв в каркасе. Найдено: {cyrillic}"
        )
