"""
Тесты моделей SQLAlchemy Phase 3 (US1) проекта Luna the Dog.

Покрывает новые модели здоровья, питания, диалога и экстренного профиля:
- WeightRecord (запись о весе)
- Vaccination (вакцинация)
- MedicalRecord (медицинская запись)
- Medication (лекарство)
- Note (заметка)
- DietRecord (запись о диете)
- FeedingEntry (запись кормления)
- ConversationState (состояние диалога)
- EmergencyProfile (экстренный профиль)

Для каждой модели проверяется:
1. Создание экземпляра с обязательными полями
2. Значения по умолчанию (defaults)
3. Имя таблицы (__tablename__)
4. Создание без nullable-полей (только обязательные)
5. Наличие composite индексов через __table_args__
6. Наличие FK-колонок (pet_id, recorded_by, user_id)

Тесты НЕ требуют БД — проверяют модели как Python-объекты.
"""

import datetime
from decimal import Decimal

from backend.app.db.models.family import ConversationState

# Импорты моделей, которые будут реализованы в Phase 3.
# До реализации моделей эти импорты вызовут ImportError — тесты будут "красными".
from backend.app.db.models.health import (
    EmergencyProfile,
    MedicalRecord,
    Medication,
    Note,
    Vaccination,
    WeightRecord,
)
from backend.app.db.models.nutrition import DietRecord, FeedingEntry

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════════════════════════════════════


def _get_index_column_sets(model_class: type) -> list[set[str]]:
    """Возвращает список множеств имён колонок для каждого индекса модели.

    Аргументы:
        model_class: класс модели SQLAlchemy с __table__

    Возвращает:
        Список множеств строк — имена колонок каждого индекса.
    """
    return [
        {column.name for column in index.columns}
        for index in model_class.__table__.indexes
    ]


def _get_column_names(model_class: type) -> list[str]:
    """Возвращает список имён колонок таблицы модели.

    Аргументы:
        model_class: класс модели SQLAlchemy с __table__

    Возвращает:
        Список строк — имена всех колонок.
    """
    return [column.name for column in model_class.__table__.columns]


def _has_foreign_key_to(model_class: type, column_name: str, target_table: str) -> bool:
    """Проверяет, что колонка модели имеет FK на указанную таблицу.

    Аргументы:
        model_class: класс модели SQLAlchemy
        column_name: имя колонки с FK
        target_table: имя целевой таблицы (например, "pet")

    Возвращает:
        True, если FK найден.
    """
    column = model_class.__table__.c[column_name]
    return any(fk.column.table.name == target_table for fk in column.foreign_keys)


# ═══════════════════════════════════════════════════════════════════════════════
# T022: health.py — WeightRecord
# ═══════════════════════════════════════════════════════════════════════════════


