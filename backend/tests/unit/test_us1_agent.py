"""
Тесты AI-агента Phase 3 (US1) проекта Luna the Dog.

Покрывает модули агента:
- T029: prompts.py -- построение system prompt (питомцы, лекарства, таймзона)
- T030: tools.py -- JSON-схемы инструментов агента
- T031: tool_handlers.py -- маршрутизация и выполнение tool calls
- T032: brain.py -- run_agent (OpenAI Responses API, ConversationState)
- T033: whisper.py -- транскрипция голоса через Whisper
- T110: Emergency tools -- инструменты экстренного профиля
- T111: date_utils.py -- нормализация относительных дат с учётом таймзоны
- T112: i18n.py -- локализованные шаблоны сообщений

Все внешние вызовы (OpenAI API, Telegram Bot API) мокируются через unittest.mock.
БД-тесты используют реальную PostgreSQL через testcontainers (фикстура db_session).
Тесты будут "красными" до реализации соответствующих модулей.
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.app.db.models.family import Family, FamilyMember, FamilySettings
from backend.app.db.models.health import Medication
from backend.app.db.models.pet import Pet
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции для создания тестовых данных
# ═══════════════════════════════════════════════════════════════════════════════


async def _create_family_with_settings(
    session: AsyncSession,
    timezone: str = "UTC",
) -> Family:
    """Создаёт семью с настройками (таймзона).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        timezone: IANA-таймзона для FamilySettings

    Возвращает:
        Family: созданная семья
    """
    family = Family()
    session.add(family)
    await session.flush()

    settings = FamilySettings(family_id=family.id, timezone=timezone)
    session.add(settings)
    await session.flush()

    return family


async def _create_member(
    session: AsyncSession,
    family_id: int,
    user_id: int = 100500,
    first_name: str = "Тест",
) -> FamilyMember:
    """Создаёт участника семьи с указанным Telegram user ID.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи
        user_id: Telegram user ID
        first_name: имя участника

    Возвращает:
        FamilyMember: созданный участник
    """
    member = FamilyMember(id=user_id, first_name=first_name, family_id=family_id)
    session.add(member)
    await session.flush()
    return member


async def _create_pet(
    session: AsyncSession,
    family_id: int,
    name: str = "Луна",
    species: str = "dog",
) -> Pet:
    """Создаёт питомца в семье.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи
        name: имя питомца
        species: вид животного

    Возвращает:
        Pet: созданный питомец
    """
    pet = Pet(name=name, species=species, family_id=family_id)
    session.add(pet)
    await session.flush()
    return pet


async def _create_active_medication(
    session: AsyncSession,
    pet_id: int,
    name: str = "Бравекто",
    dosage: str = "1 таблетка",
) -> Medication:
    """Создаёт активное лекарство для питомца.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        pet_id: ID питомца
        name: название препарата
        dosage: дозировка

    Возвращает:
        Medication: созданное лекарство (is_active=True)
    """
    medication = Medication(
        pet_id=pet_id,
        name=name,
        dosage=dosage,
        start_date=datetime.date.today(),
        is_active=True,
    )
    session.add(medication)
    await session.flush()
    return medication


# ═══════════════════════════════════════════════════════════════════════════════
# T029: prompts.py -- System prompt builder
# ═══════════════════════════════════════════════════════════════════════════════


class TestSystemPromptBuilder:
    """Тесты построения system prompt для AI-агента."""

    async def test_contains_pet_names(self, db_session: AsyncSession) -> None:
        """System prompt содержит имена питомцев семьи."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session)
        await _create_pet(db_session, family.id, name="Луна")
        await _create_pet(db_session, family.id, name="Барсик")

        prompt = await build_system_prompt(db_session, family.id)

        assert "Луна" in prompt
        assert "Барсик" in prompt

    async def test_contains_active_medications(self, db_session: AsyncSession) -> None:
        """System prompt содержит активные лекарства питомцев."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session)
        pet = await _create_pet(db_session, family.id, name="Луна")
        await _create_active_medication(db_session, pet.id, name="Бравекто")

        prompt = await build_system_prompt(db_session, family.id)

        assert "Бравекто" in prompt

    async def test_contains_family_timezone(self, db_session: AsyncSession) -> None:
        """System prompt содержит таймзону семьи."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(
            db_session, timezone="Europe/Moscow"
        )

        prompt = await build_system_prompt(db_session, family.id)

        assert "Europe/Moscow" in prompt

    async def test_empty_pets_list(self, db_session: AsyncSession) -> None:
        """System prompt корректно строится при отсутствии питомцев."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session)

        prompt = await build_system_prompt(db_session, family.id)

        # Должна быть непустая строка даже без питомцев
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    async def test_returns_string(self, db_session: AsyncSession) -> None:
        """build_system_prompt всегда возвращает строку."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session)
        await _create_pet(db_session, family.id)

        prompt = await build_system_prompt(db_session, family.id)

        assert isinstance(prompt, str)

    async def test_inactive_medication_excluded(self, db_session: AsyncSession) -> None:
        """System prompt НЕ содержит деактивированные лекарства."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session)
        pet = await _create_pet(db_session, family.id, name="Луна")

        # Создаём неактивное лекарство
        inactive_med = Medication(
            pet_id=pet.id,
            name="Старый препарат",
            start_date=datetime.date.today(),
            is_active=False,
        )
        db_session.add(inactive_med)
        await db_session.flush()

        prompt = await build_system_prompt(db_session, family.id)

        assert "Старый препарат" not in prompt

    async def test_default_timezone_utc(self, db_session: AsyncSession) -> None:
        """При отсутствии явной таймзоны используется UTC."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session, timezone="UTC")

        prompt = await build_system_prompt(db_session, family.id)

        assert "UTC" in prompt

    async def test_accepts_response_language_and_family_today(
        self,
        db_session: AsyncSession,
    ) -> None:
        """build_system_prompt принимает response_language и family_today."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(
            db_session, timezone="Europe/Moscow"
        )

        prompt = await build_system_prompt(
            session=db_session,
            family_id=family.id,
            response_language="ru",
            family_today=datetime.date(2026, 3, 8),
        )

        assert "2026-03-08" in prompt
        assert "Europe/Moscow" in prompt

    async def test_english_response_instruction_when_language_is_en(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Проверяет, что для response_language='en' есть инструкция на английский."""
        from backend.app.agent.prompts import build_system_prompt

        family = await _create_family_with_settings(db_session, timezone="UTC")

        prompt = await build_system_prompt(
            session=db_session,
            family_id=family.id,
            response_language="en",
            family_today=datetime.date(2026, 3, 8),
        )

        assert "english" in prompt.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# T030: tools.py -- Agent tool schemas
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolDefinitions:
    """Тесты JSON-схем инструментов агента."""

    def test_returns_non_empty_list(self) -> None:
        """get_tool_definitions() возвращает непустой список."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()

        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_each_tool_has_required_keys(self) -> None:
        """Каждый инструмент имеет ключи: type, name, description, parameters."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()
        required_keys = {"type", "name", "description", "parameters"}

        for tool in tools:
            assert isinstance(tool, dict), (
                f"Инструмент должен быть словарём, получен {type(tool)}"
            )
            missing = required_keys - tool.keys()
            assert not missing, (
                f"Инструмент '{tool.get('name', '???')}' не содержит ключи: {missing}"
            )

    def test_tool_type_is_function(self) -> None:
        """Все инструменты имеют type='function'."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()

        for tool in tools:
            assert tool["type"] == "function", (
                f"Инструмент '{tool.get('name')}' имеет type='{tool['type']}', "
                f"ожидается 'function'"
            )

    @pytest.mark.parametrize(
        "tool_name",
        [
            "add_weight",
            "add_vaccination",
            "add_medication",
            "add_note",
            "add_diet",
            "add_feeding",
            "get_pet_profile",
            "update_pet",
            "create_pet",
            "update_emergency_profile",
        ],
    )
    def test_required_tools_present(self, tool_name: str) -> None:
        """Основные инструменты присутствуют в списке определений."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = {tool["name"] for tool in tools}

        assert tool_name in tool_names, (
            f"Инструмент '{tool_name}' отсутствует в определениях. "
            f"Доступные: {sorted(tool_names)}"
        )

    def test_parameters_have_json_schema_structure(self) -> None:
        """Parameters каждого инструмента содержат валидную JSON Schema структуру."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()

        for tool in tools:
            params = tool["parameters"]
            assert isinstance(params, dict), (
                f"Parameters инструмента '{tool['name']}' должны быть словарём"
            )
            assert "type" in params, (
                f"Parameters инструмента '{tool['name']}' не содержат 'type'"
            )
            assert "properties" in params, (
                f"Parameters инструмента '{tool['name']}' не содержат 'properties'"
            )
            assert "required" in params, (
                f"Parameters инструмента '{tool['name']}' не содержат 'required'"
            )

    def test_tool_names_are_unique(self) -> None:
        """Имена инструментов уникальны."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()
        names = [tool["name"] for tool in tools]

        assert len(names) == len(set(names)), (
            f"Дублирующиеся имена инструментов: "
            f"{[n for n in names if names.count(n) > 1]}"
        )

    def test_tool_descriptions_are_non_empty(self) -> None:
        """Описание каждого инструмента непустое."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()

        for tool in tools:
            assert tool["description"].strip(), (
                f"Инструмент '{tool['name']}' имеет пустое описание"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# T031: tool_handlers.py -- Tool call executor
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolHandlers:
    """Тесты маршрутизации и выполнения вызовов инструментов."""

    async def test_add_weight_calls_health_service(self) -> None:
        """handle_tool_call('add_weight', ...) вызывает health_service.add_weight."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_weight_record = MagicMock()
        mock_weight_record.weight_kg = Decimal("12.50")
        mock_weight_record.measured_at = datetime.date(2026, 3, 8)

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.health_service.add_weight",
            new_callable=AsyncMock,
            return_value=mock_weight_record,
        ) as mock_add_weight:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="add_weight",
                arguments={
                    "pet_name": "Луна",
                    "weight_kg": 12.5,
                    "measured_at": "2026-03-08",
                },
                user_id=100500,
                family_id=1,
            )

            mock_add_weight.assert_awaited_once()

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_add_note_calls_health_service(self) -> None:
        """handle_tool_call('add_note', ...) вызывает health_service.add_note."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_note = MagicMock()
        mock_note.content = "Луна была активной на прогулке"

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.health_service.add_note",
            new_callable=AsyncMock,
            return_value=mock_note,
        ) as mock_add_note:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="add_note",
                arguments={
                    "pet_name": "Луна",
                    "content": "Луна была активной на прогулке",
                },
                user_id=100500,
                family_id=1,
            )

            mock_add_note.assert_awaited_once()

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_get_pet_profile_calls_pet_service(self) -> None:
        """Проверяет вызов pet_service.get_pet_by_name для get_pet_profile."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_pet = MagicMock()
        mock_pet.name = "Луна"
        mock_pet.species = "dog"
        mock_pet.breed = "Самоед"

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.pet_service.get_pet_by_name",
            new_callable=AsyncMock,
            return_value=mock_pet,
        ) as mock_get_pet:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="get_pet_profile",
                arguments={"pet_name": "Луна"},
                user_id=100500,
                family_id=1,
            )

            mock_get_pet.assert_awaited_once()

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_unknown_tool_returns_error_string(self) -> None:
        """Неизвестный tool_name возвращает строку с ошибкой, не бросает исключение."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_session = AsyncMock(spec=AsyncSession)

        result = await handle_tool_call(
            session=mock_session,
            tool_name="nonexistent_tool_xyz",
            arguments={},
            user_id=100500,
            family_id=1,
        )

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_unknown_tool_uses_i18n_with_english_language(self) -> None:
        """Неизвестный tool_name локализуется через i18n для response_language='en'."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.get_message",
            return_value="Unknown command. Please try again.",
            create=True,
        ) as mock_get_message:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="nonexistent_tool_xyz",
                arguments={},
                user_id=100500,
                family_id=1,
                response_language="en",
            )

        mock_get_message.assert_called_once()
        assert result == "Unknown command. Please try again."

    async def test_unknown_tool_fallbacks_to_russian_for_unsupported_language(
        self,
    ) -> None:
        """Неизвестный tool_name использует fallback ru при неподдерживаемом языке."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.get_message",
            return_value="Неизвестная команда. Попробуйте ещё раз.",
            create=True,
        ) as mock_get_message:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="nonexistent_tool_xyz",
                arguments={},
                user_id=100500,
                family_id=1,
                response_language="de",
            )

        language_argument = mock_get_message.call_args.kwargs.get("language")
        assert language_argument == "ru"
        assert result == "Неизвестная команда. Попробуйте ещё раз."

    async def test_add_vaccination_calls_health_service(self) -> None:
        """Проверяет вызов health_service.add_vaccination для add_vaccination."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_vaccination = MagicMock()
        mock_vaccination.vaccine_name = "Нобивак DHPPi"
        mock_vaccination.date = datetime.date(2026, 3, 8)

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.health_service.add_vaccination",
            new_callable=AsyncMock,
            return_value=mock_vaccination,
        ) as mock_add_vaccination:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="add_vaccination",
                arguments={
                    "pet_name": "Луна",
                    "vaccine_name": "Нобивак DHPPi",
                    "date": "2026-03-08",
                },
                user_id=100500,
                family_id=1,
            )

            mock_add_vaccination.assert_awaited_once()

        assert isinstance(result, str)

    async def test_add_medication_calls_health_service(self) -> None:
        """Проверяет вызов health_service.add_medication для add_medication."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_medication = MagicMock()
        mock_medication.name = "Бравекто"
        mock_medication.start_date = datetime.date(2026, 3, 8)

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.health_service.add_medication",
            new_callable=AsyncMock,
            return_value=mock_medication,
        ) as mock_add_medication:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="add_medication",
                arguments={
                    "pet_name": "Луна",
                    "name": "Бравекто",
                    "start_date": "2026-03-08",
                },
                user_id=100500,
                family_id=1,
            )

            mock_add_medication.assert_awaited_once()

        assert isinstance(result, str)

    async def test_add_diet_calls_nutrition_service_with_user_origin(self) -> None:
        """handle_tool_call('add_diet', ...) вызывает сервис и передаёт recorded_by."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_pet = MagicMock()
        mock_pet.id = 77

        mock_diet = MagicMock()
        mock_diet.food_brand = "Acana"
        mock_diet.start_date = datetime.date(2026, 3, 8)

        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_diet_record",
                new_callable=AsyncMock,
                return_value=mock_diet,
            ) as mock_add_diet_record,
        ):
            result = await handle_tool_call(
                session=mock_session,
                tool_name="add_diet",
                arguments={
                    "pet_name": "Луна",
                    "food_brand": "Acana",
                    "start_date": "2026-03-08",
                },
                user_id=100500,
                family_id=1,
            )

            mock_add_diet_record.assert_awaited_once()
            add_diet_kwargs = mock_add_diet_record.await_args.kwargs
            assert add_diet_kwargs["pet_id"] == 77
            assert add_diet_kwargs["food_brand"] == "Acana"
            assert add_diet_kwargs["start_date"] == datetime.date(2026, 3, 8)
            assert add_diet_kwargs["recorded_by"] == 100500

        assert isinstance(result, str)

    async def test_create_pet_passes_actor_id_to_pet_service(self) -> None:
        """handle_tool_call('create_pet', ...) передаёт actor_id в create_pet."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_pet = MagicMock()
        mock_pet.name = "Мурзик"
        mock_pet.species = "cat"

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.pet_service.create_pet",
            new_callable=AsyncMock,
            return_value=mock_pet,
        ) as mock_create_pet:
            result = await handle_tool_call(
                session=mock_session,
                tool_name="create_pet",
                arguments={"name": "Мурзик", "species": "cat"},
                user_id=100500,
                family_id=1,
            )

            mock_create_pet.assert_awaited_once()
            create_pet_kwargs = mock_create_pet.await_args.kwargs
            assert create_pet_kwargs["actor_id"] == 100500
            assert "created_by" not in create_pet_kwargs

        assert isinstance(result, str)

    async def test_update_pet_passes_actor_id_to_pet_service(self) -> None:
        """handle_tool_call('update_pet', ...) передаёт actor_id в update_pet."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_existing_pet = MagicMock()
        mock_existing_pet.id = 77
        mock_existing_pet.name = "Луна"

        mock_updated_pet = MagicMock()
        mock_updated_pet.name = "Луна"

        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_existing_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new_callable=AsyncMock,
                return_value=mock_updated_pet,
            ) as mock_update_pet,
        ):
            result = await handle_tool_call(
                session=mock_session,
                tool_name="update_pet",
                arguments={"pet_name": "Луна", "breed": "Корги"},
                user_id=100500,
                family_id=1,
            )

            mock_update_pet.assert_awaited_once()
            update_pet_kwargs = mock_update_pet.await_args.kwargs
            assert update_pet_kwargs["actor_id"] == 100500
            assert update_pet_kwargs["breed"] == "Корги"

        assert isinstance(result, str)

    async def test_update_pet_converts_birth_date_string_to_date(self) -> None:
        """_handle_update_pet передаёт birth_date в сервис как datetime.date."""
        from backend.app.agent.tool_handlers import _handle_update_pet

        mock_existing_pet = MagicMock(id=77)
        mock_updated_pet = MagicMock(name="Луна")
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_existing_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new_callable=AsyncMock,
                return_value=mock_updated_pet,
            ) as mock_update_pet,
        ):
            await _handle_update_pet(
                session=mock_session,
                arguments={"pet_name": "Луна", "birth_date": "2021-03-15"},
                user_id=100500,
                family_id=1,
                family_timezone="Europe/Moscow",
            )

        update_kwargs = mock_update_pet.await_args.kwargs
        assert isinstance(update_kwargs["birth_date"], datetime.date)
        assert update_kwargs["birth_date"] == datetime.date(2021, 3, 15)

    async def test_update_pet_rejects_unexpected_service_fields(self) -> None:
        """_handle_update_pet отклоняет служебные поля вне whitelist."""
        from backend.app.agent.tool_handlers import _handle_update_pet

        mock_existing_pet = MagicMock(id=77)
        mock_updated_pet = MagicMock(name="Луна")
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_existing_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.pet_service.update_pet",
                new_callable=AsyncMock,
                return_value=mock_updated_pet,
            ) as mock_update_pet,
            pytest.raises((TypeError, ValueError)),
        ):
            await _handle_update_pet(
                session=mock_session,
                arguments={
                    "pet_name": "Луна",
                    "breed": "Корги",
                    "created_by": 999001,
                },
                user_id=100500,
                family_id=1,
            )

        mock_update_pet.assert_not_awaited()

    async def test_service_exception_returns_error_string(self) -> None:
        """При исключении в сервисе handle_tool_call возвращает строку с ошибкой."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_session = AsyncMock(spec=AsyncSession)

        with patch(
            "backend.app.agent.tool_handlers.health_service.add_weight",
            new_callable=AsyncMock,
            side_effect=ValueError("Питомец не найден"),
        ):
            result = await handle_tool_call(
                session=mock_session,
                tool_name="add_weight",
                arguments={
                    "pet_name": "Несуществующий",
                    "weight_kg": 10.0,
                    "measured_at": "2026-03-08",
                },
                user_id=100500,
                family_id=1,
            )

        # Не должен бросать исключение, а вернуть строку с ошибкой
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize(
        ("handler_name", "arguments", "service_patch", "date_field_name"),
        [
            (
                "_handle_add_weight",
                {
                    "pet_name": "Луна",
                    "weight_kg": 12.5,
                    "measured_at": "2026-03-08",
                },
                "backend.app.agent.tool_handlers.health_service.add_weight",
                "measured_at",
            ),
            (
                "_handle_add_vaccination",
                {
                    "pet_name": "Луна",
                    "vaccine_name": "Нобивак DHPPi",
                    "date": "2026-03-08",
                },
                "backend.app.agent.tool_handlers.health_service.add_vaccination",
                "date",
            ),
            (
                "_handle_add_medication",
                {
                    "pet_name": "Луна",
                    "name": "Бравекто",
                    "start_date": "2026-03-08",
                },
                "backend.app.agent.tool_handlers.health_service.add_medication",
                "start_date",
            ),
            (
                "_handle_add_diet",
                {
                    "pet_name": "Луна",
                    "food_brand": "Acana",
                    "start_date": "2026-03-08",
                },
                "backend.app.agent.tool_handlers.nutrition_service.add_diet_record",
                "start_date",
            ),
        ],
    )
    async def test_date_fields_use_shared_runtime_parser_helper(
        self,
        handler_name: str,
        arguments: dict,
        service_patch: str,
        date_field_name: str,
    ) -> None:
        """Проверяет единый парсер для measured_at/date/start_date в tool_handlers."""
        from backend.app.agent import tool_handlers

        mock_session = AsyncMock(spec=AsyncSession)
        mock_pet = MagicMock()
        mock_pet.id = 77

        mock_record = MagicMock()
        mock_record.weight_kg = Decimal("12.50")
        mock_record.measured_at = datetime.date(2026, 3, 8)
        mock_record.vaccine_name = "Нобивак DHPPi"
        mock_record.date = datetime.date(2026, 3, 8)
        mock_record.name = "Бравекто"
        mock_record.start_date = datetime.date(2026, 3, 8)
        mock_record.food_brand = "Acana"

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                service_patch,
                new_callable=AsyncMock,
                return_value=mock_record,
            ) as mock_service_call,
            patch(
                "backend.app.agent.tool_handlers.parse_runtime_date",
                return_value=datetime.date(2026, 3, 8),
                create=True,
            ) as mock_runtime_parser,
        ):
            handler = getattr(tool_handlers, handler_name)
            await handler(
                session=mock_session,
                arguments=arguments,
                user_id=100500,
                family_id=1,
            )

        mock_runtime_parser.assert_called_once()
        service_kwargs = mock_service_call.await_args.kwargs
        assert service_kwargs[date_field_name] == datetime.date(2026, 3, 8)

    async def test_fed_at_accepts_offset_aware_iso_datetime_without_runtime_parser(
        self,
    ) -> None:
        """fed_at принимает offset-aware ISO datetime без date helper."""
        from backend.app.agent.tool_handlers import _handle_add_feeding

        mock_session = AsyncMock(spec=AsyncSession)
        mock_pet = MagicMock()
        mock_pet.id = 77

        mock_record = MagicMock()
        mock_record.food_description = "Acana 50g"

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_feeding_entry",
                new_callable=AsyncMock,
                return_value=mock_record,
            ) as mock_add_feeding_entry,
            patch(
                "backend.app.agent.tool_handlers.parse_runtime_date",
                return_value=datetime.date(2026, 3, 8),
                create=True,
            ) as mock_runtime_parser,
        ):
            await _handle_add_feeding(
                session=mock_session,
                arguments={
                    "pet_name": "Луна",
                    "fed_at": "2026-03-08T12:30:00+03:00",
                    "food_description": "Acana 50g",
                },
                user_id=100500,
                family_id=1,
            )

        mock_runtime_parser.assert_not_called()
        feeding_kwargs = mock_add_feeding_entry.await_args.kwargs
        assert feeding_kwargs["fed_at"] == datetime.datetime(
            2026,
            3,
            8,
            12,
            30,
            0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=3)),
        )

    async def test_fed_at_rejects_naive_iso_datetime(self) -> None:
        """_handle_add_feeding детерминированно отклоняет naive fed_at."""
        from backend.app.agent.tool_handlers import _handle_add_feeding

        mock_session = AsyncMock(spec=AsyncSession)
        mock_pet = MagicMock(id=77)
        mock_record = MagicMock(food_description="Acana 50g")

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.nutrition_service.add_feeding_entry",
                new_callable=AsyncMock,
                return_value=mock_record,
            ) as mock_add_feeding_entry,
            pytest.raises((TypeError, ValueError)),
        ):
            await _handle_add_feeding(
                session=mock_session,
                arguments={
                    "pet_name": "Луна",
                    "fed_at": "2026-03-08T12:30:00",
                    "food_description": "Acana 50g",
                },
                user_id=100500,
                family_id=1,
            )

        mock_add_feeding_entry.assert_not_awaited()

    def test_format_pet_profile_uses_i18n_fragments(self) -> None:
        """Профиль питомца собирается через i18n-ключи, без ручных label-строк."""
        from backend.app.agent.tool_handlers import _format_pet_profile

        pet = SimpleNamespace(
            name="Луна",
            species="dog",
            breed="Корги",
            birth_date=datetime.date(2020, 5, 17),
        )

        with patch(
            "backend.app.agent.tool_handlers.get_message",
            side_effect=lambda key, language="ru", **kwargs: f"{key}:{language}",
        ) as mock_get_message:
            result = _format_pet_profile(pet, "ru")

        called_keys = [call.args[0] for call in mock_get_message.call_args_list]
        assert "pet_profile" in called_keys
        assert "pet_profile_breed_part" in called_keys
        assert "pet_profile_birth_date_part" in called_keys
        assert result == "pet_profile:ru"

    def test_format_emergency_profile_uses_i18n_fragments(self) -> None:
        """Экстренный профиль использует i18n-ключи для field-label и fallback."""
        from backend.app.agent.tool_handlers import _format_emergency_profile

        profile = SimpleNamespace(
            allergies="Курица",
            chronic_conditions="Артрит",
            vet_contact="Доктор Пёс",
        )

        with patch(
            "backend.app.agent.tool_handlers.get_message",
            side_effect=lambda key,
            language="ru",
            **kwargs: f"{key}:{language}:{kwargs}",
        ) as mock_get_message:
            result = _format_emergency_profile(profile, "en")

        called_keys = [call.args[0] for call in mock_get_message.call_args_list]
        assert "emergency_profile_allergies" in called_keys
        assert "emergency_profile_chronic_conditions" in called_keys
        assert "emergency_profile_vet_contact" in called_keys
        assert "emergency_profile_empty" not in called_keys
        assert "emergency_profile_allergies:en" in result

    def test_profile_formatting_localizes_ru_and_en(self) -> None:
        """Профиль питомца возвращает разные локализованные ответы для ru/en."""
        from backend.app.agent.tool_handlers import _format_pet_profile

        pet = SimpleNamespace(name="Луна", species="dog", breed=None, birth_date=None)

        result_ru = _format_pet_profile(pet, "ru")
        result_en = _format_pet_profile(pet, "en")

        assert "Имя:" in result_ru
        assert "Name:" in result_en
        assert result_ru != result_en

    def test_emergency_profile_formatting_localizes_ru_and_en(self) -> None:
        """Экстренный профиль локализует field-label для ru/en."""
        from backend.app.agent.tool_handlers import _format_emergency_profile

        profile = SimpleNamespace(
            allergies="Chicken",
            chronic_conditions=None,
            vet_contact="Dr. Bark",
        )

        result_ru = _format_emergency_profile(profile, "ru")
        result_en = _format_emergency_profile(profile, "en")

        assert "Аллергии:" in result_ru
        assert "Allergies:" in result_en
        assert result_ru != result_en


# ═══════════════════════════════════════════════════════════════════════════════
# T032: brain.py -- Agent brain (run_agent)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentBrain:
    """Тесты основного цикла AI-агента (run_agent)."""

    async def test_calls_openai_with_system_prompt_and_user_message(self) -> None:
        """Проверяет вызов OpenAI API с system prompt и user message."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)

        # Мокаем OpenAI response
        mock_output_message = MagicMock()
        mock_output_message.type = "message"
        mock_output_message.content = [MagicMock(text="Привет! Как дела у Луны?")]

        mock_response = MagicMock()
        mock_response.id = "resp_test_123"
        mock_response.output = [mock_output_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="Ты -- ассистент по уходу за питомцами.",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            # Мокаем работу с ConversationState
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            result = await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Как дела у Луны?",
            )

            mock_client.responses.create.assert_awaited_once()

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_detects_english_and_passes_language_to_prompt_and_tool_handler(
        self,
    ) -> None:
        """run_agent определяет english input и пробрасывает response_language='en'."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)

        mock_tool_call = MagicMock()
        mock_tool_call.type = "function_call"
        mock_tool_call.name = "add_weight"
        mock_tool_call.arguments = (
            '{"pet_name": "Luna", "weight_kg": 12.5, "measured_at": "2026-03-08"}'
        )
        mock_tool_call.call_id = "call_lang_en_1"

        mock_first_response = MagicMock()
        mock_first_response.id = "resp_lang_en_with_tool"
        mock_first_response.output = [mock_tool_call]

        mock_final_message = MagicMock()
        mock_final_message.type = "message"
        mock_final_message.content = [MagicMock(text="Done.")]

        mock_second_response = MagicMock()
        mock_second_response.id = "resp_lang_en_final"
        mock_second_response.output = [mock_final_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(
            side_effect=[mock_first_response, mock_second_response]
        )

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ) as mock_build_system_prompt,
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[{"type": "function", "name": "add_weight"}],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
                return_value="Weight recorded.",
            ) as mock_handle_tool_call,
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Please record Luna weight as 12.5 kg today",
            )

        prompt_kwargs = mock_build_system_prompt.await_args.kwargs
        handle_kwargs = mock_handle_tool_call.await_args.kwargs
        assert prompt_kwargs["response_language"] == "en"
        assert handle_kwargs["response_language"] == "en"

    async def test_fallback_language_is_russian_for_non_ru_non_en_input(self) -> None:
        """Проверяет fallback language='ru' для ввода вне ru/en."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)

        mock_output_message = MagicMock()
        mock_output_message.type = "message"
        mock_output_message.content = [MagicMock(text="Ответ")]

        mock_response = MagicMock()
        mock_response.id = "resp_lang_fallback"
        mock_response.output = [mock_output_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ) as mock_build_system_prompt,
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="12345 !!!",
            )

        prompt_kwargs = mock_build_system_prompt.await_args.kwargs
        assert prompt_kwargs["response_language"] == "ru"
        assert isinstance(prompt_kwargs["family_today"], datetime.date)

    async def test_returns_text_response(self) -> None:
        """run_agent возвращает текстовый ответ от модели."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)
        expected_text = "Луна весит 12.5 кг, всё в норме!"

        mock_output_message = MagicMock()
        mock_output_message.type = "message"
        mock_output_message.content = [MagicMock(text=expected_text)]

        mock_response = MagicMock()
        mock_response.id = "resp_test_456"
        mock_response.output = [mock_output_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            result = await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Сколько весит Луна?",
            )

        assert expected_text in result

    async def test_updates_conversation_state(self) -> None:
        """run_agent обновляет ConversationState (last_response_id, turn_count)."""
        from backend.app.agent.brain import run_agent
        from backend.app.db.models.family import ConversationState

        mock_session = AsyncMock(spec=AsyncSession)

        # Создаём существующее состояние диалога
        existing_state = ConversationState(
            user_id=100500,
            last_response_id="resp_old",
            turn_count=3,
        )

        mock_output_message = MagicMock()
        mock_output_message.type = "message"
        mock_output_message.content = [MagicMock(text="Ответ")]

        mock_response = MagicMock()
        mock_response.id = "resp_new_789"
        mock_response.output = [mock_output_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(
                    scalar_one_or_none=MagicMock(return_value=existing_state)
                )
            )

            await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Тестовое сообщение",
            )

        # Проверяем, что состояние обновлено
        assert existing_state.last_response_id == "resp_new_789"
        assert existing_state.turn_count == 4

    async def test_passes_same_family_today_to_prompt_and_tool_handlers(self) -> None:
        """run_agent передаёт один и тот же family_today в prompt и tool handlers."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)
        shared_family_today = datetime.date(2026, 3, 8)

        mock_tool_call = MagicMock()
        mock_tool_call.type = "function_call"
        mock_tool_call.name = "add_weight"
        mock_tool_call.arguments = (
            '{"pet_name":"Луна","weight_kg":12.5,"measured_at":"2026-03-08"}'
        )
        mock_tool_call.call_id = "call_family_today"

        mock_first_response = MagicMock(id="resp_with_tool", output=[mock_tool_call])
        mock_message = MagicMock(type="message", content=[MagicMock(text="OK")])
        mock_second_response = MagicMock(id="resp_final", output=[mock_message])

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(
            side_effect=[mock_first_response, mock_second_response]
        )

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ) as mock_build_system_prompt,
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[{"type": "function", "name": "add_weight"}],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
                return_value="saved",
            ) as mock_handle_tool_call,
            patch(
                "backend.app.agent.brain._resolve_family_today",
                new_callable=AsyncMock,
                return_value=shared_family_today,
            ),
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )
            await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Запиши вес Луны",
            )

        prompt_kwargs = mock_build_system_prompt.await_args.kwargs
        handler_kwargs = mock_handle_tool_call.await_args.kwargs
        assert prompt_kwargs["family_today"] is shared_family_today
        assert handler_kwargs["family_today"] is shared_family_today

    async def test_conversation_state_updated_at_changes_after_state_update(
        self,
        db_session: AsyncSession,
    ) -> None:
        """run_agent обновляет updated_at у существующего ConversationState."""
        from backend.app.agent.brain import run_agent
        from backend.app.db.models.family import ConversationState

        family = await _create_family_with_settings(db_session, timezone="UTC")
        member = await _create_member(db_session, family_id=family.id, user_id=100500)
        old_timestamp = datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)
        state = ConversationState(
            user_id=member.id,
            last_response_id="resp_old",
            turn_count=1,
            updated_at=old_timestamp,
        )
        db_session.add(state)
        await db_session.flush()

        mock_response_message = MagicMock(type="message")
        mock_response_message.content = [MagicMock(text="Ответ")]
        mock_response = MagicMock(id="resp_updated", output=[mock_response_message])
        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            await run_agent(
                session=db_session,
                family_id=family.id,
                user_id=member.id,
                user_message="Привет",
            )

        await db_session.refresh(state)
        assert state.updated_at > old_timestamp

    async def test_handles_tool_calls(self) -> None:
        """При tool_calls в ответе run_agent вызывает handle_tool_call и продолжает."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)

        # Первый ответ: tool call
        mock_tool_call = MagicMock()
        mock_tool_call.type = "function_call"
        mock_tool_call.name = "add_weight"
        mock_tool_call.arguments = (
            '{"pet_name": "Луна", "weight_kg": 12.5, "measured_at": "2026-03-08"}'
        )
        mock_tool_call.call_id = "call_abc123"

        mock_first_response = MagicMock()
        mock_first_response.id = "resp_with_tools"
        mock_first_response.output = [mock_tool_call]

        # Второй ответ: финальное сообщение
        mock_final_message = MagicMock()
        mock_final_message.type = "message"
        mock_final_message.content = [MagicMock(text="Вес 12.5 кг записан!")]

        mock_second_response = MagicMock()
        mock_second_response.id = "resp_final"
        mock_second_response.output = [mock_final_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(
            side_effect=[mock_first_response, mock_second_response]
        )

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[{"type": "function", "name": "add_weight"}],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
                return_value="Вес 12.50 кг записан для Луны",
            ) as mock_handle,
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            result = await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Луна весит 12.5 кг",
            )

            mock_handle.assert_awaited_once()

        assert "записан" in result.lower() or len(result) > 0

    async def test_resets_context_when_turn_count_exceeds_limit(self) -> None:
        """run_agent сбрасывает previous_response_id при turn_count > 10."""
        from backend.app.agent.brain import run_agent
        from backend.app.db.models.family import ConversationState

        mock_session = AsyncMock(spec=AsyncSession)

        # Состояние с turn_count > 10 -- контекст должен сброситься
        old_state = ConversationState(
            user_id=100500,
            last_response_id="resp_very_old",
            turn_count=11,
        )

        mock_output_message = MagicMock()
        mock_output_message.type = "message"
        mock_output_message.content = [MagicMock(text="Ответ после сброса")]

        mock_response = MagicMock()
        mock_response.id = "resp_fresh_start"
        mock_response.output = [mock_output_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            mock_session.execute = AsyncMock(
                return_value=MagicMock(
                    scalar_one_or_none=MagicMock(return_value=old_state)
                )
            )

            await run_agent(
                session=mock_session,
                family_id=1,
                user_id=100500,
                user_message="Напомни, что мы обсуждали?",
            )

        # После сброса turn_count должен быть 1 (текущий ход),
        # а не 12 (продолжение старого)
        assert old_state.turn_count <= 1

    async def test_creates_new_conversation_state_for_new_user(self) -> None:
        """run_agent создаёт новый ConversationState для пользователя без истории."""
        from backend.app.agent.brain import run_agent

        mock_session = AsyncMock(spec=AsyncSession)

        mock_output_message = MagicMock()
        mock_output_message.type = "message"
        mock_output_message.content = [MagicMock(text="Привет!")]

        mock_response = MagicMock()
        mock_response.id = "resp_first_ever"
        mock_response.output = [mock_output_message]

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.app.agent.brain.get_ai_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "backend.app.agent.brain.build_system_prompt",
                new_callable=AsyncMock,
                return_value="System prompt",
            ),
            patch(
                "backend.app.agent.brain.get_tool_definitions",
                return_value=[],
            ),
            patch(
                "backend.app.agent.brain.handle_tool_call",
                new_callable=AsyncMock,
            ),
        ):
            # Нет существующего состояния -- scalar_one_or_none возвращает None
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            result = await run_agent(
                session=mock_session,
                family_id=1,
                user_id=999999,
                user_message="Привет!",
            )

        # Должен был добавить новый ConversationState
        assert mock_session.add.called or mock_session.merge.called
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# T033: whisper.py -- Voice transcription
# ═══════════════════════════════════════════════════════════════════════════════


class TestWhisperTranscription:
    """Тесты транскрипции голосовых сообщений через OpenAI Whisper."""

    async def test_downloads_file_via_bot(self) -> None:
        """transcribe_voice скачивает файл через bot.download_file."""
        from backend.app.agent.whisper import transcribe_voice

        mock_bot = AsyncMock()
        mock_file = AsyncMock()
        mock_file.file_path = "voice/file_123.ogg"
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        mock_bot.download_file = AsyncMock(return_value=b"fake-audio-bytes")

        mock_transcription = MagicMock()
        mock_transcription.text = "Луна сегодня хорошо поела"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "backend.app.agent.whisper.get_whisper_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await transcribe_voice(
                bot=mock_bot,
                voice_file_id="file_abc_123",
            )

            mock_bot.get_file.assert_awaited_once_with("file_abc_123")
            mock_bot.download_file.assert_awaited_once()

        assert isinstance(result, str)

    async def test_sends_audio_to_whisper_api(self) -> None:
        """transcribe_voice отправляет bytes-аудио как file-like с именем."""
        from backend.app.agent.whisper import transcribe_voice

        mock_bot = AsyncMock()
        mock_file = AsyncMock()
        mock_file.file_path = "voice/file_456.ogg"
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        mock_bot.download_file = AsyncMock(return_value=b"fake-audio-bytes")

        mock_transcription = MagicMock()
        mock_transcription.text = "Текст транскрипции"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "backend.app.agent.whisper.get_whisper_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await transcribe_voice(
                bot=mock_bot,
                voice_file_id="file_456",
            )

            mock_client.audio.transcriptions.create.assert_awaited_once()
            whisper_call_kwargs = (
                mock_client.audio.transcriptions.create.await_args.kwargs
            )
            whisper_file = whisper_call_kwargs["file"]

            assert hasattr(whisper_file, "read")
            assert whisper_file.name == "voice.ogg"

    async def test_accepts_binary_file_like_from_download_file(self) -> None:
        """transcribe_voice принимает BinaryIO из bot.download_file без TypeError."""
        import io

        from backend.app.agent.whisper import transcribe_voice

        mock_bot = AsyncMock()
        mock_file = AsyncMock()
        mock_file.file_path = "voice/file_binary_io.ogg"
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        mock_bot.download_file = AsyncMock(
            return_value=io.BytesIO(b"fake-audio-binary-io")
        )

        mock_transcription = MagicMock()
        mock_transcription.text = "Текст из BinaryIO"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "backend.app.agent.whisper.get_whisper_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await transcribe_voice(
                bot=mock_bot,
                voice_file_id="file_binary_io",
            )

        assert result == "Текст из BinaryIO"

    async def test_returns_transcription_text(self) -> None:
        """transcribe_voice возвращает текст транскрипции."""
        from backend.app.agent.whisper import transcribe_voice

        expected_text = "Луна сегодня весит двенадцать килограмм"

        mock_bot = AsyncMock()
        mock_file = AsyncMock()
        mock_file.file_path = "voice/file_789.ogg"
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        mock_bot.download_file = AsyncMock(return_value=b"fake-audio-bytes")

        mock_transcription = MagicMock()
        mock_transcription.text = expected_text

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "backend.app.agent.whisper.get_whisper_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await transcribe_voice(
                bot=mock_bot,
                voice_file_id="file_789",
            )

        assert result == expected_text


# ═══════════════════════════════════════════════════════════════════════════════
# T110: Emergency tools -- инструменты экстренного профиля
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmergencyTools:
    """Тесты инструментов экстренного профиля в tools.py и tool_handlers.py."""

    def test_update_emergency_profile_tool_defined(self) -> None:
        """Tool definition для 'update_emergency_profile' присутствует."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = {tool["name"] for tool in tools}

        assert "update_emergency_profile" in tool_names

    def test_get_emergency_profile_tool_defined(self) -> None:
        """Tool definition для 'get_emergency_profile' присутствует."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = {tool["name"] for tool in tools}

        assert "get_emergency_profile" in tool_names

    def test_update_emergency_profile_schema_has_wave5_fields(self) -> None:
        """Schema update_emergency_profile содержит новые поля Wave 5."""
        from backend.app.agent.tools import get_tool_definitions

        tools = get_tool_definitions()
        update_tool = next(
            tool for tool in tools if tool["name"] == "update_emergency_profile"
        )
        properties = update_tool["parameters"]["properties"]

        assert "blood_type" in properties
        assert properties["blood_type"]["type"] == "string"
        assert "rabies_vaccination_date" in properties
        assert properties["rabies_vaccination_date"]["type"] == "string"
        assert "latest_weight_snapshot" in properties
        assert properties["latest_weight_snapshot"]["type"] == "number"

    async def test_handle_update_emergency_profile(self) -> None:
        """Проверяет передачу actor_id в update_emergency_profile."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_pet = MagicMock()
        mock_pet.id = 77

        mock_profile = MagicMock()
        mock_profile.allergies = "Курица"
        mock_profile.pet_id = 1

        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.update_emergency_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ) as mock_update,
        ):
            result = await handle_tool_call(
                session=mock_session,
                tool_name="update_emergency_profile",
                arguments={
                    "pet_name": "Луна",
                    "allergies": "Курица",
                },
                user_id=100500,
                family_id=1,
            )

            mock_update.assert_awaited_once()
            update_emergency_profile_kwargs = mock_update.await_args.kwargs
            assert update_emergency_profile_kwargs["actor_id"] == 100500
            assert update_emergency_profile_kwargs["allergies"] == "Курица"

        assert isinstance(result, str)

    async def test_handle_update_emergency_profile_wave5_parsing_and_normalization(
        self,
    ) -> None:
        """Handler нормализует nullable-поля и приводит Wave 5 типы перед сервисом."""
        from backend.app.agent.tool_handlers import _handle_update_emergency_profile

        mock_pet = MagicMock()
        mock_pet.id = 77
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.parse_runtime_date",
                return_value=datetime.date(2026, 3, 7),
            ) as mock_parse_runtime_date,
            patch(
                "backend.app.agent.tool_handlers.health_service.update_emergency_profile",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ) as mock_update,
        ):
            result = await _handle_update_emergency_profile(
                session=mock_session,
                arguments={
                    "pet_name": "Луна",
                    "allergies": "",
                    "chronic_conditions": "unknown",
                    "vet_contact": " null ",
                    "blood_type": "UNKNOWN",
                    "rabies_vaccination_date": "вчера",
                    "latest_weight_snapshot": "12.40",
                },
                user_id=100500,
                family_id=1,
                family_timezone="Europe/Moscow",
            )

        mock_parse_runtime_date.assert_called_once_with(
            value="вчера",
            timezone="Europe/Moscow",
            field_name="rabies_vaccination_date",
        )
        update_kwargs = mock_update.await_args.kwargs
        assert update_kwargs["actor_id"] == 100500
        assert update_kwargs["allergies"] is None
        assert update_kwargs["chronic_conditions"] is None
        assert update_kwargs["vet_contact"] is None
        assert update_kwargs["blood_type"] is None
        assert update_kwargs["rabies_vaccination_date"] == datetime.date(2026, 3, 7)
        assert update_kwargs["latest_weight_snapshot"] == Decimal("12.40")
        assert isinstance(result, str)

    async def test_update_emergency_profile_rejects_unexpected_service_fields(
        self,
    ) -> None:
        """_handle_update_emergency_profile отклоняет служебные поля вне whitelist."""
        from backend.app.agent.tool_handlers import _handle_update_emergency_profile

        mock_pet = MagicMock(id=77)
        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.update_emergency_profile",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ) as mock_update,
            pytest.raises((TypeError, ValueError)),
        ):
            await _handle_update_emergency_profile(
                session=mock_session,
                arguments={
                    "pet_name": "Луна",
                    "allergies": "Курица",
                    "created_at": "2026-03-08T12:00:00+03:00",
                },
                user_id=100500,
                family_id=1,
            )

        mock_update.assert_not_awaited()

    async def test_handle_get_emergency_profile(self) -> None:
        """Проверяет передачу actor_id в get_or_create_emergency_profile."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_pet = MagicMock()
        mock_pet.id = 77

        mock_profile = MagicMock()
        mock_profile.allergies = "Курица"
        mock_profile.chronic_conditions = None
        mock_profile.vet_contact = "Ветклиника Друг"
        mock_profile.pet_id = 1

        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_or_create_emergency_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ) as mock_get,
        ):
            result = await handle_tool_call(
                session=mock_session,
                tool_name="get_emergency_profile",
                arguments={"pet_name": "Луна"},
                user_id=100500,
                family_id=1,
            )

            mock_get.assert_awaited_once()
            get_emergency_profile_kwargs = mock_get.await_args.kwargs
            assert get_emergency_profile_kwargs["actor_id"] == 100500

        assert isinstance(result, str)

    @pytest.mark.parametrize("response_language", ["ru", "en"])
    async def test_get_emergency_profile_tool_returns_wave5_fields_with_i18n(
        self,
        response_language: str,
    ) -> None:
        """get_emergency_profile возвращает blood/rabies/weight через ru/en i18n."""
        from backend.app.agent.tool_handlers import handle_tool_call

        mock_pet = MagicMock(id=77)
        mock_profile = MagicMock()
        mock_profile.allergies = None
        mock_profile.chronic_conditions = None
        mock_profile.vet_contact = None
        mock_profile.blood_type = "DEA 1.1+"
        mock_profile.rabies_vaccination_date = datetime.date(2026, 2, 1)
        mock_profile.latest_weight_snapshot = Decimal("12.40")

        mock_session = AsyncMock(spec=AsyncSession)

        with (
            patch(
                "backend.app.agent.tool_handlers._resolve_pet",
                new_callable=AsyncMock,
                return_value=mock_pet,
            ),
            patch(
                "backend.app.agent.tool_handlers.health_service.get_or_create_emergency_profile",
                new_callable=AsyncMock,
                return_value=mock_profile,
            ),
            patch(
                "backend.app.agent.tool_handlers.get_message",
                side_effect=lambda key, language="ru", **kwargs: (
                    f"{key}:{language}:{kwargs.get('value')}"
                ),
            ),
        ):
            result = await handle_tool_call(
                session=mock_session,
                tool_name="get_emergency_profile",
                arguments={"pet_name": "Луна"},
                user_id=100500,
                family_id=1,
                response_language=response_language,
            )

        assert f"emergency_profile_blood_type:{response_language}:DEA 1.1+" in result
        assert (
            "emergency_profile_rabies_vaccination_date:"
            f"{response_language}:2026-02-01" in result
        )
        assert (
            f"emergency_profile_latest_weight_snapshot:{response_language}:12.40"
            in result
        )


# ═══════════════════════════════════════════════════════════════════════════════
# T111: date_utils.py -- Timezone-aware date normalization
# ═══════════════════════════════════════════════════════════════════════════════


class TestDateNormalization:
    """Тесты нормализации относительных дат с учётом таймзоны."""

    def test_today_returns_current_date_utc(self) -> None:
        """'сегодня' -> сегодняшняя дата в UTC."""
        from backend.app.agent.date_utils import normalize_relative_date

        result = normalize_relative_date("сегодня", timezone="UTC")

        assert result is not None
        assert isinstance(result, datetime.date)
        # Проверяем, что дата -- сегодня в UTC
        expected = datetime.datetime.now(tz=datetime.UTC).date()
        assert result == expected

    def test_tomorrow_returns_next_day(self) -> None:
        """'завтра' -> date.today() + 1 день."""
        from backend.app.agent.date_utils import normalize_relative_date

        result = normalize_relative_date("завтра", timezone="UTC")

        assert result is not None
        expected = (
            datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(days=1)
        ).date()
        assert result == expected

    def test_yesterday_returns_previous_day(self) -> None:
        """'вчера' -> date.today() - 1 день."""
        from backend.app.agent.date_utils import normalize_relative_date

        result = normalize_relative_date("вчера", timezone="UTC")

        assert result is not None
        expected = (
            datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=1)
        ).date()
        assert result == expected

    def test_plain_text_returns_none(self) -> None:
        """Обычный текст без дат -> None."""
        from backend.app.agent.date_utils import normalize_relative_date

        result = normalize_relative_date(
            "Луна хорошо себя чувствует",
            timezone="UTC",
        )

        assert result is None

    def test_moscow_timezone(self) -> None:
        """'сегодня' в Europe/Moscow корректно учитывает смещение +3."""
        from backend.app.agent.date_utils import normalize_relative_date

        result = normalize_relative_date("сегодня", timezone="Europe/Moscow")

        assert result is not None
        assert isinstance(result, datetime.date)

        # Дата в Москве может отличаться от UTC, если сейчас ночь UTC
        import zoneinfo

        moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
        expected = datetime.datetime.now(tz=moscow_tz).date()
        assert result == expected

    def test_empty_string_returns_none(self) -> None:
        """Пустая строка -> None."""
        from backend.app.agent.date_utils import normalize_relative_date

        result = normalize_relative_date("", timezone="UTC")

        assert result is None

    def test_case_insensitive(self) -> None:
        """Распознавание дат не зависит от регистра."""
        from backend.app.agent.date_utils import normalize_relative_date

        result_lower = normalize_relative_date("сегодня", timezone="UTC")
        result_upper = normalize_relative_date("Сегодня", timezone="UTC")

        assert result_lower is not None
        assert result_lower == result_upper

    def test_supports_english_relative_keywords(self) -> None:
        """Поддерживаются английские относительные даты today/yesterday/tomorrow."""
        from backend.app.agent.date_utils import normalize_relative_date

        today_result = normalize_relative_date("today", timezone="UTC")
        yesterday_result = normalize_relative_date("yesterday", timezone="UTC")
        tomorrow_result = normalize_relative_date("tomorrow", timezone="UTC")

        assert today_result == datetime.datetime.now(tz=datetime.UTC).date()
        assert (
            yesterday_result
            == (
                datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=1)
            ).date()
        )
        assert (
            tomorrow_result
            == (
                datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(days=1)
            ).date()
        )

    def test_parse_runtime_date_supports_iso_and_relative_values(self) -> None:
        """parse_runtime_date поддерживает ISO и относительные значения."""
        from backend.app.agent.date_utils import parse_runtime_date

        iso_date = parse_runtime_date("2026-03-08", timezone="UTC", field_name="date")
        relative_date = parse_runtime_date("today", timezone="UTC", field_name="date")

        assert iso_date == datetime.date(2026, 3, 8)
        assert relative_date == datetime.datetime.now(tz=datetime.UTC).date()

    def test_parse_runtime_date_raises_domain_error_for_invalid_input(self) -> None:
        """Невалидная дата вызывает понятную доменную ошибку с именем поля."""
        from backend.app.agent.date_utils import (
            InvalidRuntimeDateError,
            parse_runtime_date,
        )

        with pytest.raises(InvalidRuntimeDateError) as error_info:
            parse_runtime_date(
                "2026-99-99",
                timezone="UTC",
                field_name="start_date",
            )

        error_text = str(error_info.value)
        assert "start_date" in error_text
        assert "2026-99-99" in error_text


# ═══════════════════════════════════════════════════════════════════════════════
# T112: i18n.py -- Localized message templates
# ═══════════════════════════════════════════════════════════════════════════════


class TestI18n:
    """Тесты локализованных шаблонов сообщений."""

    def test_returns_russian_by_default(self) -> None:
        """get_message() по умолчанию возвращает текст на русском."""
        from backend.app.agent.i18n import get_message

        result = get_message("weight_saved")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_supports_english(self) -> None:
        """get_message(language='en') возвращает текст на английском."""
        from backend.app.agent.i18n import get_message

        result = get_message("weight_saved", language="en")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_supports_parameter_substitution(self) -> None:
        """get_message() поддерживает подстановку параметров."""
        from backend.app.agent.i18n import get_message

        result = get_message("weight_saved", weight="12.5", pet_name="Луна")

        assert isinstance(result, str)
        # Подставленные параметры должны быть в результате
        assert "12.5" in result or "Луна" in result

    @pytest.mark.parametrize(
        "message_key",
        [
            "weight_saved",
            "vaccination_saved",
            "note_saved",
            "pet_created",
            "pet_profile",
            "pet_profile_breed_part",
            "pet_profile_birth_date_part",
            "emergency_profile_allergies",
            "emergency_profile_chronic_conditions",
            "emergency_profile_vet_contact",
            "unknown_command",
            "error_occurred",
        ],
    )
    def test_required_keys_exist(self, message_key: str) -> None:
        """Основные ключи сообщений присутствуют и возвращают непустую строку."""
        from backend.app.agent.i18n import get_message

        result = get_message(message_key)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_key_returns_key_itself(self) -> None:
        """Несуществующий ключ -> возвращает сам ключ."""
        from backend.app.agent.i18n import get_message

        nonexistent_key = "this_key_does_not_exist_xyz"
        result = get_message(nonexistent_key)

        assert result == nonexistent_key

    def test_russian_and_english_differ(self) -> None:
        """Русский и английский тексты для одного ключа различаются."""
        from backend.app.agent.i18n import get_message

        result_ru = get_message("weight_saved", language="ru")
        result_en = get_message("weight_saved", language="en")

        assert result_ru != result_en

    def test_default_language_is_russian(self) -> None:
        """Язык по умолчанию -- русский (параметр language не передан)."""
        from backend.app.agent.i18n import get_message

        result_default = get_message("weight_saved")
        result_ru = get_message("weight_saved", language="ru")

        assert result_default == result_ru
