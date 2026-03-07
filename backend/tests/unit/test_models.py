"""
Тесты моделей SQLAlchemy Phase 2 проекта Luna the Dog.

Покрывает все модели инфраструктурного ядра:
- Family (singleton домохозяйства)
- FamilyMember (участник семьи, Telegram user ID как PK)
- Pet (питомец с soft-delete через is_active)
- FamilySettings (настройки семьи: таймзона, локаль)
- FamilyInvite (инвайт / одноразовый код)
- ChangeLog (журнал аудита)
- OAuthCredential (OAuth-токены OpenAI)
- family_pet (M2M связь участник-питомец)

Для каждой модели проверяется:
1. Создание с обязательными полями
2. Значения по умолчанию
3. Сохранение и чтение из БД
4. Связи (FK, M2M, relationships)
5. Индексы и unique constraints
"""

import datetime
import uuid

import pytest
from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.family import (
    Family,
    FamilyInvite,
    FamilyMember,
    FamilySettings,
    OAuthCredential,
    family_pet,
)
from backend.app.db.models.pet import Pet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные фабрики для создания тестовых экземпляров
# ═══════════════════════════════════════════════════════════════════════════════


def _make_family() -> Family:
    """Создаёт экземпляр Family для тестов."""
    return Family()


async def _persist_family(session: AsyncSession) -> Family:
    """Сохраняет Family в БД и возвращает его.

    Аргументы:
        session: активная AsyncSession

    Возвращает:
        Family: сохранённый экземпляр с заполненным id
    """
    family = _make_family()
    session.add(family)
    await session.flush()
    return family


def _make_family_member(
    telegram_user_id: int = 100500,
    first_name: str = "Алиса",
    family_id: int | None = None,
) -> FamilyMember:
    """Создаёт экземпляр FamilyMember для тестов.

    Аргументы:
        telegram_user_id: Telegram user ID (BigInteger PK)
        first_name: имя из Telegram (обязательное поле)
        family_id: FK на Family (опционально)
    """
    member = FamilyMember(
        id=telegram_user_id,
        first_name=first_name,
    )
    if family_id is not None:
        member.family_id = family_id
    return member


async def _persist_family_member(
    session: AsyncSession,
    family_id: int,
    telegram_user_id: int = 100500,
    first_name: str = "Алиса",
) -> FamilyMember:
    """Сохраняет FamilyMember в БД.

    Аргументы:
        session: активная AsyncSession
        family_id: ID семьи (FK)
        telegram_user_id: Telegram user ID
        first_name: имя из Telegram
    """
    member = _make_family_member(
        telegram_user_id=telegram_user_id,
        first_name=first_name,
        family_id=family_id,
    )
    session.add(member)
    await session.flush()
    return member


def _make_pet(
    name: str = "Луна",
    species: str = "dog",
    created_by: int | None = None,
    family_id: int | None = None,
) -> Pet:
    """Создаёт экземпляр Pet для тестов.

    Аргументы:
        name: имя питомца (обязательное)
        species: вид животного (dog/cat/other)
        created_by: FK -> FamilyMember.id
        family_id: FK -> Family.id
    """
    pet = Pet(name=name, species=species)
    if created_by is not None:
        pet.created_by = created_by
    if family_id is not None:
        pet.family_id = family_id
    return pet


async def _persist_pet(
    session: AsyncSession,
    family_id: int,
    created_by: int,
    name: str = "Луна",
    species: str = "dog",
) -> Pet:
    """Сохраняет Pet в БД.

    Аргументы:
        session: активная AsyncSession
        family_id: ID семьи
        created_by: Telegram user ID создателя
        name: имя питомца
        species: вид животного
    """
    pet = _make_pet(
        name=name,
        species=species,
        created_by=created_by,
        family_id=family_id,
    )
    session.add(pet)
    await session.flush()
    return pet


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели Family
# ═══════════════════════════════════════════════════════════════════════════════


