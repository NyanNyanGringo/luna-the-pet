"""
Сервис управления семьёй: bootstrap, участники, таймзона, инвайты.

Содержит бизнес-логику работы с Family, FamilyMember, FamilySettings,
FamilyInvite. Все функции принимают AsyncSession первым аргументом
и не управляют транзакциями (commit/rollback — ответственность вызывающего).
"""

import datetime
import logging
import uuid
from zoneinfo import ZoneInfo

from backend.app.db.models.family import (
    Family,
    FamilyInvite,
    FamilyMember,
    FamilySettings,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# T129: Bootstrap — singleton семьи, участники
# ═══════════════════════════════════════════════════════════════════════════════


async def get_or_create_family(session: AsyncSession) -> Family:
    """Возвращает существующую Family или создаёт новую (singleton).

    При создании автоматически добавляет FamilySettings с timezone='UTC'.
    Гарантирует, что в БД не будет более одной Family.

    Аргументы:
        session: асинхронная сессия SQLAlchemy

    Возвращает:
        Family: единственная семья в системе

    Побочные эффекты:
        При отсутствии Family — создаёт Family + FamilySettings, делает flush.
    """
    existing_family = await _find_existing_family(session)
    if existing_family is not None:
        logger.debug("Семья уже существует, id=%d", existing_family.id)
        return existing_family

    try:
        return await _create_family_with_settings(session)
    except IntegrityError:
        logger.info("Семья создана конкурентной транзакцией, читаем существующую")
        concurrent_family = await _find_existing_family(session)
        if concurrent_family is None:
            raise
        return concurrent_family


async def _find_existing_family(session: AsyncSession) -> Family | None:
    """Ищет первую (и единственную) Family в БД.

    Аргументы:
        session: асинхронная сессия SQLAlchemy

    Возвращает:
        Family | None: найденная семья или None
    """
    result = await session.execute(select(Family).limit(1))
    return result.scalar_one_or_none()


async def _create_family_with_settings(session: AsyncSession) -> Family:
    """Создаёт новую Family с FamilySettings(timezone='UTC').

    Аргументы:
        session: асинхронная сессия SQLAlchemy

    Возвращает:
        Family: созданная семья

    Побочные эффекты:
        Добавляет Family и FamilySettings в сессию, делает flush.
    """
    async with session.begin_nested():
        family = Family()
        session.add(family)
        await session.flush()

        settings = FamilySettings(family_id=family.id, timezone="UTC")
        session.add(settings)
        await session.flush()

    logger.info("Создана новая семья id=%d с настройками UTC", family.id)
    return family


async def register_member(
    session: AsyncSession,
    telegram_user_id: int,
    first_name: str,
    username: str | None,
    family_id: int,
) -> FamilyMember:
    """Создаёт нового участника семьи.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_user_id: Telegram user ID (PK)
        first_name: имя пользователя из Telegram
        username: Telegram username (может быть None)
        family_id: ID семьи для привязки

    Возвращает:
        FamilyMember: созданный участник

    Побочные эффекты:
        Добавляет FamilyMember в сессию, делает flush.
    """
    member = FamilyMember(
        id=telegram_user_id,
        first_name=first_name,
        username=username,
        family_id=family_id,
    )
    session.add(member)
    await session.flush()

    logger.info(
        "Зарегистрирован участник id=%d (%s) в семье %d",
        telegram_user_id,
        first_name,
        family_id,
    )
    return member


async def get_member(
    session: AsyncSession,
    telegram_user_id: int,
) -> FamilyMember | None:
    """Ищет участника семьи по Telegram user ID.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_user_id: Telegram user ID для поиска

    Возвращает:
        FamilyMember | None: найденный участник или None
    """
    result = await session.execute(
        select(FamilyMember).where(FamilyMember.id == telegram_user_id)
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════════════
# T105: Timezone
# ═══════════════════════════════════════════════════════════════════════════════


async def set_timezone(
    session: AsyncSession,
    family_id: int,
    timezone_str: str,
) -> FamilySettings:
    """Устанавливает IANA-таймзону для семьи.

    Валидирует таймзону через zoneinfo.ZoneInfo.
    Невалидная или пустая строка вызывает ValueError.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи
        timezone_str: IANA-таймзона (например, 'Europe/Moscow')

    Возвращает:
        FamilySettings: обновлённые настройки

    Ошибки:
        ValueError: если timezone_str невалидна или пуста

    Побочные эффекты:
        Обновляет timezone в FamilySettings, делает flush.
    """
    _validate_timezone(timezone_str)
    settings = await _get_family_settings(session, family_id)
    settings.timezone = timezone_str
    await session.flush()

    logger.info("Таймзона семьи %d изменена на %s", family_id, timezone_str)
    return settings


def _validate_timezone(timezone_str: str) -> None:
    """Проверяет, что строка является валидной IANA-таймзоной.

    Аргументы:
        timezone_str: строка таймзоны для проверки

    Ошибки:
        ValueError: если таймзона невалидна или пуста
    """
    if not timezone_str:
        raise ValueError("Невалидная timezone: пустая строка")

    try:
        ZoneInfo(timezone_str)
    except (KeyError, ValueError) as validation_error:
        raise ValueError(f"Невалидная timezone: '{timezone_str}'") from validation_error


async def _get_family_settings(
    session: AsyncSession,
    family_id: int,
) -> FamilySettings:
    """Возвращает FamilySettings для указанной семьи.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи

    Возвращает:
        FamilySettings: настройки семьи

    Ошибки:
        ValueError: если настройки для семьи не найдены
    """
    result = await session.execute(
        select(FamilySettings).where(FamilySettings.family_id == family_id)
    )
    settings = result.scalar_one_or_none()

    if settings is None:
        raise ValueError(f"Настройки для семьи {family_id} не найдены")

    return settings


async def get_timezone(session: AsyncSession, family_id: int) -> str:
    """Возвращает текущую таймзону семьи.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи

    Возвращает:
        str: IANA-таймзона (например, 'UTC', 'Europe/Moscow')

    Ошибки:
        ValueError: если настройки для семьи не найдены
    """
    settings = await _get_family_settings(session, family_id)
    return settings.timezone


# ═══════════════════════════════════════════════════════════════════════════════
# T105: Invites
# ═══════════════════════════════════════════════════════════════════════════════


async def create_invite(
    session: AsyncSession,
    family_id: int,
    created_by_id: int,
    expires_hours: int = 24,
) -> FamilyInvite:
    """Создаёт новый инвайт-код для присоединения к семье.

    Генерирует уникальный код на основе uuid4 (первые 8 символов).
    Инвайт действителен expires_hours часов с момента создания.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи
        created_by_id: Telegram user ID создателя
        expires_hours: срок действия в часах (по умолчанию 24)

    Возвращает:
        FamilyInvite: созданный инвайт со статусом 'active'

    Побочные эффекты:
        Добавляет FamilyInvite в сессию, делает flush.
    """
    invite_code = uuid.uuid4().hex[:8].upper()
    expires_at = datetime.datetime.now(
        tz=datetime.UTC,
    ) + datetime.timedelta(hours=expires_hours)

    invite = FamilyInvite(
        family_id=family_id,
        invite_code=invite_code,
        created_by=created_by_id,
        expires_at=expires_at,
        status="active",
    )
    session.add(invite)
    await session.flush()

    logger.info(
        "Создан инвайт '%s' для семьи %d (истекает через %d ч.)",
        invite_code,
        family_id,
        expires_hours,
    )
    return invite


async def revoke_invite(
    session: AsyncSession,
    invite_id: int,
) -> FamilyInvite:
    """Отзывает инвайт — устанавливает revoked_at и status='revoked'.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        invite_id: ID инвайта для отзыва

    Возвращает:
        FamilyInvite: обновлённый инвайт

    Ошибки:
        ValueError: если инвайт не найден

    Побочные эффекты:
        Обновляет revoked_at и status, делает flush.
    """
    invite = await _get_invite_by_id(session, invite_id)

    invite.revoked_at = datetime.datetime.now(tz=datetime.UTC)
    invite.status = "revoked"
    await session.flush()

    logger.info("Инвайт id=%d отозван", invite_id)
    return invite


async def _get_invite_by_id(
    session: AsyncSession,
    invite_id: int,
) -> FamilyInvite:
    """Ищет инвайт по ID.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        invite_id: ID инвайта

    Возвращает:
        FamilyInvite: найденный инвайт

    Ошибки:
        ValueError: если инвайт не найден
    """
    result = await session.execute(
        select(FamilyInvite).where(FamilyInvite.id == invite_id)
    )
    invite = result.scalar_one_or_none()

    if invite is None:
        raise ValueError(f"Инвайт с id={invite_id} не найден")

    return invite


async def use_invite(
    session: AsyncSession,
    invite_code: str,
    user_id: int,
) -> FamilyInvite:
    """Использует инвайт-код — помечает used_by, used_at, status='used'.

    Проверки перед использованием:
    - Инвайт существует (иначе ValueError)
    - Инвайт не отозван (иначе ValueError)
    - Инвайт не использован (иначе ValueError)
    - Инвайт не просрочен (иначе ValueError)

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        invite_code: код приглашения
        user_id: Telegram user ID использующего

    Возвращает:
        FamilyInvite: обновлённый инвайт

    Ошибки:
        ValueError: если код не найден, отозван, использован или просрочен

    Побочные эффекты:
        Обновляет used_by, used_at и status, делает flush.
    """
    invite = await _find_invite_by_code(session, invite_code)
    _validate_invite_usability(invite)

    invite.used_by = user_id
    invite.used_at = datetime.datetime.now(tz=datetime.UTC)
    invite.status = "used"
    await session.flush()

    logger.info(
        "Инвайт '%s' использован пользователем %d",
        invite_code,
        user_id,
    )
    return invite


async def _find_invite_by_code(
    session: AsyncSession,
    invite_code: str,
) -> FamilyInvite:
    """Ищет инвайт по коду.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        invite_code: уникальный код инвайта

    Возвращает:
        FamilyInvite: найденный инвайт

    Ошибки:
        ValueError: если инвайт с таким кодом не существует
    """
    result = await session.execute(
        select(FamilyInvite).where(FamilyInvite.invite_code == invite_code)
    )
    invite = result.scalar_one_or_none()

    if invite is None:
        raise ValueError(f"Инвайт с кодом '{invite_code}' не найден")

    return invite


def _validate_invite_usability(invite: FamilyInvite) -> None:
    """Проверяет, что инвайт можно использовать.

    Аргументы:
        invite: инвайт для проверки

    Ошибки:
        ValueError: если инвайт отозван, уже использован или просрочен
    """
    if invite.status == "revoked" or invite.revoked_at is not None:
        raise ValueError(f"Инвайт '{invite.invite_code}' отозван")

    if invite.status == "used" or invite.used_by is not None:
        raise ValueError(f"Инвайт '{invite.invite_code}' уже использован")

    now_utc = datetime.datetime.now(tz=datetime.UTC)
    if invite.expires_at < now_utc:
        raise ValueError(f"Инвайт '{invite.invite_code}' просрочен")


async def list_invites(
    session: AsyncSession,
    family_id: int,
) -> list[FamilyInvite]:
    """Возвращает все инвайты указанной семьи.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        family_id: ID семьи

    Возвращает:
        list[FamilyInvite]: список всех инвайтов (любого статуса)
    """
    result = await session.execute(
        select(FamilyInvite).where(FamilyInvite.family_id == family_id)
    )
    return list(result.scalars().all())
