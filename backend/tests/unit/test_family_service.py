"""
Тесты сервиса семьи (family_service) — T129 + T105.

Покрывает:
- T129: Singleton family bootstrap (get_or_create_family, register_member, get_member)
- T105: Invites и timezone (set_timezone, get_timezone, create_invite,
         revoke_invite, use_invite, list_invites)

Интеграционные тесты с реальной PostgreSQL (testcontainers).
Каждый тест получает чистую транзакцию через фикстуру db_session.
"""

import asyncio
import datetime

import pytest
from backend.app.db.models.family import (
    Family,
    FamilyInvite,
    FamilyMember,
    FamilySettings,
)
from backend.app.services.family_service import (
    create_invite,
    get_member,
    get_or_create_family,
    get_timezone,
    list_invites,
    register_member,
    revoke_invite,
    set_timezone,
    use_invite,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные утилиты
# ═══════════════════════════════════════════════════════════════════════════════


async def _seed_family_with_member(
    session: AsyncSession,
) -> tuple[Family, FamilyMember]:
    """Создаёт Family + FamilyMember для тестов, требующих готовых данных.

    Возвращает:
        tuple: (Family, FamilyMember) — созданные и сохранённые сущности
    """
    family = await get_or_create_family(session)
    member = await register_member(
        session,
        telegram_user_id=100500,
        first_name="Тестовый",
        username="testuser",
        family_id=family.id,
    )
    return family, member


# ═══════════════════════════════════════════════════════════════════════════════
# T129: Singleton family bootstrap
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetOrCreateFamily:
    """Тесты get_or_create_family — singleton-создание домохозяйства."""

    async def test_creates_family_when_none_exists(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если в БД нет Family — создаёт новую с FamilySettings (timezone='UTC')."""
        family = await get_or_create_family(db_session)

        assert family is not None
        assert family.id is not None

    async def test_created_family_has_settings_with_utc(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Созданная Family содержит FamilySettings с timezone='UTC'."""
        family = await get_or_create_family(db_session)

        # Проверяем наличие FamilySettings через запрос
        result = await db_session.execute(
            select(FamilySettings).where(
                FamilySettings.family_id == family.id,
            )
        )
        settings = result.scalar_one_or_none()

        assert settings is not None
        assert settings.timezone == "UTC"

    async def test_returns_existing_family_on_second_call(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Повторный вызов возвращает ту же Family (singleton)."""
        first_family = await get_or_create_family(db_session)
        second_family = await get_or_create_family(db_session)

        assert first_family.id == second_family.id

    async def test_does_not_create_second_family(
        self,
        db_session: AsyncSession,
    ) -> None:
        """В БД не может быть двух Family — guard-проверка."""
        await get_or_create_family(db_session)
        await get_or_create_family(db_session)

        result = await db_session.execute(select(Family))
        all_families = result.scalars().all()

        assert len(all_families) == 1

    async def test_concurrent_calls_keep_singleton_family(
        self,
        async_engine: AsyncEngine,
        tables: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Конкурентные вызовы get_or_create_family не должны создавать дубли."""
        from backend.app.db.models.family import FamilyInvite, OAuthCredential
        from backend.app.services import family_service

        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        release_find = asyncio.Event()
        find_call_count = 0
        original_find = family_service._find_existing_family

        async def synchronized_find(session: AsyncSession) -> Family | None:
            nonlocal find_call_count
            result = await original_find(session)
            find_call_count += 1
            if find_call_count == 2:
                release_find.set()
            await release_find.wait()
            return result

        monkeypatch.setattr(family_service, "_find_existing_family", synchronized_find)

        async def run_creation_in_session(target_session: AsyncSession) -> None:
            """Запускает singleton-bootstrap и коммитит транзакцию в рамках task."""
            await family_service.get_or_create_family(target_session)
            await target_session.commit()

        try:
            async with (
                session_factory() as first_session,
                session_factory() as second_session,
            ):
                await asyncio.gather(
                    run_creation_in_session(first_session),
                    run_creation_in_session(second_session),
                )

            async with session_factory() as verification_session:
                result = await verification_session.execute(select(Family))
                all_families = result.scalars().all()
        finally:
            async with session_factory() as cleanup_session:
                await cleanup_session.execute(delete(FamilyInvite))
                await cleanup_session.execute(delete(FamilyMember))
                await cleanup_session.execute(delete(FamilySettings))
                await cleanup_session.execute(delete(OAuthCredential))
                await cleanup_session.execute(delete(Family))
                await cleanup_session.commit()

        assert len(all_families) == 1


class TestRegisterMember:
    """Тесты register_member — регистрация участника семьи."""

    async def test_creates_family_member(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Создаёт FamilyMember с указанными данными и привязывает к Family."""
        family = await get_or_create_family(db_session)

        member = await register_member(
            db_session,
            telegram_user_id=111222333,
            first_name="Алексей",
            username="alexey",
            family_id=family.id,
        )

        assert member is not None
        assert member.id == 111222333
        assert member.first_name == "Алексей"
        assert member.username == "alexey"

    async def test_member_linked_to_family(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Созданный FamilyMember привязан к переданной Family."""
        family = await get_or_create_family(db_session)

        member = await register_member(
            db_session,
            telegram_user_id=222333444,
            first_name="Мария",
            username="maria",
            family_id=family.id,
        )

        assert member.family_id == family.id

    async def test_member_persisted_in_database(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyMember сохраняется в БД и читается обратно."""
        family = await get_or_create_family(db_session)

        await register_member(
            db_session,
            telegram_user_id=333444555,
            first_name="Иван",
            username="ivan",
            family_id=family.id,
        )

        result = await db_session.execute(
            select(FamilyMember).where(FamilyMember.id == 333444555)
        )
        persisted_member = result.scalar_one_or_none()

        assert persisted_member is not None
        assert persisted_member.first_name == "Иван"

    async def test_member_without_username(
        self,
        db_session: AsyncSession,
    ) -> None:
        """FamilyMember может быть создан без username (nullable)."""
        family = await get_or_create_family(db_session)

        member = await register_member(
            db_session,
            telegram_user_id=444555666,
            first_name="Без юзернейма",
            username=None,
            family_id=family.id,
        )

        assert member.username is None


class TestGetMember:
    """Тесты get_member — поиск участника по Telegram user ID."""

    async def test_returns_existing_member(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает FamilyMember, если он существует в БД."""
        family = await get_or_create_family(db_session)
        await register_member(
            db_session,
            telegram_user_id=555666777,
            first_name="Ольга",
            username="olga",
            family_id=family.id,
        )

        found_member = await get_member(db_session, telegram_user_id=555666777)

        assert found_member is not None
        assert found_member.first_name == "Ольга"

    async def test_returns_none_for_unknown_user(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает None, если пользователь не найден в БД."""
        found_member = await get_member(db_session, telegram_user_id=999888777)

        assert found_member is None


# ═══════════════════════════════════════════════════════════════════════════════
# T105: Timezone
# ═══════════════════════════════════════════════════════════════════════════════


class TestSetTimezone:
    """Тесты set_timezone — установка IANA-таймзоны в FamilySettings."""

    async def test_sets_valid_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Устанавливает валидную IANA-таймзону (например, 'Europe/Moscow')."""
        family = await get_or_create_family(db_session)

        await set_timezone(db_session, family.id, "Europe/Moscow")

        current_timezone = await get_timezone(db_session, family.id)
        assert current_timezone == "Europe/Moscow"

    async def test_rejects_invalid_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Невалидная таймзона (например, 'Mars/Olympus') вызывает ошибку."""
        family = await get_or_create_family(db_session)

        with pytest.raises(ValueError, match=r"[Tt]imezone|[Нн]евалидн"):
            await set_timezone(db_session, family.id, "Mars/Olympus")

    async def test_updates_existing_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Повторный вызов перезаписывает таймзону."""
        family = await get_or_create_family(db_session)

        await set_timezone(db_session, family.id, "Europe/Moscow")
        await set_timezone(db_session, family.id, "Asia/Tokyo")

        current_timezone = await get_timezone(db_session, family.id)
        assert current_timezone == "Asia/Tokyo"

    async def test_rejects_empty_timezone_string(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Пустая строка таймзоны вызывает ошибку."""
        family = await get_or_create_family(db_session)

        with pytest.raises((ValueError, KeyError)):
            await set_timezone(db_session, family.id, "")


class TestGetTimezone:
    """Тесты get_timezone — получение таймзоны из FamilySettings."""

    async def test_returns_default_utc(
        self,
        db_session: AsyncSession,
    ) -> None:
        """По умолчанию возвращает 'UTC' (значение из get_or_create_family)."""
        family = await get_or_create_family(db_session)

        timezone_value = await get_timezone(db_session, family.id)

        assert timezone_value == "UTC"

    async def test_returns_updated_timezone(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает обновлённую таймзону после set_timezone."""
        family = await get_or_create_family(db_session)
        await set_timezone(db_session, family.id, "America/New_York")

        timezone_value = await get_timezone(db_session, family.id)

        assert timezone_value == "America/New_York"


# ═══════════════════════════════════════════════════════════════════════════════
# T105: Invites
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateInvite:
    """Тесты create_invite — создание одноразового инвайт-кода."""

    async def test_creates_invite_with_unique_code(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Создаёт FamilyInvite с уникальным кодом."""
        family, member = await _seed_family_with_member(db_session)

        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        assert invite is not None
        assert invite.invite_code is not None
        assert len(invite.invite_code) > 0

    async def test_invite_has_expiry(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Инвайт содержит expires_at в будущем."""
        family, member = await _seed_family_with_member(db_session)

        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
            expires_hours=24,
        )

        assert invite.expires_at is not None
        # expires_at должен быть в будущем (как минимум через 23 часа)
        now_utc = datetime.datetime.now(tz=datetime.UTC)
        assert invite.expires_at > now_utc

    async def test_invite_codes_are_unique(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Два инвайта имеют разные коды."""
        family, member = await _seed_family_with_member(db_session)

        first_invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )
        second_invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        assert first_invite.invite_code != second_invite.invite_code

    async def test_invite_status_is_active(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Новый инвайт имеет статус 'active'."""
        family, member = await _seed_family_with_member(db_session)

        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        assert invite.status == "active"

    async def test_invite_linked_to_family_and_creator(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Инвайт привязан к семье и создателю."""
        family, member = await _seed_family_with_member(db_session)

        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        assert invite.family_id == family.id
        assert invite.created_by == member.id


class TestRevokeInvite:
    """Тесты revoke_invite — отзыв инвайта."""

    async def test_sets_revoked_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """После отзыва устанавливается revoked_at."""
        family, member = await _seed_family_with_member(db_session)
        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        await revoke_invite(db_session, invite.id)

        # Перечитываем из БД
        result = await db_session.execute(
            select(FamilyInvite).where(FamilyInvite.id == invite.id)
        )
        revoked_invite = result.scalar_one()

        assert revoked_invite.revoked_at is not None

    async def test_revoked_invite_cannot_be_used(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Отозванный инвайт нельзя использовать — вызывает ошибку."""
        family, member = await _seed_family_with_member(db_session)
        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )
        await revoke_invite(db_session, invite.id)

        # Регистрируем нового пользователя для использования инвайта
        new_member = await register_member(
            db_session,
            telegram_user_id=999111222,
            first_name="Новый",
            username="newuser",
            family_id=family.id,
        )

        with pytest.raises((ValueError, RuntimeError)):
            await use_invite(
                db_session,
                invite_code=invite.invite_code,
                user_id=new_member.id,
            )


class TestUseInvite:
    """Тесты use_invite — использование инвайт-кода."""

    async def test_marks_invite_as_used(
        self,
        db_session: AsyncSession,
    ) -> None:
        """После использования инвайт помечается: used_by, used_at, status='used'."""
        family, member = await _seed_family_with_member(db_session)
        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        # Регистрируем нового пользователя
        new_member = await register_member(
            db_session,
            telegram_user_id=888777666,
            first_name="Гость",
            username="guest",
            family_id=family.id,
        )

        await use_invite(
            db_session,
            invite_code=invite.invite_code,
            user_id=new_member.id,
        )

        # Перечитываем из БД
        result = await db_session.execute(
            select(FamilyInvite).where(FamilyInvite.id == invite.id)
        )
        used_invite = result.scalar_one()

        assert used_invite.status == "used"
        assert used_invite.used_by == new_member.id
        assert used_invite.used_at is not None

    async def test_expired_invite_raises_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Просроченный инвайт (expires_at в прошлом) вызывает ошибку."""
        family, member = await _seed_family_with_member(db_session)

        # Создаём инвайт с минимальным сроком, затем руками ставим expires_at в прошлое
        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
            expires_hours=1,
        )

        # Подменяем expires_at на прошлую дату
        invite.expires_at = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(
            hours=1
        )
        await db_session.flush()

        new_member = await register_member(
            db_session,
            telegram_user_id=777666555,
            first_name="Опоздавший",
            username="late",
            family_id=family.id,
        )

        with pytest.raises((ValueError, RuntimeError)):
            await use_invite(
                db_session,
                invite_code=invite.invite_code,
                user_id=new_member.id,
            )

    async def test_already_used_invite_raises_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Уже использованный инвайт нельзя использовать повторно."""
        family, member = await _seed_family_with_member(db_session)
        invite = await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        first_user = await register_member(
            db_session,
            telegram_user_id=666555444,
            first_name="Первый",
            username="first",
            family_id=family.id,
        )
        await use_invite(
            db_session,
            invite_code=invite.invite_code,
            user_id=first_user.id,
        )

        second_user = await register_member(
            db_session,
            telegram_user_id=555444333,
            first_name="Второй",
            username="second",
            family_id=family.id,
        )

        with pytest.raises((ValueError, RuntimeError)):
            await use_invite(
                db_session,
                invite_code=invite.invite_code,
                user_id=second_user.id,
            )

    async def test_nonexistent_invite_code_raises_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Несуществующий код инвайта вызывает ошибку."""
        with pytest.raises((ValueError, RuntimeError, LookupError)):
            await use_invite(
                db_session,
                invite_code="nonexistent_code_12345",
                user_id=123456789,
            )


class TestListInvites:
    """Тесты list_invites — получение списка инвайтов семьи."""

    async def test_returns_empty_list_when_no_invites(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает пустой список, если инвайтов нет."""
        family = await get_or_create_family(db_session)

        invites = await list_invites(db_session, family.id)

        assert invites == []

    async def test_returns_all_invites_for_family(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Возвращает все инвайты для указанной семьи."""
        family, member = await _seed_family_with_member(db_session)

        await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )
        await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        invites = await list_invites(db_session, family.id)

        assert len(invites) == 2

    async def test_returns_invites_as_family_invite_instances(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Элементы списка являются экземплярами FamilyInvite."""
        family, member = await _seed_family_with_member(db_session)
        await create_invite(
            db_session,
            family_id=family.id,
            created_by_id=member.id,
        )

        invites = await list_invites(db_session, family.id)

        assert len(invites) == 1
        assert isinstance(invites[0], FamilyInvite)