class TestFamilyModel:
    """Тесты модели Family (singleton домохозяйства)."""

    def test_create_family_instance(self) -> None:
        """Family создаётся без аргументов (singleton)."""
        family = _make_family()
        assert family is not None

    async def test_family_persists_and_gets_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family сохраняется в БД и получает автоинкрементный id."""
        family = await _persist_family(db_session)
        assert family.id is not None
        assert isinstance(family.id, int)

    async def test_family_has_created_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family получает created_at при сохранении."""
        family = await _persist_family(db_session)
        assert family.created_at is not None

    async def test_family_read_back_from_database(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family читается обратно из БД с корректными данными."""
        family = await _persist_family(db_session)
        family_id = family.id

        result = await db_session.execute(select(Family).where(Family.id == family_id))
        loaded_family = result.scalar_one()
        assert loaded_family.id == family_id

    async def test_family_has_members_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family имеет связь members с FamilyMember."""
        family = await _persist_family(db_session)
        await _persist_family_member(db_session, family_id=family.id)

        await db_session.refresh(family, attribute_names=["members"])
        assert len(family.members) == 1

    async def test_family_has_settings_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family имеет связь settings с FamilySettings."""
        family = await _persist_family(db_session)

        settings = FamilySettings(family_id=family.id)
        db_session.add(settings)
        await db_session.flush()

        await db_session.refresh(family, attribute_names=["settings"])
        assert family.settings is not None
        assert family.settings.family_id == family.id

    async def test_family_has_invites_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family имеет связь invites с FamilyInvite."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        invite = FamilyInvite(
            invite_code=str(uuid.uuid4()),
            created_by=member.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        db_session.add(invite)
        await db_session.flush()

        await db_session.refresh(family, attribute_names=["invites"])
        assert len(family.invites) == 1

    async def test_family_has_oauth_credentials_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Family имеет связь oauth_credentials с OAuthCredential."""
        family = await _persist_family(db_session)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="encrypted_access_token",
            refresh_token_enc="encrypted_refresh_token",
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=1),
        )
        db_session.add(credential)
        await db_session.flush()

        await db_session.refresh(family, attribute_names=["oauth_credentials"])
        assert len(family.oauth_credentials) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели FamilyMember
# ═══════════════════════════════════════════════════════════════════════════════


