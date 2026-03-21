"""
Тесты моделей SQLAlchemy для фичи 007-extend-agent-tools.

Покрывает 5 новых моделей:
- Measurement (измерение физиологического параметра)
- VetVisit (визит к ветеринару)
- MoodLog (наблюдение за самочувствием)
- Document (документ питомца)
- HeatCycle (цикл течки)

Для каждой модели проверяется:
1. Создание экземпляра с обязательными полями
2. Значения по умолчанию (nullable-поля = None)
3. Имя таблицы (__tablename__)
4. Создание со всеми полями, включая nullable
5. Наличие composite индексов через __table_args__
6. Наличие FK-колонок (pet_id → pet, recorded_by без FK)

Тесты НЕ требуют БД — проверяют модели как Python-объекты.
"""

import datetime
from decimal import Decimal

# Импорты моделей, которые будут реализованы.
# До реализации моделей эти импорты вызовут ImportError — тесты будут "красными".
from backend.app.db.models.documents import Document
from backend.app.db.models.health import (
    HeatCycle,
    Measurement,
    MoodLog,
    VetVisit,
)

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
# Measurement (измерение физиологического параметра)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMeasurement:
    """Тесты модели Measurement (измерение: температура, пульс, дыхание)."""

    def test_tablename(self) -> None:
        """Measurement.__tablename__ == 'measurement'."""
        assert Measurement.__tablename__ == "measurement"

    def test_create_with_required_fields(self) -> None:
        """Measurement создаётся с обязательными полями."""
        record = Measurement(
            pet_id=1,
            measurement_type="temperature",
            value=Decimal("38.50"),
            unit="°C",
            measured_at=datetime.date.today(),
        )
        assert record.pet_id == 1
        assert record.measurement_type == "temperature"
        assert record.value == Decimal("38.50")
        assert record.unit == "°C"
        assert record.measured_at == datetime.date.today()

    def test_create_without_nullable_fields(self) -> None:
        """Measurement создаётся без nullable-полей (recorded_by)."""
        record = Measurement(
            pet_id=1,
            measurement_type="pulse",
            value=Decimal("80.00"),
            unit="уд/мин",
            measured_at=datetime.date.today(),
        )
        assert record.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """Measurement создаётся со всеми полями, включая nullable."""
        record = Measurement(
            pet_id=1,
            measurement_type="respiration",
            value=Decimal("20.00"),
            unit="вд/мин",
            measured_at=datetime.date.today(),
            recorded_by=100500,
        )
        assert record.measurement_type == "respiration"
        assert record.value == Decimal("20.00")
        assert record.unit == "вд/мин"
        assert record.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """Measurement имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(Measurement)

    def test_has_recorded_by_column(self) -> None:
        """Measurement имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(Measurement)

    def test_has_measurement_type_column(self) -> None:
        """Measurement имеет колонку measurement_type."""
        assert "measurement_type" in _get_column_names(Measurement)

    def test_has_value_column(self) -> None:
        """Measurement имеет колонку value."""
        assert "value" in _get_column_names(Measurement)

    def test_has_unit_column(self) -> None:
        """Measurement имеет колонку unit."""
        assert "unit" in _get_column_names(Measurement)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(Measurement, "pet_id", "pet")

    def test_recorded_by_no_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(Measurement, "recorded_by", "family_member")

    def test_composite_index_pet_id_measured_at(self) -> None:
        """Существует composite индекс на (pet_id, measured_at)."""
        index_sets = _get_index_column_sets(Measurement)
        assert {"pet_id", "measured_at"} in index_sets

    def test_composite_index_pet_id_measurement_type(self) -> None:
        """Существует composite индекс на (pet_id, measurement_type)."""
        index_sets = _get_index_column_sets(Measurement)
        assert {"pet_id", "measurement_type"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# VetVisit (визит к ветеринару)
# ═══════════════════════════════════════════════════════════════════════════════


class TestVetVisit:
    """Тесты модели VetVisit (запись о визите к ветеринару)."""

    def test_tablename(self) -> None:
        """VetVisit.__tablename__ == 'vet_visit'."""
        assert VetVisit.__tablename__ == "vet_visit"

    def test_create_with_required_fields(self) -> None:
        """VetVisit создаётся с обязательными полями."""
        visit = VetVisit(
            pet_id=1,
            reason="Плановый осмотр",
            visit_date=datetime.date.today(),
            status="planned",
        )
        assert visit.pet_id == 1
        assert visit.reason == "Плановый осмотр"
        assert visit.visit_date == datetime.date.today()
        assert visit.status == "planned"

    def test_create_without_nullable_fields(self) -> None:
        """VetVisit создаётся без nullable-полей."""
        visit = VetVisit(
            pet_id=1,
            reason="Вакцинация",
            visit_date=datetime.date.today(),
            status="completed",
        )
        assert visit.clinic is None
        assert visit.notes is None
        assert visit.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """VetVisit создаётся со всеми полями, включая nullable."""
        visit = VetVisit(
            pet_id=1,
            clinic="Ветклиника Друг",
            reason="Кастрация",
            visit_date=datetime.date(2026, 4, 15),
            status="planned",
            notes="Записаны на утро",
            recorded_by=100500,
        )
        assert visit.clinic == "Ветклиника Друг"
        assert visit.reason == "Кастрация"
        assert visit.visit_date == datetime.date(2026, 4, 15)
        assert visit.status == "planned"
        assert visit.notes == "Записаны на утро"
        assert visit.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """VetVisit имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(VetVisit)

    def test_has_recorded_by_column(self) -> None:
        """VetVisit имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(VetVisit)

    def test_has_clinic_column(self) -> None:
        """VetVisit имеет колонку clinic."""
        assert "clinic" in _get_column_names(VetVisit)

    def test_has_status_column(self) -> None:
        """VetVisit имеет колонку status."""
        assert "status" in _get_column_names(VetVisit)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(VetVisit, "pet_id", "pet")

    def test_recorded_by_no_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(VetVisit, "recorded_by", "family_member")

    def test_composite_index_pet_id_visit_date(self) -> None:
        """Существует composite индекс на (pet_id, visit_date)."""
        index_sets = _get_index_column_sets(VetVisit)
        assert {"pet_id", "visit_date"} in index_sets

    def test_composite_index_pet_id_status(self) -> None:
        """Существует composite индекс на (pet_id, status)."""
        index_sets = _get_index_column_sets(VetVisit)
        assert {"pet_id", "status"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# MoodLog (наблюдение за самочувствием)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMoodLog:
    """Тесты модели MoodLog (ежедневное наблюдение за самочувствием)."""

    def test_tablename(self) -> None:
        """MoodLog.__tablename__ == 'mood_log'."""
        assert MoodLog.__tablename__ == "mood_log"

    def test_create_with_required_fields(self) -> None:
        """MoodLog создаётся с обязательными полями."""
        log = MoodLog(
            pet_id=1,
            mood="good",
            appetite="good",
            log_date=datetime.date.today(),
        )
        assert log.pet_id == 1
        assert log.mood == "good"
        assert log.appetite == "good"
        assert log.log_date == datetime.date.today()

    def test_create_without_nullable_fields(self) -> None:
        """MoodLog создаётся без nullable-полей."""
        log = MoodLog(
            pet_id=1,
            mood="normal",
            appetite="reduced",
            log_date=datetime.date.today(),
        )
        assert log.notes is None
        assert log.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """MoodLog создаётся со всеми полями, включая nullable."""
        log = MoodLog(
            pet_id=1,
            mood="excellent",
            appetite="good",
            log_date=datetime.date.today(),
            notes="Луна сегодня очень активная, много бегала",
            recorded_by=100500,
        )
        assert log.mood == "excellent"
        assert log.appetite == "good"
        assert log.notes == "Луна сегодня очень активная, много бегала"
        assert log.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """MoodLog имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(MoodLog)

    def test_has_recorded_by_column(self) -> None:
        """MoodLog имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(MoodLog)

    def test_has_mood_column(self) -> None:
        """MoodLog имеет колонку mood."""
        assert "mood" in _get_column_names(MoodLog)

    def test_has_appetite_column(self) -> None:
        """MoodLog имеет колонку appetite."""
        assert "appetite" in _get_column_names(MoodLog)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(MoodLog, "pet_id", "pet")

    def test_recorded_by_no_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(MoodLog, "recorded_by", "family_member")

    def test_composite_index_pet_id_log_date(self) -> None:
        """Существует composite индекс на (pet_id, log_date)."""
        index_sets = _get_index_column_sets(MoodLog)
        assert {"pet_id", "log_date"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# Document (документ питомца)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocument:
    """Тесты модели Document (документ питомца: паспорт, анализы и т.д.)."""

    def test_tablename(self) -> None:
        """Document.__tablename__ == 'document'."""
        assert Document.__tablename__ == "document"

    def test_create_with_required_fields(self) -> None:
        """Document создаётся с обязательными полями."""
        doc = Document(
            pet_id=1,
            document_type="passport",
            url="https://example.com/docs/passport.pdf",
        )
        assert doc.pet_id == 1
        assert doc.document_type == "passport"
        assert doc.url == "https://example.com/docs/passport.pdf"

    def test_create_without_nullable_fields(self) -> None:
        """Document создаётся без nullable-полей."""
        doc = Document(
            pet_id=1,
            document_type="analysis",
            url="https://example.com/docs/blood-test.pdf",
        )
        assert doc.issued_date is None
        assert doc.description is None
        assert doc.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """Document создаётся со всеми полями, включая nullable."""
        doc = Document(
            pet_id=1,
            document_type="certificate",
            url="https://example.com/docs/vaccination-cert.pdf",
            issued_date=datetime.date(2026, 1, 15),
            description="Сертификат о вакцинации от бешенства",
            recorded_by=100500,
        )
        assert doc.document_type == "certificate"
        assert doc.url == "https://example.com/docs/vaccination-cert.pdf"
        assert doc.issued_date == datetime.date(2026, 1, 15)
        assert doc.description == "Сертификат о вакцинации от бешенства"
        assert doc.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """Document имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(Document)

    def test_has_recorded_by_column(self) -> None:
        """Document имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(Document)

    def test_has_document_type_column(self) -> None:
        """Document имеет колонку document_type."""
        assert "document_type" in _get_column_names(Document)

    def test_has_url_column(self) -> None:
        """Document имеет колонку url."""
        assert "url" in _get_column_names(Document)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(Document, "pet_id", "pet")

    def test_recorded_by_no_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(Document, "recorded_by", "family_member")

    def test_composite_index_pet_id_document_type(self) -> None:
        """Существует composite индекс на (pet_id, document_type)."""
        index_sets = _get_index_column_sets(Document)
        assert {"pet_id", "document_type"} in index_sets


# ═══════════════════════════════════════════════════════════════════════════════
# HeatCycle (цикл течки)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHeatCycle:
    """Тесты модели HeatCycle (запись о цикле течки)."""

    def test_tablename(self) -> None:
        """HeatCycle.__tablename__ == 'heat_cycle'."""
        assert HeatCycle.__tablename__ == "heat_cycle"

    def test_create_with_required_fields(self) -> None:
        """HeatCycle создаётся с обязательными полями."""
        cycle = HeatCycle(
            pet_id=1,
            start_date=datetime.date(2026, 3, 1),
        )
        assert cycle.pet_id == 1
        assert cycle.start_date == datetime.date(2026, 3, 1)

    def test_create_without_nullable_fields(self) -> None:
        """HeatCycle создаётся без nullable-полей."""
        cycle = HeatCycle(
            pet_id=1,
            start_date=datetime.date.today(),
        )
        assert cycle.end_date is None
        assert cycle.notes is None
        assert cycle.recorded_by is None

    def test_create_with_all_fields(self) -> None:
        """HeatCycle создаётся со всеми полями, включая nullable."""
        cycle = HeatCycle(
            pet_id=1,
            start_date=datetime.date(2026, 3, 1),
            end_date=datetime.date(2026, 3, 21),
            notes="Первая течка, поведение спокойное",
            recorded_by=100500,
        )
        assert cycle.start_date == datetime.date(2026, 3, 1)
        assert cycle.end_date == datetime.date(2026, 3, 21)
        assert cycle.notes == "Первая течка, поведение спокойное"
        assert cycle.recorded_by == 100500

    def test_has_pet_id_column(self) -> None:
        """HeatCycle имеет колонку pet_id."""
        assert "pet_id" in _get_column_names(HeatCycle)

    def test_has_recorded_by_column(self) -> None:
        """HeatCycle имеет колонку recorded_by."""
        assert "recorded_by" in _get_column_names(HeatCycle)

    def test_has_start_date_column(self) -> None:
        """HeatCycle имеет колонку start_date."""
        assert "start_date" in _get_column_names(HeatCycle)

    def test_has_end_date_column(self) -> None:
        """HeatCycle имеет колонку end_date."""
        assert "end_date" in _get_column_names(HeatCycle)

    def test_pet_id_foreign_key(self) -> None:
        """pet_id ссылается на таблицу pet."""
        assert _has_foreign_key_to(HeatCycle, "pet_id", "pet")

    def test_recorded_by_no_foreign_key(self) -> None:
        """recorded_by хранит Telegram user ID без FK на legacy family_member."""
        assert not _has_foreign_key_to(HeatCycle, "recorded_by", "family_member")

    def test_composite_index_pet_id_start_date(self) -> None:
        """Существует composite индекс на (pet_id, start_date)."""
        index_sets = _get_index_column_sets(HeatCycle)
        assert {"pet_id", "start_date"} in index_sets