class TestWeightRecord:
    """Тесты модели WeightRecord (запись о весе питомца)."""

    def test_tablename(self) -> None:
        """WeightRecord.__tablename__ == 'weight_record'."""
        assert WeightRecord.__tablename__ == "weight_record"

    def test_create_with_required_fields(self) -> None:
        """WeightRecord создаётся с обязательными полями."""
        record = WeightRecord(
            pet_id=1,
            weight_kg=Decimal("12.50"),
            measured_at=datetime.date.today(),
        )
        assert record.pet_id == 1
        assert record.weight_kg == Decimal("12.50")
        assert record.measured_at == datetime.date.today()

    def test_create_without_nullable_fields(self) -> None:
        """WeightRecord создаётся без nullable-полей (recorded_by)."""
        record = WeightRecord(
            pet_id=1,
            weight_kg=Decimal("5.00"),
            measured_at=datetime.date.today(),
        )
        # recorded_by — nullable, должен быть None по умолчанию
        assert record.recorded_by is None

    def test_has_pet_id_column(self) -> None:
        """WeightRecord имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(WeightRecord)

    def test_has_recorded_by_column(self) -> None:
        """WeightRecord имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(WeightRecord)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(WeightRecord, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(WeightRecord, "recorded_by", "family_member")

    def test_composite_index_pet_id_measured_at(self) -> None:
        """Существует composite индекс на (pet_id, measured_at)."""
        index_sets = _get_index_column_sets(WeightRecord)
        assert {"pet_id", "measured_at"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T022: health.py — Vaccination
# ═══════════════════════════════════════════════════════════════════════════════


class TestVaccination:
    """Тесты модели Vaccination (запись о вакцинации)."""

    def test_tablename(self) -> None:
        """Vaccination.__tablename__ == 'vaccination'."""
        assert Vaccination.__tablename__ == "vaccination"

    def test_create_with_required_fields(self) -> None:
        """Vaccination создаётся с обязательными полями: pet_id, vaccine_name, date."""
        vaccination = Vaccination(
            pet_id=1,
            vaccine_name="Нобивак DHPPi",
            date=datetime.date.today(),
        )
        assert vaccination.pet_id == 1
        assert vaccination.vaccine_name == "Нобивак DHPPi"
        assert vaccination.date == datetime.date.today()

    def test_create_without_nullable_fields(self) -> None:
        """Vaccination создаётся без nullable-полей."""
        vaccination = Vaccination(
            pet_id=1,
            vaccine_name="Рабикан",
            date=datetime.date.today(),
        )
        assert vaccination.next_date is None
        assert vaccination.vet_name is None
        assert vaccination.batch_number is None
        assert vaccination.notes is None
        assert vaccination.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """Vaccination создаётся со всеми полями, включая nullable."""
        today = datetime.date.today()
        next_year = today.replace(year=today.year + 1)
        vaccination = Vaccination(
            pet_id=1,
            vaccine_name="Нобивак Rabies",
            date=today,
            next_date=next_year,
            vet_name="Ветклиника Друг",
            batch_number="LOT-2026-001",
            notes="Переносимость хорошая",
            recorded_by=100500,
        )
        assert vaccination.next_date == next_year
        assert vaccination.vet_name == "Ветклиника Друг"
        assert vaccination.batch_number == "LOT-2026-001"
        assert vaccination.notes == "Переносимость хорошая"
        assert vaccination.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """Vaccination имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(Vaccination)

    def test_has_recorded_by_column(self) -> None:
        """Vaccination имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(Vaccination)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(Vaccination, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(Vaccination, "recorded_by", "family_member")

    def test_composite_index_pet_id_date(self) -> None:
        """Существует composite индекс на (pet_id, date)."""
        index_sets = _get_index_column_sets(Vaccination)
        assert {"pet_id", "date"} in index_sets

    def test_composite_index_pet_id_next_date(self) -> None:
        """Существует composite индекс на (pet_id, next_date)."""
        index_sets = _get_index_column_sets(Vaccination)
        assert {"pet_id", "next_date"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T022: health.py — MedicalRecord
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedicalRecord:
    """Тесты модели MedicalRecord (медицинская запись)."""

    def test_tablename(self) -> None:
        """MedicalRecord.__tablename__ == 'medical_record'."""
        assert MedicalRecord.__tablename__ == "medical_record"

    def test_create_with_required_fields(self) -> None:
        """MedicalRecord создаётся с обязательными полями."""
        record = MedicalRecord(
            pet_id=1,
            record_type="illness",
            title="Аллергия на курицу",
            date=datetime.date.today(),
        )
        assert record.pet_id == 1
        assert record.record_type == "illness"
        assert record.title == "Аллергия на курицу"
        assert record.date == datetime.date.today()

    def test_create_without_nullable_fields(self) -> None:
        """MedicalRecord создаётся без nullable-полей."""
        record = MedicalRecord(
            pet_id=1,
            record_type="checkup",
            title="Плановый осмотр",
            date=datetime.date.today(),
        )
        assert record.description is None
        assert record.resolved_date is None
        assert record.vet_name is None
        assert record.recorded_by is None

    def test_has_pet_id_column(self) -> None:
        """MedicalRecord имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(MedicalRecord)

    def test_has_recorded_by_column(self) -> None:
        """MedicalRecord имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(MedicalRecord)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(MedicalRecord, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(MedicalRecord, "recorded_by", "family_member")

    def test_composite_index_pet_id_record_type(self) -> None:
        """Существует composite индекс на (pet_id, record_type)."""
        index_sets = _get_index_column_sets(MedicalRecord)
        assert {"pet_id", "record_type"} in index_sets

    def test_composite_index_pet_id_date(self) -> None:
        """Существует composite индекс на (pet_id, date)."""
        index_sets = _get_index_column_sets(MedicalRecord)
        assert {"pet_id", "date"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T022: health.py — Medication
# ═══════════════════════════════════════════════════════════════════════════════


class TestMedication:
    """Тесты модели Medication (лекарство питомца)."""

    def test_tablename(self) -> None:
        """Medication.__tablename__ == 'medication'."""
        assert Medication.__tablename__ == "medication"

    def test_create_with_required_fields(self) -> None:
        """Medication создаётся с обязательными полями: pet_id, name, start_date."""
        medication = Medication(
            pet_id=1,
            name="Бравекто",
            start_date=datetime.date.today(),
        )
        assert medication.pet_id == 1
        assert medication.name == "Бравекто"
        assert medication.start_date == datetime.date.today()

    def test_default_is_active_true(self) -> None:
        """Medication.is_active по умолчанию True."""
        medication = Medication(
            pet_id=1,
            name="Бравекто",
            start_date=datetime.date.today(),
        )
        assert medication.is_active is True

    def test_is_active_explicit_false(self) -> None:
        """Medication.is_active можно установить в False явно."""
        medication = Medication(
            pet_id=1,
            name="Старое лекарство",
            start_date=datetime.date(2025, 1, 1),
            is_active=False,
        )
        assert medication.is_active is False

    def test_create_without_nullable_fields(self) -> None:
        """Medication создаётся без nullable-полей."""
        medication = Medication(
            pet_id=1,
            name="Мильбемакс",
            start_date=datetime.date.today(),
        )
        assert medication.dosage is None
        assert medication.frequency is None
        assert medication.frequency_days is None
        assert medication.end_date is None
        assert medication.last_given_date is None
        assert medication.notes is None
        assert medication.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """Medication создаётся со всеми полями."""
        today = datetime.date.today()
        medication = Medication(
            pet_id=1,
            name="Бравекто",
            dosage="1 таблетка 500мг",
            frequency="каждые 3 месяца",
            frequency_days=90,
            start_date=today,
            end_date=today.replace(year=today.year + 1),
            last_given_date=today,
            is_active=True,
            notes="Давать с едой",
            recorded_by=100500,
        )
        assert medication.dosage == "1 таблетка 500мг"
        assert medication.frequency == "каждые 3 месяца"
        assert medication.frequency_days == 90
        assert medication.last_given_date == today
        assert medication.notes == "Давать с едой"
        assert medication.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """Medication имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(Medication)

    def test_has_recorded_by_column(self) -> None:
        """Medication имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(Medication)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(Medication, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(Medication, "recorded_by", "family_member")

    def test_composite_index_pet_id_is_active(self) -> None:
        """Существует composite индекс на (pet_id, is_active)."""
        index_sets = _get_index_column_sets(Medication)
        assert {"pet_id", "is_active"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T022: health.py — Note
# ═══════════════════════════════════════════════════════════════════════════════


class TestNote:
    """Тесты модели Note (заметка о питомце)."""

    def test_tablename(self) -> None:
        """Note.__tablename__ == 'note'."""
        assert Note.__tablename__ == "note"

    def test_create_with_required_fields(self) -> None:
        """Note создаётся с обязательными полями: pet_id, content."""
        note = Note(
            pet_id=1,
            content="Луна сегодня была очень активной на прогулке",
        )
        assert note.pet_id == 1
        assert note.content == "Луна сегодня была очень активной на прогулке"

    def test_create_without_nullable_fields(self) -> None:
        """Note создаётся без nullable-полей (recorded_by)."""
        note = Note(
            pet_id=1,
            content="Тестовая заметка",
        )
        assert note.recorded_by is None

    def test_has_pet_id_column(self) -> None:
        """Note имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(Note)

    def test_has_recorded_by_column(self) -> None:
        """Note имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(Note)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(Note, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(Note, "recorded_by", "family_member")

    def test_composite_index_pet_id_created_at(self) -> None:
        """Существует composite индекс на (pet_id, created_at)."""
        index_sets = _get_index_column_sets(Note)
        assert {"pet_id", "created_at"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T023: nutrition.py — DietRecord
# ═══════════════════════════════════════════════════════════════════════════════


class TestDietRecord:
    """Тесты модели DietRecord (запись о диете питомца)."""

    def test_tablename(self) -> None:
        """DietRecord.__tablename__ == 'diet_record'."""
        assert DietRecord.__tablename__ == "diet_record"

    def test_create_with_required_fields(self) -> None:
        """DietRecord создаётся с обязательными полями."""
        record = DietRecord(
            pet_id=1,
            food_brand="Royal Canin Medium Adult",
            start_date=datetime.date.today(),
        )
        assert record.pet_id == 1
        assert record.food_brand == "Royal Canin Medium Adult"
        assert record.start_date == datetime.date.today()

    def test_create_without_nullable_fields(self) -> None:
        """DietRecord создаётся без nullable-полей."""
        record = DietRecord(
            pet_id=1,
            food_brand="Acana",
            start_date=datetime.date.today(),
        )
        assert record.food_type is None
        assert record.end_date is None
        assert record.notes is None
        assert record.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """DietRecord создаётся со всеми полями."""
        today = datetime.date.today()
        record = DietRecord(
            pet_id=1,
            food_brand="Orijen Original",
            food_type="dry",
            start_date=today,
            end_date=today.replace(month=today.month % 12 + 1),
            notes="Переход с Royal Canin",
            recorded_by=100500,
        )
        assert record.food_type == "dry"
        assert record.notes == "Переход с Royal Canin"
        assert record.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """DietRecord имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(DietRecord)

    def test_has_recorded_by_column(self) -> None:
        """DietRecord имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(DietRecord)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(DietRecord, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(DietRecord, "recorded_by", "family_member")

    def test_composite_index_pet_id_end_date(self) -> None:
        """Существует composite индекс на (pet_id, end_date)."""
        index_sets = _get_index_column_sets(DietRecord)
        assert {"pet_id", "end_date"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T023: nutrition.py — FeedingEntry
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedingEntry:
    """Тесты модели FeedingEntry (запись кормления)."""

    def test_tablename(self) -> None:
        """FeedingEntry.__tablename__ == 'feeding_entry'."""
        assert FeedingEntry.__tablename__ == "feeding_entry"

    def test_create_with_required_fields(self) -> None:
        """FeedingEntry создаётся с обязательными полями."""
        now = datetime.datetime.now(tz=datetime.UTC)
        entry = FeedingEntry(
            pet_id=1,
            fed_at=now,
            food_description="Сухой корм Royal Canin, 200г",
        )
        assert entry.pet_id == 1
        assert entry.fed_at == now
        assert entry.food_description == "Сухой корм Royal Canin, 200г"

    def test_create_without_nullable_fields(self) -> None:
        """FeedingEntry создаётся без nullable-полей (portion_size, recorded_by)."""
        entry = FeedingEntry(
            pet_id=1,
            fed_at=datetime.datetime.now(tz=datetime.UTC),
            food_description="Мясо с рисом",
        )
        assert entry.portion_size is None
        assert entry.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """FeedingEntry создаётся со всеми полями."""
        now = datetime.datetime.now(tz=datetime.UTC)
        entry = FeedingEntry(
            pet_id=1,
            fed_at=now,
            food_description="Влажный корм Monge",
            portion_size="150г",
            recorded_by=100500,
        )
        assert entry.portion_size == "150г"
        assert entry.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """FeedingEntry имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(FeedingEntry)

    def test_has_recorded_by_column(self) -> None:
        """FeedingEntry имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(FeedingEntry)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(FeedingEntry, "pet_id", "pet")

    def test_recorded_by_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(FeedingEntry, "recorded_by", "family_member")

    def test_composite_index_pet_id_fed_at(self) -> None:
        """Существует composite индекс на (pet_id, fed_at)."""
        index_sets = _get_index_column_sets(FeedingEntry)
        assert {"pet_id", "fed_at"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# T024: family.py — ConversationState
# ═══════════════════════════════════════════════════════════════════════════════


class TestConversationState:
    """Тесты модели ConversationState (состояние диалога пользователя)."""

    def test_tablename(self) -> None:
        """ConversationState.__tablename__ == 'conversation_state'."""
        assert ConversationState.__tablename__ == "conversation_state"

    def test_create_with_required_fields(self) -> None:
        """ConversationState создаётся с обязательными полями."""
        state = ConversationState(telegram_user_id=100500, workspace_id=1)
        assert state.telegram_user_id == 100500
        assert state.workspace_id == 1

    def test_default_turn_count_zero(self) -> None:
        """ConversationState.turn_count по умолчанию 0."""
        state = ConversationState(telegram_user_id=100500, workspace_id=1)
        assert state.turn_count == 0

    def test_turn_count_explicit_value(self) -> None:
        """ConversationState.turn_count можно установить явно."""
        state = ConversationState(
            telegram_user_id=100500, workspace_id=1, turn_count=42
        )
        assert state.turn_count == 42

    def test_create_without_nullable_fields(self) -> None:
        """ConversationState создаётся без nullable-полей."""
        state = ConversationState(telegram_user_id=100500, workspace_id=1)
        assert state.last_response_id is None
        assert state.session_summary is None

    def test_create_with_all_fields(self) -> None:
        """ConversationState создаётся со всеми полями."""
        state = ConversationState(
            telegram_user_id=100500,
            workspace_id=1,
            last_response_id="resp_abc123",
            turn_count=10,
            session_summary="Обсуждали вакцинацию Луны",
        )
        assert state.last_response_id == "resp_abc123"
        assert state.turn_count == 10
        assert state.session_summary == "Обсуждали вакцинацию Луны"

    def test_id_is_autoincrement_primary_key(self) -> None:
        """id является автоинкрементным первичным ключом."""
        pk_columns = {
            column.name for column in ConversationState.__table__.primary_key.columns
        }
        assert pk_columns == {"id"}

    def test_has_telegram_user_id_column(self) -> None:
        """ConversationState имеет колонку telegram_user_id."""
        assert "telegram_user_id" in _get_column_names(ConversationState)

    def test_workspace_id_foreign_key(self) -> None:
        """workspace_id ссылается на таблицу workspace."""
        assert _has_foreign_key_to(ConversationState, "workspace_id", "workspace")

    def test_has_updated_at_column(self) -> None:
        """ConversationState имеет колонку updated_at."""
        assert "updated_at" in _get_column_names(ConversationState)


# ═══════════════════════════════════════════════════════════════════════════════
# T107: health.py — EmergencyProfile
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmergencyProfile:
    """Тесты модели EmergencyProfile (экстренный профиль питомца)."""

    def test_tablename(self) -> None:
        """EmergencyProfile.__tablename__ == 'emergency_profile'."""
        assert EmergencyProfile.__tablename__ == "emergency_profile"

    def test_create_with_required_fields(self) -> None:
        """EmergencyProfile создаётся с обязательным полем: pet_id."""
        profile = EmergencyProfile(pet_id=1)
        assert profile.pet_id == 1

    def test_create_without_nullable_fields(self) -> None:
        """EmergencyProfile создаётся без nullable-полей (все кроме pet_id nullable)."""
        profile = EmergencyProfile(pet_id=1)
        assert profile.allergies is None
        assert profile.chronic_conditions is None
        assert profile.vet_contact is None
        assert profile.blood_type is None
        assert profile.rabies_vaccination_date is None
        assert profile.latest_weight_snapshot is None

    def test_create_with_all_fields(self) -> None:
        """EmergencyProfile создаётся со всеми полями."""
        profile = EmergencyProfile(
            pet_id=1,
            allergies="Курица, говядина",
            chronic_conditions="Атопический дерматит",
            vet_contact="Ветклиника Друг, +7-999-123-45-67",
            blood_type="DEA 1.1+",
            rabies_vaccination_date=datetime.date(2026, 1, 15),
            latest_weight_snapshot=Decimal("12.50"),
        )
        assert profile.allergies == "Курица, говядина"
        assert profile.chronic_conditions == "Атопический дерматит"
        assert profile.vet_contact == "Ветклиника Друг, +7-999-123-45-67"
        assert profile.blood_type == "DEA 1.1+"
        assert profile.rabies_vaccination_date == datetime.date(2026, 1, 15)
        assert profile.latest_weight_snapshot == Decimal("12.50")

    def test_has_pet_id_column(self) -> None:
        """EmergencyProfile имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(EmergencyProfile)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(EmergencyProfile, "pet_id", "pet")

    def test_pet_id_unique(self) -> None:
        """pet_id имеет UNIQUE constraint (один профиль на питомца)."""
        pet_id_column = EmergencyProfile.__table__.c.pet_id
        # Проверяем через unique на колонке или через constraints таблицы
        is_unique_column = pet_id_column.unique is True
        has_unique_constraint = any(
            constraint
            for constraint in EmergencyProfile.__table__.constraints
            if hasattr(constraint, "columns")
            and len(constraint.columns) == 1
            and "pet_id" in {c.name for c in constraint.columns}
            and getattr(constraint, "_pending_colargs", None) is None
        )
        assert is_unique_column or has_unique_constraint, (
            "pet_id должен иметь UNIQUE constraint (один EmergencyProfile на питомца)"
        )