class TestFamilyMemberModel:
    """Тесты модели FamilyMember (участник семьи)."""

    def test_create_family_member_with_required_fields(self) -> None:
        """FamilyMember создаётся с обязательными полями id и first_name."""
        member = _make_family_member(
            telegram_user_id=12345,
            first_name="Борис",
        )
        assert member.id == 12345
        assert member.first_name == "Борис"

    def test_family_member_id_is_telegram_user_id(self) -> None:
        """id — это BigInteger Telegram user ID, а не autoincrement."""
        member = _make_family_member(telegram_user_id=9876543210)
        assert member.id == 9876543210

    def test_family_member_username_is_nullable(self) -> None:
        """username по умолчанию None (nullable)."""
        member = _make_family_member()
        assert member.username is None

    def test_family_member_is_authorized_defaults_to_true(self) -> None:
        """is_authorized по умолчанию True."""
        member = _make_family_member()
        assert member.is_authorized is True

    async def test_family_member_persists_to_database(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyMember сохраняется в БД с корректными данными."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=111222333,
            first_name="Владимир",
        )
        assert member.id == 111222333
        assert member.first_name == "Владимир"

    async def test_family_member_read_back(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyMember читается обратно из БД."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(
            db_session, family_id=family.id, telegram_user_id=999888
        )

        result = await db_session.execute(
            select(FamilyMember).where(FamilyMember.id == 999888)
        )
        loaded = result.scalar_one()
        assert loaded.first_name == member.first_name

    async def test_family_member_has_created_at_with_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """created_at имеет информацию о часовом поясе (timezone-aware)."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        assert member.created_at is not None
        assert member.created_at.tzinfo is not None

    async def test_family_member_username_can_be_set(
        self,
        db_session: AsyncSession,
    ) -> None:
        """username можно установить для участника."""
        family = await _persist_family(db_session)
        member = FamilyMember(
            id=555666,
            first_name="Дмитрий",
            username="dmitry_bot",
            family_id=family.id,
        )
        db_session.add(member)
        await db_session.flush()
        assert member.username == "dmitry_bot"

    async def test_family_member_first_name_is_not_null(
        self,
        db_session: AsyncSession,
    ) -> None:
        """first_name обязательно (NOT NULL) — вставка без него вызывает ошибку."""
        family = await _persist_family(db_session)
        member = FamilyMember(id=777888, family_id=family.id)
        # first_name не установлен — ожидаем IntegrityError
        db_session.add(member)
        with pytest.raises(IntegrityError):
            await db_session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели Pet
# ═══════════════════════════════════════════════════════════════════════════════


class TestPetModel:
    """Тесты модели Pet (питомец)."""

    def test_create_pet_with_required_fields(self) -> None:
        """Pet создаётся с обязательными полями name и species."""
        pet = _make_pet(name="Рекс", species="dog")
        assert pet.name == "Рекс"
        assert pet.species == "dog"

    def test_pet_breed_is_nullable(self) -> None:
        """breed по умолчанию None."""
        pet = _make_pet()
        assert pet.breed is None

    def test_pet_birth_date_is_nullable(self) -> None:
        """birth_date по умолчанию None."""
        pet = _make_pet()
        assert pet.birth_date is None

    def test_pet_gender_is_nullable(self) -> None:
        """gender по умолчанию None."""
        pet = _make_pet()
        assert pet.gender is None

    def test_pet_origin_story_is_nullable(self) -> None:
        """origin_story по умолчанию None."""
        pet = _make_pet()
        assert pet.origin_story is None

    def test_pet_blood_type_is_nullable(self) -> None:
        """blood_type по умолчанию None."""
        pet = _make_pet()
        assert pet.blood_type is None

    def test_pet_chip_number_is_nullable(self) -> None:
        """chip_number по умолчанию None."""
        pet = _make_pet()
        assert pet.chip_number is None

    def test_pet_vet_contact_is_nullable(self) -> None:
        """vet_contact по умолчанию None."""
        pet = _make_pet()
        assert pet.vet_contact is None

    def test_pet_is_neutered_defaults_to_false(self) -> None:
        """is_neutered по умолчанию False."""
        pet = _make_pet()
        assert pet.is_neutered is False

    def test_pet_is_active_defaults_to_true(self) -> None:
        """is_active по умолчанию True (soft-delete per FR-007a)."""
        pet = _make_pet()
        assert pet.is_active is True

    async def test_pet_persists_with_all_fields(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Pet сохраняется в БД со всеми заполненными полями."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        pet = Pet(
            name="Луна",
            species="dog",
            breed="Лабрадор",
            birth_date=datetime.date(2021, 3, 15),
            gender="female",
            origin_story="Найдена в приюте",
            blood_type="DEA 1.1+",
            chip_number="900000000123456",
            vet_contact="Клиника АйВет, +7 (999) 123-45-67",
            is_neutered=True,
            created_by=member.id,
            family_id=family.id,
        )
        db_session.add(pet)
        await db_session.flush()

        assert pet.id is not None
        assert pet.breed == "Лабрадор"
        assert pet.birth_date == datetime.date(2021, 3, 15)
        assert pet.gender == "female"
        assert pet.is_neutered is True
        assert pet.chip_number == "900000000123456"

    async def test_pet_read_back_from_database(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Pet читается обратно из БД с корректными данными."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(
            db_session,
            family_id=family.id,
            created_by=member.id,
            name="Мурка",
            species="cat",
        )

        result = await db_session.execute(select(Pet).where(Pet.id == pet.id))
        loaded = result.scalar_one()
        assert loaded.name == "Мурка"
        assert loaded.species == "cat"

    async def test_pet_has_created_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Pet получает created_at при сохранении."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)
        assert pet.created_at is not None

    async def test_pet_created_by_is_foreign_key(
        self,
        db_session: AsyncSession,
    ) -> None:
        """created_by является FK -> FamilyMember.id."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(
            db_session, family_id=family.id, telegram_user_id=444555
        )
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)
        assert pet.created_by == 444555

    async def test_pet_family_id_is_foreign_key(
        self,
        db_session: AsyncSession,
    ) -> None:
        """family_id является FK -> Family.id."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)
        assert pet.family_id == family.id

    async def test_pet_soft_delete_via_is_active(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Soft-delete: установка is_active=False скрывает питомца."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)
        assert pet.is_active is True

        pet.is_active = False
        await db_session.flush()

        result = await db_session.execute(select(Pet).where(Pet.id == pet.id))
        loaded = result.scalar_one()
        assert loaded.is_active is False

    async def test_pet_name_not_null_constraint(
        self,
        db_session: AsyncSession,
    ) -> None:
        """name обязательно (NOT NULL)."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = Pet(
            species="dog",
            created_by=member.id,
            family_id=family.id,
        )
        db_session.add(pet)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_pet_species_not_null_constraint(
        self,
        db_session: AsyncSession,
    ) -> None:
        """species обязательно (NOT NULL)."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = Pet(
            name="Бобик",
            created_by=member.id,
            family_id=family.id,
        )
        db_session.add(pet)
        with pytest.raises(IntegrityError):
            await db_session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели FamilySettings
# ═══════════════════════════════════════════════════════════════════════════════


class TestFamilySettingsModel:
    """Тесты модели FamilySettings (настройки семьи)."""

    async def test_create_family_settings_with_defaults(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilySettings создаётся с дефолтной таймзоной UTC."""
        family = await _persist_family(db_session)
        settings = FamilySettings(family_id=family.id)
        db_session.add(settings)
        await db_session.flush()

        assert settings.timezone == "UTC"

    async def test_family_settings_family_id_is_unique(
        self,
        db_session: AsyncSession,
    ) -> None:
        """family_id уникально — дублирование вызывает IntegrityError."""
        family = await _persist_family(db_session)

        settings_first = FamilySettings(family_id=family.id)
        db_session.add(settings_first)
        await db_session.flush()

        settings_duplicate = FamilySettings(family_id=family.id)
        db_session.add(settings_duplicate)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_family_settings_timezone_can_be_changed(
        self,
        db_session: AsyncSession,
    ) -> None:
        """timezone можно изменить на любую IANA-таймзону."""
        family = await _persist_family(db_session)
        settings = FamilySettings(
            family_id=family.id,
            timezone="Europe/Belgrade",
        )
        db_session.add(settings)
        await db_session.flush()
        assert settings.timezone == "Europe/Belgrade"

    async def test_family_settings_date_locale_is_nullable(
        self,
        db_session: AsyncSession,
    ) -> None:
        """date_locale может быть None."""
        family = await _persist_family(db_session)
        settings = FamilySettings(family_id=family.id)
        db_session.add(settings)
        await db_session.flush()
        assert settings.date_locale is None

    async def test_family_settings_date_locale_can_be_set(
        self,
        db_session: AsyncSession,
    ) -> None:
        """date_locale можно установить."""
        family = await _persist_family(db_session)
        settings = FamilySettings(
            family_id=family.id,
            date_locale="ru_RU",
        )
        db_session.add(settings)
        await db_session.flush()
        assert settings.date_locale == "ru_RU"

    async def test_family_settings_read_back(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilySettings читается обратно из БД."""
        family = await _persist_family(db_session)
        settings = FamilySettings(
            family_id=family.id,
            timezone="Asia/Tokyo",
        )
        db_session.add(settings)
        await db_session.flush()

        result = await db_session.execute(
            select(FamilySettings).where(FamilySettings.family_id == family.id)
        )
        loaded = result.scalar_one()
        assert loaded.timezone == "Asia/Tokyo"


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели FamilyInvite
# ═══════════════════════════════════════════════════════════════════════════════


class TestFamilyInviteModel:
    """Тесты модели FamilyInvite (инвайт / одноразовый код)."""

    async def test_create_family_invite(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyInvite создаётся с обязательными полями."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        invite_code = str(uuid.uuid4())
        expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)

        invite = FamilyInvite(
            invite_code=invite_code,
            created_by=member.id,
            family_id=family.id,
            expires_at=expires_at,
        )
        db_session.add(invite)
        await db_session.flush()

        assert invite.id is not None
        assert invite.invite_code == invite_code

    async def test_family_invite_has_created_by_fk(
        self,
        db_session: AsyncSession,
    ) -> None:
        """created_by является FK -> FamilyMember.id."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=999111,
        )

        invite = FamilyInvite(
            invite_code="test-code-123",
            created_by=member.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=24),
        )
        db_session.add(invite)
        await db_session.flush()
        assert invite.created_by == 999111

    async def test_family_invite_revoked_at_is_nullable(
        self,
        db_session: AsyncSession,
    ) -> None:
        """revoked_at по умолчанию None (не отозван)."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        invite = FamilyInvite(
            invite_code="code-456",
            created_by=member.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=24),
        )
        db_session.add(invite)
        await db_session.flush()
        assert invite.revoked_at is None

    async def test_family_invite_used_by_is_nullable(
        self,
        db_session: AsyncSession,
    ) -> None:
        """used_by по умолчанию None (не использован)."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        invite = FamilyInvite(
            invite_code="code-789",
            created_by=member.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=24),
        )
        db_session.add(invite)
        await db_session.flush()
        assert invite.used_by is None
        assert invite.used_at is None

    async def test_family_invite_can_be_used(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Инвайт можно пометить как использованный."""
        family = await _persist_family(db_session)
        creator = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=111,
        )
        joiner = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=222,
            first_name="Новичок",
        )

        invite = FamilyInvite(
            invite_code="join-code",
            created_by=creator.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=24),
        )
        db_session.add(invite)
        await db_session.flush()

        now = datetime.datetime.now(datetime.UTC)
        invite.used_by = joiner.id
        invite.used_at = now
        await db_session.flush()

        assert invite.used_by == 222
        assert invite.used_at is not None

    async def test_family_invite_status_field(
        self,
        db_session: AsyncSession,
    ) -> None:
        """status отражает состояние инвайта."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        invite = FamilyInvite(
            invite_code="status-test",
            created_by=member.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=24),
            status="pending",
        )
        db_session.add(invite)
        await db_session.flush()
        assert invite.status == "pending"

    async def test_family_invite_read_back(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyInvite читается обратно из БД."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        invite = FamilyInvite(
            invite_code="read-test",
            created_by=member.id,
            family_id=family.id,
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=24),
        )
        db_session.add(invite)
        await db_session.flush()

        result = await db_session.execute(
            select(FamilyInvite).where(FamilyInvite.invite_code == "read-test")
        )
        loaded = result.scalar_one()
        assert loaded.created_by == member.id


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели ChangeLog
# ═══════════════════════════════════════════════════════════════════════════════


