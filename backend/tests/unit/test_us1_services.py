"""
Тесты сервисов Phase 3 (US1) проекта Luna the Dog.

Покрывает сервисы:
- T026: pet_service (CRUD питомцев, поиск по имени в тексте)
- T027: health_service (вес, вакцинации, медкарты, лекарства, заметки)
- T028: nutrition_service (диеты, записи кормлений)
- T108: EmergencyProfile в health_service (экстренный профиль)
- T109: audit_service (журнал аудита)

Все тесты работают с реальной PostgreSQL через testcontainers.
Каждый тест получает чистую транзакцию через фикстуру db_session.
"""

import datetime
import inspect
from decimal import Decimal

import pytest
from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.family import Family, FamilyMember
from backend.app.db.models.health import (
    EmergencyProfile,
    MedicalRecord,
    Medication,
    Note,
    Vaccination,
    WeightRecord,
)
from backend.app.db.models.nutrition import DietRecord, FeedingEntry
from backend.app.db.models.pet import Pet

# Импорты сервисов, которые будут реализованы.
# До реализации сервисов эти импорты вызовут ImportError — тесты будут "красными".
from backend.app.services.audit_service import get_entity_history, log_change
from backend.app.services.health_service import (
    add_medical_record,
    add_medication,
    add_note,
    add_vaccination,
    add_weight,
    deactivate_medication,
    get_latest_weight,
    get_medical_records,
    get_medications,
    get_notes,
    get_or_create_emergency_profile,
    get_vaccinations,
    get_weight_history,
    update_emergency_profile,
)
from backend.app.services.nutrition_service import (
    add_diet_record,
    add_feeding_entry,
    end_diet_record,
    get_current_diet,
    get_diet_history,
    get_feeding_entries,
)
from backend.app.services.pet_service import (
    create_pet,
    get_family_pets,
    get_pet_by_id,
    get_pet_by_name,
    resolve_pet_from_text,
    update_pet,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Фикстуры
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def family_and_pet(
    db_session: AsyncSession,
) -> tuple[Family, FamilyMember, Pet]:
    """Создаёт Family + FamilyMember + Pet для тестов сервисов."""
    family = Family()
    db_session.add(family)
    await db_session.flush()

    member = FamilyMember(id=111222333, first_name="Тест", family_id=family.id)
    db_session.add(member)
    await db_session.flush()

    pet = Pet(
        name="Луна",
        species="dog",
        family_id=family.id,
        created_by=member.id,
    )
    db_session.add(pet)
    await db_session.flush()

    return family, member, pet


# ═══════════════════════════════════════════════════════════════════════════════
# T026: pet_service
# ═══════════════════════════════════════════════════════════════════════════════


class TestPetService:
    """Тесты pet_service — CRUD и поиск питомцев."""

    # --- create_pet ---

    async def test_create_pet_returns_pet_with_name_and_species(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """create_pet создаёт питомца и пишет audit create с минимальным diff."""
        family, member, _ = family_and_pet

        new_pet = await create_pet(
            db_session,
            family_id=family.id,
            name="Барсик",
            species="cat",
            actor_id=member.id,
        )

        audit_entries = await get_entity_history(
            db_session,
            entity_type="pet",
            entity_id=new_pet.id,
        )

        assert new_pet.name == "Барсик"
        assert new_pet.species == "cat"
        assert new_pet.family_id == family.id
        assert new_pet.id is not None
        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json == {
            "name": "Барсик",
            "species": "cat",
            "family_id": family.id,
            "created_by": member.id,
        }

    async def test_create_pet_with_optional_fields(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """create_pet принимает необязательные поля (breed, birth_date и т.д.)."""
        family, member, _ = family_and_pet

        new_pet = await create_pet(
            db_session,
            family_id=family.id,
            name="Рекс",
            species="dog",
            actor_id=member.id,
            breed="Немецкая овчарка",
            birth_date=datetime.date(2024, 3, 15),
        )

        assert new_pet.breed == "Немецкая овчарка"
        assert new_pet.birth_date == datetime.date(2024, 3, 15)

    async def test_create_pet_requires_actor_id(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """create_pet требует actor_id (или обязательный user-origin идентификатор)."""
        family, _, _ = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await create_pet(
                db_session,
                family_id=family.id,
                name="Тишка",
                species="cat",
            )

    async def test_create_pet_rejects_actor_id_none(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """create_pet не допускает actor_id=None."""
        family, _, _ = family_and_pet

        with pytest.raises(ValueError, match="actor_id"):
            await create_pet(
                db_session,
                family_id=family.id,
                name="Тишка",
                species="cat",
                actor_id=None,
            )

    # --- get_family_pets ---

    async def test_get_family_pets_returns_all_pets(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_family_pets возвращает всех питомцев семьи."""
        family, member, existing_pet = family_and_pet

        # Добавляем второго питомца
        second_pet = Pet(
            name="Мурка",
            species="cat",
            family_id=family.id,
            created_by=member.id,
        )
        db_session.add(second_pet)
        await db_session.flush()

        pets = await get_family_pets(db_session, family.id)

        assert len(pets) == 2
        pet_names = {pet.name for pet in pets}
        assert pet_names == {"Луна", "Мурка"}

    async def test_get_family_pets_returns_empty_for_unknown_family(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_family_pets возвращает пустой список для несуществующей семьи."""
        pets = await get_family_pets(db_session, family_id=99999)

        assert pets == []

    # --- get_pet_by_id ---

    async def test_get_pet_by_id_returns_pet(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_pet_by_id возвращает питомца по ID."""
        _, _, pet = family_and_pet

        found_pet = await get_pet_by_id(db_session, pet.id)

        assert found_pet is not None
        assert found_pet.id == pet.id
        assert found_pet.name == "Луна"

    async def test_get_pet_by_id_returns_none_for_unknown(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_pet_by_id возвращает None для несуществующего ID."""
        found_pet = await get_pet_by_id(db_session, pet_id=99999)

        assert found_pet is None

    # --- get_pet_by_name ---

    async def test_get_pet_by_name_case_insensitive(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_pet_by_name ищет без учёта регистра."""
        family, _, _ = family_and_pet

        found_pet = await get_pet_by_name(db_session, family_id=family.id, name="луна")

        assert found_pet is not None
        assert found_pet.name == "Луна"

    async def test_get_pet_by_name_returns_none_for_unknown(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_pet_by_name возвращает None, если питомец не найден."""
        family, _, _ = family_and_pet

        found_pet = await get_pet_by_name(db_session, family_id=family.id, name="Шарик")

        assert found_pet is None

    # --- resolve_pet_from_text ---

    async def test_resolve_pet_from_text_finds_pet_name_in_sentence(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """resolve_pet_from_text находит имя питомца внутри текста."""
        family, _, _ = family_and_pet

        found_pet = await resolve_pet_from_text(
            db_session,
            family_id=family.id,
            text="Покормите Луну сегодня вечером",
        )

        assert found_pet is not None
        assert found_pet.name == "Луна"

    async def test_resolve_pet_from_text_case_insensitive(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """resolve_pet_from_text работает без учёта регистра."""
        family, _, _ = family_and_pet

        found_pet = await resolve_pet_from_text(
            db_session,
            family_id=family.id,
            text="сегодня луна была активной",
        )

        assert found_pet is not None
        assert found_pet.name == "Луна"

    async def test_resolve_pet_from_text_returns_none_when_no_match(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """resolve_pet_from_text возвращает None, если имя не найдено в тексте."""
        family, _, _ = family_and_pet

        found_pet = await resolve_pet_from_text(
            db_session,
            family_id=family.id,
            text="Отличная погода для прогулки",
        )

        assert found_pet is None

    # --- update_pet ---

    async def test_update_pet_changes_fields(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_pet обновляет поля и пишет audit update только по изменённым полям."""
        _, member, pet = family_and_pet

        updated_pet = await update_pet(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            breed="Лабрадор",
            is_neutered=True,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="pet",
            entity_id=pet.id,
        )

        assert updated_pet.breed == "Лабрадор"
        assert updated_pet.is_neutered is True
        # Имя не должно измениться
        assert updated_pet.name == "Луна"
        assert len(audit_entries) == 1
        assert audit_entries[0].action == "update"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json == {
            "breed": "Лабрадор",
            "is_neutered": True,
        }

    async def test_update_pet_requires_actor_id(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_pet требует actor_id (или обязательный user-origin идентификатор)."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await update_pet(
                db_session,
                pet_id=pet.id,
                breed="Лабрадор",
            )

    async def test_update_pet_rejects_actor_id_none(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_pet не допускает actor_id=None."""
        _, _, pet = family_and_pet

        with pytest.raises(ValueError, match="actor_id"):
            await update_pet(
                db_session,
                pet_id=pet.id,
                actor_id=None,
                breed="Лабрадор",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# T027: health_service — WeightRecord
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthService:
    """Тесты health_service — CRUD записей о здоровье питомца."""

    # --- add_weight / get_weight_history / get_latest_weight ---

    async def test_add_weight_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_weight создаёт запись о весе и возвращает WeightRecord."""
        _, member, pet = family_and_pet

        record = await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("12.50"),
            measured_at=datetime.date(2026, 3, 1),
            recorded_by=member.id,
        )

        assert isinstance(record, WeightRecord)
        assert record.pet_id == pet.id
        assert record.weight_kg == Decimal("12.50")
        assert record.measured_at == datetime.date(2026, 3, 1)
        assert record.id is not None

    async def test_add_weight_requires_actor_origin(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_weight требует actor_id/user-origin (например recorded_by)."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await add_weight(
                db_session,
                pet_id=pet.id,
                weight_kg=Decimal("9.90"),
                measured_at=datetime.date(2026, 3, 1),
            )

    async def test_add_weight_writes_audit_create_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_weight пишет ChangeLog create с actor_id и минимальным diff_json."""
        _, member, pet = family_and_pet

        record = await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("12.50"),
            measured_at=datetime.date(2026, 3, 1),
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="weight_record",
            entity_id=record.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {
            "pet_id",
            "weight_kg",
            "measured_at",
            "recorded_by",
        }
        assert audit_entries[0].diff_json["pet_id"] == pet.id
        assert str(audit_entries[0].diff_json["weight_kg"]) == "12.50"
        assert audit_entries[0].diff_json["measured_at"] == "2026-03-01"
        assert audit_entries[0].diff_json["recorded_by"] == member.id

    async def test_get_weight_history_sorted_desc(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_weight_history возвращает записи, отсортированные по measured_at desc."""
        _, member, pet = family_and_pet

        await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("11.00"),
            measured_at=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("12.00"),
            measured_at=datetime.date(2026, 3, 1),
            recorded_by=member.id,
        )
        await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("11.50"),
            measured_at=datetime.date(2026, 2, 1),
            recorded_by=member.id,
        )

        history = await get_weight_history(db_session, pet_id=pet.id)

        assert len(history) == 3
        # Первая запись — самая свежая (2026-03-01)
        assert history[0].measured_at == datetime.date(2026, 3, 1)
        assert history[1].measured_at == datetime.date(2026, 2, 1)
        assert history[2].measured_at == datetime.date(2026, 1, 1)

    async def test_get_weight_history_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_weight_history возвращает пустой список, если записей нет."""
        _, _, pet = family_and_pet

        history = await get_weight_history(db_session, pet_id=pet.id)

        assert history == []

    async def test_get_latest_weight_returns_most_recent(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_latest_weight возвращает самую свежую запись о весе."""
        _, member, pet = family_and_pet

        await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("11.00"),
            measured_at=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        await add_weight(
            db_session,
            pet_id=pet.id,
            weight_kg=Decimal("12.50"),
            measured_at=datetime.date(2026, 3, 1),
            recorded_by=member.id,
        )

        latest = await get_latest_weight(db_session, pet_id=pet.id)

        assert latest is not None
        assert latest.weight_kg == Decimal("12.50")
        assert latest.measured_at == datetime.date(2026, 3, 1)

    async def test_get_latest_weight_returns_none_when_no_records(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_latest_weight возвращает None, если записей о весе нет."""
        _, _, pet = family_and_pet

        latest = await get_latest_weight(db_session, pet_id=pet.id)

        assert latest is None

    # --- add_vaccination / get_vaccinations ---

    async def test_add_vaccination_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_vaccination создаёт запись о вакцинации."""
        _, member, pet = family_and_pet
        today = datetime.date.today()

        vaccination = await add_vaccination(
            db_session,
            pet_id=pet.id,
            vaccine_name="Нобивак DHPPi",
            date=today,
            next_date=today.replace(year=today.year + 1),
            vet_name="Клиника Друг",
            recorded_by=member.id,
        )

        assert isinstance(vaccination, Vaccination)
        assert vaccination.vaccine_name == "Нобивак DHPPi"
        assert vaccination.vet_name == "Клиника Друг"
        assert vaccination.id is not None

    async def test_add_vaccination_requires_actor_origin(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_vaccination требует actor_id/user-origin (например recorded_by)."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await add_vaccination(
                db_session,
                pet_id=pet.id,
                vaccine_name="Рабикан",
                date=datetime.date(2026, 3, 1),
            )

    async def test_add_vaccination_writes_audit_create_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_vaccination пишет ChangeLog create с actor_id и минимальным diff_json."""
        _, member, pet = family_and_pet

        vaccination = await add_vaccination(
            db_session,
            pet_id=pet.id,
            vaccine_name="Нобивак DHPPi",
            date=datetime.date(2026, 3, 1),
            next_date=datetime.date(2027, 3, 1),
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="vaccination",
            entity_id=vaccination.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {
            "pet_id",
            "vaccine_name",
            "date",
            "next_date",
            "recorded_by",
        }
        assert audit_entries[0].diff_json["pet_id"] == pet.id
        assert audit_entries[0].diff_json["vaccine_name"] == "Нобивак DHPPi"
        assert audit_entries[0].diff_json["date"] == "2026-03-01"
        assert audit_entries[0].diff_json["next_date"] == "2027-03-01"
        assert audit_entries[0].diff_json["recorded_by"] == member.id

    async def test_get_vaccinations_returns_all_for_pet(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_vaccinations возвращает все вакцинации питомца."""
        _, member, pet = family_and_pet

        await add_vaccination(
            db_session,
            pet_id=pet.id,
            vaccine_name="Нобивак DHPPi",
            date=datetime.date(2026, 1, 15),
            recorded_by=member.id,
        )
        await add_vaccination(
            db_session,
            pet_id=pet.id,
            vaccine_name="Рабикан",
            date=datetime.date(2026, 2, 20),
            recorded_by=member.id,
        )

        vaccinations = await get_vaccinations(db_session, pet_id=pet.id)

        assert len(vaccinations) == 2

    async def test_get_vaccinations_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_vaccinations возвращает пустой список, если вакцинаций нет."""
        _, _, pet = family_and_pet

        vaccinations = await get_vaccinations(db_session, pet_id=pet.id)

        assert vaccinations == []

    # --- add_medical_record / get_medical_records ---

    async def test_add_medical_record_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_medical_record создаёт медицинскую запись."""
        _, member, pet = family_and_pet

        record = await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="illness",
            title="Аллергия на курицу",
            date=datetime.date(2026, 2, 10),
            description="Зуд и покраснение кожи",
            recorded_by=member.id,
        )

        assert isinstance(record, MedicalRecord)
        assert record.record_type == "illness"
        assert record.title == "Аллергия на курицу"
        assert record.id is not None

    async def test_add_medical_record_requires_recorded_by(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_medical_record требует обязательный recorded_by."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError), match="recorded_by"):
            await add_medical_record(
                db_session,
                pet_id=pet.id,
                record_type="illness",
                title="Без автора",
                date=datetime.date(2026, 2, 11),
            )

    async def test_add_medical_record_writes_audit_create_json_safe_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_medical_record пишет audit create с JSON-safe diff_json."""
        _, member, pet = family_and_pet

        record = await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="checkup",
            title="Плановый осмотр",
            date=datetime.date(2026, 2, 10),
            description="Все показатели в норме",
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="medical_record",
            entity_id=record.id,
        )

        assert audit_entries
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert {"pet_id", "record_type", "title", "date", "recorded_by"} <= set(
            audit_entries[0].diff_json.keys()
        )
        assert audit_entries[0].diff_json["date"] == "2026-02-10"

    async def test_get_medical_records_filter_by_record_type(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medical_records фильтрует записи по record_type."""
        _, member, pet = family_and_pet

        await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="illness",
            title="Аллергия",
            date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="checkup",
            title="Плановый осмотр",
            date=datetime.date(2026, 2, 1),
            recorded_by=member.id,
        )
        await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="illness",
            title="Отит",
            date=datetime.date(2026, 3, 1),
            recorded_by=member.id,
        )

        illness_records = await get_medical_records(
            db_session, pet_id=pet.id, record_type="illness"
        )

        assert len(illness_records) == 2
        for record in illness_records:
            assert record.record_type == "illness"

    async def test_get_medical_records_active_only(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medical_records(active_only=True) возвращает только незакрытые записи."""
        _, member, pet = family_and_pet

        # Активная запись (resolved_date = None)
        await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="illness",
            title="Хронический дерматит",
            date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        # Закрытая запись (resolved_date установлена)
        closed_record = await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="illness",
            title="Простуда",
            date=datetime.date(2026, 2, 1),
            recorded_by=member.id,
        )
        closed_record.resolved_date = datetime.date(2026, 2, 10)
        await db_session.flush()

        active_records = await get_medical_records(
            db_session, pet_id=pet.id, active_only=True
        )

        assert len(active_records) == 1
        assert active_records[0].title == "Хронический дерматит"

    async def test_get_medical_records_all_without_filter(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medical_records без фильтров возвращает все записи питомца."""
        _, member, pet = family_and_pet

        await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="illness",
            title="Аллергия",
            date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        await add_medical_record(
            db_session,
            pet_id=pet.id,
            record_type="checkup",
            title="Осмотр",
            date=datetime.date(2026, 2, 1),
            recorded_by=member.id,
        )

        all_records = await get_medical_records(db_session, pet_id=pet.id)

        assert len(all_records) == 2

    async def test_get_medical_records_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medical_records возвращает пустой список, если записей нет."""
        _, _, pet = family_and_pet

        records = await get_medical_records(db_session, pet_id=pet.id)

        assert records == []

    # --- add_medication / get_medications / deactivate_medication ---

    async def test_add_medication_creates_active_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_medication создаёт активный препарат."""
        _, member, pet = family_and_pet

        medication = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Бравекто",
            start_date=datetime.date(2026, 1, 1),
            dosage="500мг",
            recorded_by=member.id,
        )

        assert isinstance(medication, Medication)
        assert medication.name == "Бравекто"
        assert medication.is_active is True
        assert medication.id is not None

    async def test_add_medication_requires_actor_origin(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_medication требует actor_id/user-origin (например recorded_by)."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await add_medication(
                db_session,
                pet_id=pet.id,
                name="Бравекто",
                start_date=datetime.date(2026, 1, 1),
            )

    async def test_add_medication_writes_audit_create_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_medication пишет ChangeLog create с actor_id и минимальным diff_json."""
        _, member, pet = family_and_pet

        medication = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Бравекто",
            start_date=datetime.date(2026, 1, 1),
            dosage="500мг",
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="medication",
            entity_id=medication.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {
            "pet_id",
            "name",
            "start_date",
            "dosage",
            "recorded_by",
        }
        assert audit_entries[0].diff_json["pet_id"] == pet.id
        assert audit_entries[0].diff_json["name"] == "Бравекто"
        assert audit_entries[0].diff_json["start_date"] == "2026-01-01"
        assert audit_entries[0].diff_json["dosage"] == "500мг"
        assert audit_entries[0].diff_json["recorded_by"] == member.id

    async def test_get_medications_active_only(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medications с active_only=True возвращает только активные препараты."""
        _, member, pet = family_and_pet

        await add_medication(
            db_session,
            pet_id=pet.id,
            name="Бравекто",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        inactive_medication = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Старый препарат",
            start_date=datetime.date(2025, 1, 1),
            recorded_by=member.id,
        )
        await deactivate_medication(
            db_session,
            medication_id=inactive_medication.id,
            actor_id=member.id,
        )

        active_medications = await get_medications(
            db_session, pet_id=pet.id, active_only=True
        )

        assert len(active_medications) == 1
        assert active_medications[0].name == "Бравекто"

    async def test_get_medications_all(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medications без active_only возвращает все препараты."""
        _, member, pet = family_and_pet

        await add_medication(
            db_session,
            pet_id=pet.id,
            name="Бравекто",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        medication_to_deactivate = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Старый препарат",
            start_date=datetime.date(2025, 1, 1),
            recorded_by=member.id,
        )
        await deactivate_medication(
            db_session,
            medication_id=medication_to_deactivate.id,
            actor_id=member.id,
        )

        all_medications = await get_medications(
            db_session, pet_id=pet.id, active_only=False
        )

        assert len(all_medications) == 2

    async def test_deactivate_medication_sets_inactive(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """deactivate_medication устанавливает is_active=False."""
        _, member, pet = family_and_pet

        medication = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Бравекто",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )

        deactivated = await deactivate_medication(
            db_session,
            medication_id=medication.id,
            actor_id=member.id,
        )

        assert deactivated.is_active is False

    async def test_deactivate_medication_requires_actor_id(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """deactivate_medication требует actor_id для операции закрытия."""
        _, member, pet = family_and_pet

        medication = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Бравекто",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )

        with pytest.raises((TypeError, ValueError)):
            await deactivate_medication(db_session, medication_id=medication.id)

    async def test_deactivate_medication_writes_audit_close_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """deactivate_medication пишет ChangeLog close с actor_id и diff close."""
        _, member, pet = family_and_pet

        medication = await add_medication(
            db_session,
            pet_id=pet.id,
            name="Симпарика",
            start_date=datetime.date(2026, 2, 1),
            recorded_by=member.id,
        )
        await deactivate_medication(
            db_session,
            medication_id=medication.id,
            actor_id=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="medication",
            entity_id=medication.id,
        )
        close_entries = [entry for entry in audit_entries if entry.action == "close"]

        assert close_entries
        assert close_entries[0].actor_id == member.id
        assert close_entries[0].diff_json is not None
        assert set(close_entries[0].diff_json.keys()) == {"is_active", "end_date"}
        assert close_entries[0].diff_json["is_active"] is False
        assert close_entries[0].diff_json["end_date"] is not None

    async def test_get_medications_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_medications возвращает пустой список, если препаратов нет."""
        _, _, pet = family_and_pet

        medications = await get_medications(db_session, pet_id=pet.id)

        assert medications == []

    # --- add_note / get_notes ---

    async def test_add_note_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_note создаёт заметку о питомце."""
        _, member, pet = family_and_pet

        note = await add_note(
            db_session,
            pet_id=pet.id,
            content="Луна сегодня была очень активной",
            recorded_by=member.id,
        )

        assert isinstance(note, Note)
        assert note.content == "Луна сегодня была очень активной"
        assert note.id is not None

    async def test_add_note_requires_actor_origin(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_note требует actor_id/user-origin (например recorded_by)."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await add_note(
                db_session,
                pet_id=pet.id,
                content="Без автора нельзя",
            )

    async def test_add_note_writes_audit_create_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_note пишет ChangeLog create с actor_id и минимальным diff_json."""
        _, member, pet = family_and_pet

        note = await add_note(
            db_session,
            pet_id=pet.id,
            content="Проверка аудита заметки",
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="note",
            entity_id=note.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {
            "pet_id",
            "content",
            "recorded_by",
        }
        assert audit_entries[0].diff_json["pet_id"] == pet.id
        assert audit_entries[0].diff_json["content"] == "Проверка аудита заметки"
        assert audit_entries[0].diff_json["recorded_by"] == member.id

    async def test_get_notes_with_limit(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_notes с limit ограничивает количество возвращаемых записей."""
        _, member, pet = family_and_pet

        # Создаём 5 заметок
        for i in range(5):
            await add_note(
                db_session,
                pet_id=pet.id,
                content=f"Заметка #{i + 1}",
                recorded_by=member.id,
            )

        notes = await get_notes(db_session, pet_id=pet.id, limit=3)

        assert len(notes) == 3

    async def test_get_notes_with_offset(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_notes с offset пропускает указанное количество записей."""
        _, member, pet = family_and_pet

        # Создаём 5 заметок
        for i in range(5):
            await add_note(
                db_session,
                pet_id=pet.id,
                content=f"Заметка #{i + 1}",
                recorded_by=member.id,
            )

        # Пропускаем первые 3 записи, берём следующие
        notes_with_offset = await get_notes(
            db_session, pet_id=pet.id, limit=20, offset=3
        )

        assert len(notes_with_offset) == 2

    async def test_get_notes_default_limit(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_notes с limit по умолчанию (20) возвращает не более 20 записей."""
        _, member, pet = family_and_pet

        # Создаём 3 заметки — все должны вернуться
        for i in range(3):
            await add_note(
                db_session,
                pet_id=pet.id,
                content=f"Заметка #{i + 1}",
                recorded_by=member.id,
            )

        notes = await get_notes(db_session, pet_id=pet.id)

        assert len(notes) == 3

    async def test_get_notes_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_notes возвращает пустой список, если заметок нет."""
        _, _, pet = family_and_pet

        notes = await get_notes(db_session, pet_id=pet.id)

        assert notes == []


# ═══════════════════════════════════════════════════════════════════════════════
# T028: nutrition_service
# ═══════════════════════════════════════════════════════════════════════════════


class TestNutritionService:
    """Тесты nutrition_service — диеты и записи кормлений."""

    # --- add_diet_record / get_diet_history / get_current_diet / end_diet_record ---

    async def test_add_diet_record_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_diet_record создаёт запись о диете."""
        _, member, pet = family_and_pet

        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin Medium Adult",
            start_date=datetime.date(2026, 1, 1),
            food_type="dry",
            recorded_by=member.id,
        )

        assert isinstance(diet, DietRecord)
        assert diet.food_brand == "Royal Canin Medium Adult"
        assert diet.food_type == "dry"
        assert diet.id is not None

    async def test_add_diet_record_closes_previous_open_diet(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """Новая диета закрывает предыдущую открытую end_date=new_start_date."""
        _, member, pet = family_and_pet
        new_start_date = datetime.date(2026, 2, 15)

        old_diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Старый рацион",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        new_diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Новый рацион",
            start_date=new_start_date,
            recorded_by=member.id,
        )
        await db_session.refresh(old_diet)

        assert old_diet.end_date == new_start_date
        assert new_diet.start_date == new_start_date

    async def test_add_diet_record_requires_actor_origin(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_diet_record требует actor_id/user-origin (recorded_by)."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await add_diet_record(
                db_session,
                pet_id=pet.id,
                food_brand="Royal Canin",
                start_date=datetime.date(2026, 1, 1),
            )

    async def test_add_diet_record_rejects_recorded_by_none(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_diet_record не допускает recorded_by=None."""
        _, _, pet = family_and_pet

        with pytest.raises(ValueError, match="recorded_by"):
            await add_diet_record(
                db_session,
                pet_id=pet.id,
                food_brand="Royal Canin",
                start_date=datetime.date(2026, 1, 1),
                recorded_by=None,
            )

    async def test_add_diet_record_rejects_backdated_start_before_open_diet(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """Новая диета раньше start_date открытой записи даёт доменную ошибку."""
        _, member, pet = family_and_pet

        await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Текущий рацион",
            start_date=datetime.date(2026, 3, 10),
            recorded_by=member.id,
        )

        with pytest.raises(ValueError, match="start_date|раньше|хронолог"):
            await add_diet_record(
                db_session,
                pet_id=pet.id,
                food_brand="Старый рацион",
                start_date=datetime.date(2026, 3, 1),
                recorded_by=member.id,
            )

    async def test_add_diet_record_writes_audit_create_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_diet_record пишет ChangeLog create с actor_id и минимальным diff_json."""
        _, member, pet = family_and_pet

        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Acana",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="diet_record",
            entity_id=diet.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {
            "pet_id",
            "food_brand",
            "start_date",
            "recorded_by",
        }
        assert audit_entries[0].diff_json["pet_id"] == pet.id
        assert audit_entries[0].diff_json["food_brand"] == "Acana"
        assert audit_entries[0].diff_json["start_date"] == "2026-01-01"
        assert audit_entries[0].diff_json["recorded_by"] == member.id

    async def test_get_diet_history_sorted_desc(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_diet_history возвращает диеты, отсортированные по start_date desc."""
        _, member, pet = family_and_pet

        await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin",
            start_date=datetime.date(2025, 6, 1),
            recorded_by=member.id,
        )
        await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Orijen",
            start_date=datetime.date(2025, 9, 1),
            recorded_by=member.id,
        )
        await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Acana",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )

        history = await get_diet_history(db_session, pet_id=pet.id)

        assert len(history) == 3
        # Первая запись — самая свежая (2026-01-01)
        assert history[0].food_brand == "Acana"
        assert history[1].food_brand == "Orijen"
        assert history[2].food_brand == "Royal Canin"

    async def test_get_diet_history_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_diet_history возвращает пустой список, если диет нет."""
        _, _, pet = family_and_pet

        history = await get_diet_history(db_session, pet_id=pet.id)

        assert history == []

    async def test_get_current_diet_returns_active_diet(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_current_diet возвращает диету с end_date IS NULL."""
        _, member, pet = family_and_pet

        # Закрытая диета (end_date установлен)
        closed_diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin",
            start_date=datetime.date(2025, 1, 1),
            recorded_by=member.id,
        )
        await end_diet_record(
            db_session,
            diet_record_id=closed_diet.id,
            end_date=datetime.date(2025, 12, 31),
            actor_id=member.id,
        )

        # Текущая диета (end_date = None)
        await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Acana",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )

        current = await get_current_diet(db_session, pet_id=pet.id)

        assert current is not None
        assert current.food_brand == "Acana"
        assert current.end_date is None

    async def test_get_current_diet_returns_latest_open_for_dirty_data(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """При нескольких открытых диетах возвращается самая свежая, без падения."""
        _, member, pet = family_and_pet

        older_open = DietRecord(
            pet_id=pet.id,
            food_brand="Старый открытый рацион",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        newest_open = DietRecord(
            pet_id=pet.id,
            food_brand="Свежий открытый рацион",
            start_date=datetime.date(2026, 2, 1),
            recorded_by=member.id,
        )
        db_session.add_all([older_open, newest_open])
        await db_session.flush()

        current = await get_current_diet(db_session, pet_id=pet.id)

        assert current is not None
        assert current.id == newest_open.id
        assert current.food_brand == "Свежий открытый рацион"

    async def test_get_current_diet_returns_none_when_all_closed(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_current_diet возвращает None, если все диеты закрыты."""
        _, member, pet = family_and_pet

        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin",
            start_date=datetime.date(2025, 1, 1),
            recorded_by=member.id,
        )
        await end_diet_record(
            db_session,
            diet_record_id=diet.id,
            end_date=datetime.date(2025, 12, 31),
            actor_id=member.id,
        )

        current = await get_current_diet(db_session, pet_id=pet.id)

        assert current is None

    async def test_end_diet_record_sets_end_date(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """end_diet_record устанавливает end_date для записи о диете."""
        _, member, pet = family_and_pet
        end_date = datetime.date(2026, 3, 1)

        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )

        closed_diet = await end_diet_record(
            db_session,
            diet_record_id=diet.id,
            end_date=end_date,
            actor_id=member.id,
        )

        assert closed_diet.end_date == end_date

    async def test_end_diet_record_rejects_end_date_before_start_date(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """end_diet_record отклоняет end_date раньше start_date."""
        _, member, pet = family_and_pet
        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 1, 15),
            recorded_by=member.id,
        )

        with pytest.raises(ValueError, match="end_date"):
            await end_diet_record(
                db_session,
                diet_record_id=diet.id,
                end_date=datetime.date(2026, 1, 1),
                actor_id=member.id,
            )

    async def test_end_diet_record_requires_actor_id(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """end_diet_record требует actor_id/user-origin."""
        _, member, pet = family_and_pet

        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Royal Canin",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )

        with pytest.raises((TypeError, ValueError)):
            await end_diet_record(
                db_session,
                diet_record_id=diet.id,
                end_date=datetime.date(2026, 3, 1),
            )

    async def test_end_diet_record_writes_close_audit_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """end_diet_record пишет ChangeLog close с actor_id и minimal diff_json."""
        _, member, pet = family_and_pet

        diet = await add_diet_record(
            db_session,
            pet_id=pet.id,
            food_brand="Farmina",
            start_date=datetime.date(2026, 1, 1),
            recorded_by=member.id,
        )
        await end_diet_record(
            db_session,
            diet_record_id=diet.id,
            end_date=datetime.date(2026, 2, 1),
            actor_id=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="diet_record",
            entity_id=diet.id,
        )
        close_entries = [entry for entry in audit_entries if entry.action == "close"]

        assert close_entries
        assert close_entries[0].actor_id == member.id
        assert close_entries[0].diff_json is not None
        assert set(close_entries[0].diff_json.keys()) == {"end_date"}
        assert close_entries[0].diff_json["end_date"] == "2026-02-01"

    # --- add_feeding_entry / get_feeding_entries ---

    async def test_add_feeding_entry_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_feeding_entry создаёт запись о кормлении."""
        _, member, pet = family_and_pet
        now = datetime.datetime.now(tz=datetime.UTC)

        entry = await add_feeding_entry(
            db_session,
            pet_id=pet.id,
            fed_at=now,
            food_description="Сухой корм Royal Canin, 200г",
            portion_size="200г",
            recorded_by=member.id,
        )

        assert isinstance(entry, FeedingEntry)
        assert entry.food_description == "Сухой корм Royal Canin, 200г"
        assert entry.id is not None

    async def test_add_feeding_entry_requires_actor_origin(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_feeding_entry требует recorded_by и не допускает silent write."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await add_feeding_entry(
                db_session,
                pet_id=pet.id,
                fed_at=datetime.datetime(2026, 3, 8, 8, 0, tzinfo=datetime.UTC),
                food_description="Корм без автора",
            )

    async def test_add_feeding_entry_writes_audit_create_with_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """add_feeding_entry пишет ChangeLog create с JSON-safe минимальным diff."""
        _, member, pet = family_and_pet
        feeding_time = datetime.datetime(2026, 3, 8, 8, 30, tzinfo=datetime.UTC)

        entry = await add_feeding_entry(
            db_session,
            pet_id=pet.id,
            fed_at=feeding_time,
            food_description="Acana 50г",
            portion_size="50г",
            recorded_by=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="feeding_entry",
            entity_id=entry.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {
            "pet_id",
            "fed_at",
            "food_description",
            "recorded_by",
        }
        assert audit_entries[0].diff_json["pet_id"] == pet.id
        assert audit_entries[0].diff_json["fed_at"] == "2026-03-08T08:30:00+00:00"
        assert audit_entries[0].diff_json["food_description"] == "Acana 50г"
        assert audit_entries[0].diff_json["recorded_by"] == member.id

    async def test_get_feeding_entries_sorted_desc(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_feeding_entries возвращает записи, отсортированные по fed_at desc."""
        _, member, pet = family_and_pet
        base_time = datetime.datetime(2026, 3, 1, 8, 0, tzinfo=datetime.UTC)

        await add_feeding_entry(
            db_session,
            pet_id=pet.id,
            fed_at=base_time,
            food_description="Утренний корм",
            recorded_by=member.id,
        )
        await add_feeding_entry(
            db_session,
            pet_id=pet.id,
            fed_at=base_time + datetime.timedelta(hours=12),
            food_description="Вечерний корм",
            recorded_by=member.id,
        )
        await add_feeding_entry(
            db_session,
            pet_id=pet.id,
            fed_at=base_time + datetime.timedelta(hours=6),
            food_description="Дневной корм",
            recorded_by=member.id,
        )

        entries = await get_feeding_entries(db_session, pet_id=pet.id)

        assert len(entries) == 3
        # Первая запись — самая свежая (вечерний корм)
        assert entries[0].food_description == "Вечерний корм"
        assert entries[1].food_description == "Дневной корм"
        assert entries[2].food_description == "Утренний корм"

    async def test_get_feeding_entries_with_limit(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_feeding_entries с limit ограничивает количество записей."""
        _, member, pet = family_and_pet
        base_time = datetime.datetime(2026, 3, 1, 8, 0, tzinfo=datetime.UTC)

        for i in range(5):
            await add_feeding_entry(
                db_session,
                pet_id=pet.id,
                fed_at=base_time + datetime.timedelta(hours=i),
                food_description=f"Корм #{i + 1}",
                recorded_by=member.id,
            )

        entries = await get_feeding_entries(db_session, pet_id=pet.id, limit=3)

        assert len(entries) == 3

    async def test_get_feeding_entries_empty(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_feeding_entries возвращает пустой список, если записей нет."""
        _, _, pet = family_and_pet

        entries = await get_feeding_entries(db_session, pet_id=pet.id)

        assert entries == []


# ═══════════════════════════════════════════════════════════════════════════════
# T108: EmergencyProfile в health_service
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmergencyProfileService:
    """Тесты get_or_create_emergency_profile / update_emergency_profile."""

    async def test_get_or_create_creates_new_profile(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_or_create_emergency_profile создаёт профиль, если его нет."""
        _, member, pet = family_and_pet

        profile = await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        assert isinstance(profile, EmergencyProfile)
        assert profile.pet_id == pet.id
        assert profile.id is not None

    async def test_get_or_create_autocreate_writes_audit_create(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """auto-create через get_or_create пишет ChangeLog create emergency_profile."""
        _, member, pet = family_and_pet

        profile = await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="emergency_profile",
            entity_id=profile.id,
        )

        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"
        assert audit_entries[0].actor_id == member.id
        assert audit_entries[0].diff_json is not None
        assert set(audit_entries[0].diff_json.keys()) == {"pet_id"}
        assert audit_entries[0].diff_json["pet_id"] == pet.id

    async def test_get_or_create_returns_existing_profile(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_or_create_emergency_profile возвращает существующий профиль."""
        _, member, pet = family_and_pet

        first_profile = await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )
        second_profile = await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        assert first_profile.id == second_profile.id

    async def test_update_emergency_profile_sets_fields(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_emergency_profile обновляет указанные поля профиля."""
        _, member, pet = family_and_pet

        # Сначала создаём профиль
        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        updated_profile = await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            allergies="Курица, говядина",
            chronic_conditions="Атопический дерматит",
            vet_contact="Клиника Друг, +7-999-123-45-67",
            blood_type="DEA 1.1+",
        )

        assert updated_profile.allergies == "Курица, говядина"
        assert updated_profile.chronic_conditions == "Атопический дерматит"
        assert updated_profile.vet_contact == "Клиника Друг, +7-999-123-45-67"
        assert updated_profile.blood_type == "DEA 1.1+"

    async def test_update_emergency_profile_partial_update(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_emergency_profile обновляет только указанные поля."""
        _, member, pet = family_and_pet

        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        # Первое обновление — аллергии
        await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            allergies="Курица",
        )

        # Второе обновление — вес (аллергии не должны сброситься)
        updated_profile = await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            latest_weight_snapshot=Decimal("12.50"),
        )

        assert updated_profile.allergies == "Курица"
        assert updated_profile.latest_weight_snapshot == Decimal("12.50")

    @pytest.mark.parametrize("invalid_vet_contact", ["", "   ", "???###"])
    async def test_update_emergency_profile_rejects_invalid_vet_contact(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
        invalid_vet_contact: str,
    ) -> None:
        """update_emergency_profile отклоняет пустой и мусорный vet_contact."""
        _, member, pet = family_and_pet
        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        with pytest.raises(ValueError, match="vet_contact"):
            await update_emergency_profile(
                db_session,
                pet_id=pet.id,
                actor_id=member.id,
                vet_contact=invalid_vet_contact,
            )

    async def test_update_emergency_profile_invalid_payload_has_no_side_effects(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """Невалидный payload не создаёт EmergencyProfile и ChangeLog."""
        _, member, pet = family_and_pet

        with pytest.raises(ValueError, match="vet_contact"):
            await update_emergency_profile(
                db_session,
                pet_id=pet.id,
                actor_id=member.id,
                vet_contact="???###",
            )

        profile_result = await db_session.execute(
            select(EmergencyProfile).where(EmergencyProfile.pet_id == pet.id)
        )
        changelog_result = await db_session.execute(
            select(ChangeLog).where(ChangeLog.entity_type == "emergency_profile")
        )

        assert profile_result.scalar_one_or_none() is None
        assert changelog_result.scalars().all() == []

    async def test_update_emergency_profile_normalizes_blood_type(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_emergency_profile мягко нормализует blood_type."""
        _, member, pet = family_and_pet
        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        updated_profile = await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            blood_type="  dea 1.1+  ",
        )

        assert updated_profile.blood_type == "DEA 1.1+"

    @pytest.mark.parametrize("nullable_blood_type", ["unknown", " null "])
    async def test_update_emergency_profile_blood_type_supports_null_unknown(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
        nullable_blood_type: str,
    ) -> None:
        """blood_type принимает unknown/null и сохраняет как None."""
        _, member, pet = family_and_pet
        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        updated_profile = await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            blood_type=nullable_blood_type,
        )

        assert updated_profile.blood_type is None

    @pytest.mark.parametrize("invalid_blood_type", ["", "   ", "not-a-blood-type"])
    async def test_update_emergency_profile_rejects_invalid_blood_type(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
        invalid_blood_type: str,
    ) -> None:
        """blood_type отклоняет пустые и нераспознаваемые значения."""
        _, member, pet = family_and_pet
        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        with pytest.raises(ValueError, match="blood_type"):
            await update_emergency_profile(
                db_session,
                pet_id=pet.id,
                actor_id=member.id,
                blood_type=invalid_blood_type,
            )

    async def test_update_emergency_profile_nullable_sos_fields_accept_sentinels(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """nullable SOS-поля принимают unknown/null как None."""
        _, member, pet = family_and_pet
        await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )

        updated_profile = await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            allergies="unknown",
            chronic_conditions=" null ",
            vet_contact="UNKNOWN",
        )

        assert updated_profile.allergies is None
        assert updated_profile.chronic_conditions is None
        assert updated_profile.vet_contact is None

    async def test_update_emergency_profile_requires_actor_id(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_emergency_profile требует actor_id для мутации профиля."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await update_emergency_profile(
                db_session,
                pet_id=pet.id,
                allergies="Курица",
            )

    async def test_update_emergency_profile_writes_audit_update_minimal_diff(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """update_emergency_profile пишет ChangeLog update по изменённым полям."""
        _, member, pet = family_and_pet

        profile = await get_or_create_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
        )
        await update_emergency_profile(
            db_session,
            pet_id=pet.id,
            actor_id=member.id,
            allergies="Курица",
            blood_type="DEA 1.1+",
        )
        audit_entries = await get_entity_history(
            db_session,
            entity_type="emergency_profile",
            entity_id=profile.id,
        )
        update_entries = [entry for entry in audit_entries if entry.action == "update"]

        assert update_entries
        assert update_entries[0].actor_id == member.id
        assert update_entries[0].diff_json == {
            "allergies": "Курица",
            "blood_type": "DEA 1.1+",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# T109: audit_service
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditService:
    """Тесты audit_service — журнал аудита изменений."""

    async def test_log_change_creates_record(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """log_change создаёт запись и сохраняет diff_json без преобразований."""
        _, member, pet = family_and_pet
        diff_payload = {
            "field": "name",
            "old": "Луна",
            "new": "Луна-2",
            "meta": {"source": "ui", "tags": ["rename", "manual"]},
            "nullable": None,
        }

        entry = await log_change(
            db_session,
            entity_type="pet",
            entity_id=pet.id,
            action="create",
            actor_id=member.id,
            diff_json=diff_payload,
        )

        assert isinstance(entry, ChangeLog)
        assert entry.entity_type == "pet"
        assert entry.entity_id == pet.id
        assert entry.action == "create"
        assert entry.actor_id == member.id
        assert entry.diff_json == diff_payload
        assert entry.id is not None

    async def test_log_change_requires_actor_id(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """log_change требует actor_id и не принимает вызов без автора."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await log_change(
                db_session,
                entity_type="pet",
                entity_id=pet.id,
                action="update",
            )

    async def test_log_change_rejects_actor_id_none(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """log_change не допускает actor_id=None, чтобы не писать NULL в аудит."""
        _, _, pet = family_and_pet

        with pytest.raises((TypeError, ValueError)):
            await log_change(
                db_session,
                entity_type="pet",
                entity_id=pet.id,
                action="update",
                actor_id=None,
            )

    def test_log_change_signature_requires_actor_id(self) -> None:
        """log_change объявляет actor_id обязательным параметром без default."""
        actor_parameter = inspect.signature(log_change).parameters["actor_id"]

        assert actor_parameter.default is inspect.Signature.empty
        assert str(actor_parameter.annotation) == "int"

    async def test_log_change_rejects_actor_id_bool(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """log_change не принимает bool как actor_id, чтобы не путать с int."""
        _, _, pet = family_and_pet

        with pytest.raises(TypeError, match="actor_id"):
            await log_change(
                db_session,
                entity_type="pet",
                entity_id=pet.id,
                action="update",
                actor_id=True,
            )

    async def test_get_entity_history_sorted_desc(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_entity_history возвращает записи, отсортированные по changed_at desc."""
        _, member, pet = family_and_pet

        first_entry = await log_change(
            db_session,
            entity_type="pet",
            entity_id=pet.id,
            action="create",
            actor_id=member.id,
        )
        second_entry = await log_change(
            db_session,
            entity_type="pet",
            entity_id=pet.id,
            action="update",
            actor_id=member.id,
            diff_json={"breed": "Лабрадор"},
        )

        history = await get_entity_history(
            db_session, entity_type="pet", entity_id=pet.id
        )

        assert len(history) == 2
        # Первая запись — самая свежая (update)
        assert history[0].id == second_entry.id
        assert history[0].action == "update"
        assert history[1].id == first_entry.id
        assert history[1].action == "create"

    async def test_get_entity_history_empty(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_entity_history возвращает пустой список для сущности без истории."""
        history = await get_entity_history(
            db_session, entity_type="pet", entity_id=99999
        )

        assert history == []

    async def test_get_entity_history_filters_by_entity(
        self,
        db_session: AsyncSession,
        family_and_pet: tuple[Family, FamilyMember, Pet],
    ) -> None:
        """get_entity_history возвращает записи только для указанной сущности."""
        _, member, pet = family_and_pet

        # Запись для pet
        await log_change(
            db_session,
            entity_type="pet",
            entity_id=pet.id,
            action="create",
            actor_id=member.id,
        )
        # Запись для другой сущности (vaccination с другим entity_id)
        await log_change(
            db_session,
            entity_type="vaccination",
            entity_id=999,
            action="create",
            actor_id=member.id,
        )

        pet_history = await get_entity_history(
            db_session, entity_type="pet", entity_id=pet.id
        )

        assert len(pet_history) == 1
        assert pet_history[0].entity_type == "pet"