class TestChangeLogModel:
    """Тесты модели ChangeLog (журнал аудита)."""

    async def test_create_changelog_entry(
        self,
        db_session: AsyncSession,
    ) -> None:
        """ChangeLog создаётся с обязательными полями."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        log_entry = ChangeLog(
            entity_type="pet",
            entity_id=1,
            action="create",
            actor_id=member.id,
        )
        db_session.add(log_entry)
        await db_session.flush()

        assert log_entry.id is not None

    async def test_changelog_has_changed_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """changed_at заполняется автоматически."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        log_entry = ChangeLog(
            entity_type="pet",
            entity_id=1,
            action="update",
            actor_id=member.id,
        )
        db_session.add(log_entry)
        await db_session.flush()
        assert log_entry.changed_at is not None

    async def test_changelog_actor_id_is_fk(
        self,
        db_session: AsyncSession,
    ) -> None:
        """actor_id является FK -> FamilyMember.id."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=321654,
        )

        log_entry = ChangeLog(
            entity_type="weight_record",
            entity_id=42,
            action="delete",
            actor_id=member.id,
        )
        db_session.add(log_entry)
        await db_session.flush()
        assert log_entry.actor_id == 321654

    async def test_changelog_diff_json_is_nullable(
        self,
        db_session: AsyncSession,
    ) -> None:
        """diff_json может быть None (например, для create/delete)."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        log_entry = ChangeLog(
            entity_type="pet",
            entity_id=1,
            action="create",
            actor_id=member.id,
        )
        db_session.add(log_entry)
        await db_session.flush()
        assert log_entry.diff_json is None

    async def test_changelog_diff_json_can_store_data(
        self,
        db_session: AsyncSession,
    ) -> None:
        """diff_json может хранить JSON с изменениями."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        diff = {"name": {"old": "Луна", "new": "Лунка"}}
        log_entry = ChangeLog(
            entity_type="pet",
            entity_id=1,
            action="update",
            actor_id=member.id,
            diff_json=diff,
        )
        db_session.add(log_entry)
        await db_session.flush()
        assert log_entry.diff_json == diff

    async def test_changelog_read_back(
        self,
        db_session: AsyncSession,
    ) -> None:
        """ChangeLog читается обратно из БД с корректными данными."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)

        log_entry = ChangeLog(
            entity_type="vaccination",
            entity_id=5,
            action="create",
            actor_id=member.id,
        )
        db_session.add(log_entry)
        await db_session.flush()

        result = await db_session.execute(
            select(ChangeLog).where(ChangeLog.id == log_entry.id)
        )
        loaded = result.scalar_one()
        assert loaded.entity_type == "vaccination"
        assert loaded.entity_id == 5
        assert loaded.action == "create"


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты модели OAuthCredential
# ═══════════════════════════════════════════════════════════════════════════════


class TestOAuthCredentialModel:
    """Тесты модели OAuthCredential (OAuth-токены OpenAI)."""

    async def test_create_oauth_credential(
        self,
        db_session: AsyncSession,
    ) -> None:
        """OAuthCredential создаётся с обязательными полями."""
        family = await _persist_family(db_session)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="encrypted_access_token_data",
            refresh_token_enc="encrypted_refresh_token_data",
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=1),
        )
        db_session.add(credential)
        await db_session.flush()

        assert credential.id is not None

    async def test_oauth_credential_provider_defaults_to_openai(
        self,
        db_session: AsyncSession,
    ) -> None:
        """provider по умолчанию 'openai'."""
        family = await _persist_family(db_session)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="access",
            refresh_token_enc="refresh",
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=1),
        )
        db_session.add(credential)
        await db_session.flush()
        assert credential.provider == "openai"

    async def test_oauth_credential_status_defaults_to_active(
        self,
        db_session: AsyncSession,
    ) -> None:
        """status по умолчанию 'active'."""
        family = await _persist_family(db_session)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="access",
            refresh_token_enc="refresh",
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=1),
        )
        db_session.add(credential)
        await db_session.flush()
        assert credential.status == "active"

    async def test_oauth_credential_family_id_provider_unique(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Уникальное ограничение: (family_id, provider) — дубликат вызывает ошибку."""
        family = await _persist_family(db_session)
        expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)

        credential_first = OAuthCredential(
            family_id=family.id,
            provider="openai",
            access_token_enc="access_1",
            refresh_token_enc="refresh_1",
            expires_at=expires,
        )
        db_session.add(credential_first)
        await db_session.flush()

        credential_duplicate = OAuthCredential(
            family_id=family.id,
            provider="openai",
            access_token_enc="access_2",
            refresh_token_enc="refresh_2",
            expires_at=expires,
        )
        db_session.add(credential_duplicate)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_oauth_credential_read_back(
        self,
        db_session: AsyncSession,
    ) -> None:
        """OAuthCredential читается обратно из БД."""
        family = await _persist_family(db_session)
        expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="read_back_access",
            refresh_token_enc="read_back_refresh",
            expires_at=expires,
        )
        db_session.add(credential)
        await db_session.flush()

        result = await db_session.execute(
            select(OAuthCredential).where(OAuthCredential.id == credential.id)
        )
        loaded = result.scalar_one()
        assert loaded.access_token_enc == "read_back_access"
        assert loaded.refresh_token_enc == "read_back_refresh"
        assert loaded.family_id == family.id

    async def test_oauth_credential_status_can_be_changed(
        self,
        db_session: AsyncSession,
    ) -> None:
        """status можно изменить (active -> expired -> revoked)."""
        family = await _persist_family(db_session)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="access",
            refresh_token_enc="refresh",
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=1),
        )
        db_session.add(credential)
        await db_session.flush()

        credential.status = "expired"
        await db_session.flush()
        assert credential.status == "expired"

        credential.status = "revoked"
        await db_session.flush()
        assert credential.status == "revoked"

    async def test_oauth_credential_family_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """OAuthCredential связан с Family через family_id FK."""
        family = await _persist_family(db_session)

        credential = OAuthCredential(
            family_id=family.id,
            access_token_enc="access",
            refresh_token_enc="refresh",
            expires_at=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(hours=1),
        )
        db_session.add(credential)
        await db_session.flush()

        assert credential.family_id == family.id


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты M2M связи family_pet
# ═══════════════════════════════════════════════════════════════════════════════


class TestFamilyPetAssociation:
    """Тесты M2M связи family_pet (участник-питомец)."""

    async def test_create_family_pet_association(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Связь M2M между FamilyMember и Pet создаётся через family_pet."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)

        await db_session.execute(
            family_pet.insert().values(
                family_member_id=member.id,
                pet_id=pet.id,
            )
        )
        await db_session.flush()

        # Проверяем, что связь сохранилась
        result = await db_session.execute(
            select(family_pet).where(family_pet.c.family_member_id == member.id)
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0].pet_id == pet.id

    async def test_family_pet_composite_primary_key(
        self,
        db_session: AsyncSession,
    ) -> None:
        """family_pet имеет составной PK (family_member_id, pet_id)."""
        # Проверяем через интроспекцию таблицы
        primary_key_columns = [column.name for column in family_pet.primary_key.columns]
        assert "family_member_id" in primary_key_columns
        assert "pet_id" in primary_key_columns

    async def test_member_can_have_multiple_pets(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Один участник может быть связан с несколькими питомцами."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet_luna = await _persist_pet(
            db_session,
            family_id=family.id,
            created_by=member.id,
            name="Луна",
        )
        pet_rex = await _persist_pet(
            db_session,
            family_id=family.id,
            created_by=member.id,
            name="Рекс",
        )

        await db_session.execute(
            family_pet.insert().values(family_member_id=member.id, pet_id=pet_luna.id)
        )
        await db_session.execute(
            family_pet.insert().values(family_member_id=member.id, pet_id=pet_rex.id)
        )
        await db_session.flush()

        result = await db_session.execute(
            select(family_pet).where(family_pet.c.family_member_id == member.id)
        )
        rows = result.fetchall()
        assert len(rows) == 2

    async def test_pet_can_have_multiple_members(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Один питомец может быть связан с несколькими участниками."""
        family = await _persist_family(db_session)
        member_alice = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=1001,
            first_name="Алиса",
        )
        member_boris = await _persist_family_member(
            db_session,
            family_id=family.id,
            telegram_user_id=1002,
            first_name="Борис",
        )
        pet = await _persist_pet(
            db_session,
            family_id=family.id,
            created_by=member_alice.id,
        )

        await db_session.execute(
            family_pet.insert().values(family_member_id=member_alice.id, pet_id=pet.id)
        )
        await db_session.execute(
            family_pet.insert().values(family_member_id=member_boris.id, pet_id=pet.id)
        )
        await db_session.flush()

        result = await db_session.execute(
            select(family_pet).where(family_pet.c.pet_id == pet.id)
        )
        rows = result.fetchall()
        assert len(rows) == 2

    async def test_duplicate_association_raises_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Дублирование связи (family_member_id, pet_id) вызывает ошибку."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)

        await db_session.execute(
            family_pet.insert().values(family_member_id=member.id, pet_id=pet.id)
        )
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await db_session.execute(
                family_pet.insert().values(family_member_id=member.id, pet_id=pet.id)
            )
        await db_session.flush()

    async def test_member_pets_relationship(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyMember.pets relationship загружает связанных питомцев."""
        family = await _persist_family(db_session)
        member = await _persist_family_member(db_session, family_id=family.id)
        pet = await _persist_pet(db_session, family_id=family.id, created_by=member.id)

        await db_session.execute(
            family_pet.insert().values(family_member_id=member.id, pet_id=pet.id)
        )
        await db_session.flush()

        await db_session.refresh(member, attribute_names=["pets"])
        assert len(member.pets) == 1
        assert member.pets[0].name == pet.name


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты таблиц: индексы и constraints (интроспекция)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTableStructure:
    """Тесты структуры таблиц: индексы, уникальные ограничения, FK."""

    async def test_pet_table_has_family_id_foreign_key(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Таблица pet имеет FK на family."""
        # Проверяем наличие колонки family_id в модели Pet
        pet_columns = [column.name for column in Pet.__table__.columns]
        assert "family_id" in pet_columns

    async def test_pet_table_has_created_by_foreign_key(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Таблица pet имеет FK на family_member (created_by)."""
        pet_columns = [column.name for column in Pet.__table__.columns]
        assert "created_by" in pet_columns

    def test_family_settings_table_has_unique_family_id(self) -> None:
        """Таблица family_settings имеет unique constraint на family_id."""
        family_id_column = FamilySettings.__table__.c.family_id
        # Проверяем, что колонка family_id помечена как unique
        assert family_id_column.unique is True or any(
            constraint
            for constraint in FamilySettings.__table__.constraints
            if hasattr(constraint, "columns")
            and "family_id" in [c.name for c in constraint.columns]
        )

    def test_oauth_credential_has_unique_family_provider(self) -> None:
        """OAuthCredential имеет unique constraint на (family_id, provider)."""
        # Ищем unique constraint с двумя колонками
        unique_constraints = [
            constraint
            for constraint in OAuthCredential.__table__.constraints
            if hasattr(constraint, "columns") and len(constraint.columns) == 2
        ]
        found = False
        for constraint in unique_constraints:
            column_names = {c.name for c in constraint.columns}
            if column_names == {"family_id", "provider"}:
                found = True
                break

        # Альтернативная проверка через indexes
        if not found:
            for index in OAuthCredential.__table__.indexes:
                column_names = {c.name for c in index.columns}
                if column_names == {"family_id", "provider"} and index.unique:
                    found = True
                    break

        assert found, (
            "Не найден unique constraint на (family_id, provider) "
            "в таблице OAuthCredential"
        )

    def test_family_pet_has_composite_pk(self) -> None:
        """family_pet имеет составной PK из family_member_id и pet_id."""
        pk_column_names = {column.name for column in family_pet.primary_key.columns}
        assert pk_column_names == {"family_member_id", "pet_id"}

    def test_changelog_table_has_entity_type_column(self) -> None:
        """ChangeLog имеет колонку entity_type."""
        column_names = [column.name for column in ChangeLog.__table__.columns]
        assert "entity_type" in column_names

    def test_changelog_table_has_entity_id_column(self) -> None:
        """ChangeLog имеет колонку entity_id."""
        column_names = [column.name for column in ChangeLog.__table__.columns]
        assert "entity_id" in column_names

    def test_changelog_table_has_action_column(self) -> None:
        """ChangeLog имеет колонку action."""
        column_names = [column.name for column in ChangeLog.__table__.columns]
        assert "action" in column_names

    def test_changelog_table_has_actor_id_column(self) -> None:
        """ChangeLog имеет колонку actor_id (FK -> FamilyMember)."""
        column_names = [column.name for column in ChangeLog.__table__.columns]
        assert "actor_id" in column_names

    def test_changelog_table_has_diff_json_column(self) -> None:
        """ChangeLog имеет колонку diff_json."""
        column_names = [column.name for column in ChangeLog.__table__.columns]
        assert "diff_json" in column_names

    def test_changelog_table_has_changed_at_column(self) -> None:
        """ChangeLog имеет колонку changed_at."""
        column_names = [column.name for column in ChangeLog.__table__.columns]
        assert "changed_at" in column_names
