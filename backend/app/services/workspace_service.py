"""
Сервис управления workspace: создание, деактивация, участники, таймзона.

Содержит бизнес-логику работы с Workspace, WorkspaceMember, WorkspaceSettings.
Все функции принимают AsyncSession первым аргументом и не управляют
транзакциями (commit/rollback — ответственность вызывающего).
"""

import datetime
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from backend.app.db.models.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
WORKSPACE_MEMBER_CREATE_RETRIES = 2
LEGACY_WORKSPACE_CHAT_ID_OFFSET = 2_000_000_000_000
SIMPLE_ACTIVE_STATUSES = {"member", "administrator", "creator"}


# ═══════════════════════════════════════════════════════════════════════════════
# Workspace CRUD
# ═══════════════════════════════════════════════════════════════════════════════


async def get_or_create_workspace(
    session: AsyncSession,
    telegram_chat_id: int,
    title: str,
) -> tuple[Workspace, bool]:
    """Находит workspace по telegram_chat_id или создаёт новый.

    Если workspace найден и неактивен — реактивирует (is_active=True,
    обновляет title). Если не найден — сначала пытается переназначить
    единственный legacy workspace из миграции, иначе создаёт новый с
    WorkspaceSettings.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_chat_id: ID Telegram-группы
        title: название группы

    Возвращает:
        tuple[Workspace, bool]: (workspace, is_new) — is_new=True если
        workspace создан впервые, False если найден или реактивирован.

    Побочные эффекты:
        При создании — добавляет Workspace + WorkspaceSettings, делает flush.
        При реактивации — обновляет is_active и title, делает flush.
    """
    workspace = await _find_workspace_by_chat_id(session, telegram_chat_id)
    if workspace is not None:
        return await _ensure_workspace_active(session, workspace, title), False

    legacy_workspace = await _find_single_legacy_workspace_for_adoption(session)
    if legacy_workspace is not None:
        try:
            adopted = await _adopt_legacy_workspace(
                session=session,
                workspace=legacy_workspace,
                telegram_chat_id=telegram_chat_id,
                title=title,
            )
            return adopted, False
        except IntegrityError:
            concurrent = await _get_workspace_after_integrity_error(
                session=session,
                telegram_chat_id=telegram_chat_id,
                title=title,
            )
            return concurrent, False

    try:
        created = await _create_workspace_with_settings(
            session, telegram_chat_id, title
        )
        return created, True
    except IntegrityError:
        concurrent = await _get_workspace_after_integrity_error(
            session=session,
            telegram_chat_id=telegram_chat_id,
            title=title,
        )
        return concurrent, False


async def _find_single_legacy_workspace_for_adoption(
    session: AsyncSession,
) -> Workspace | None:
    """Возвращает единственный legacy workspace для безопасного переназначения.

    Переназначение выполняется только если:
    1) в базе есть ровно один workspace с синтетическим chat_id из legacy-миграции;
    2) нет ни одного workspace с реальным chat_id.
    """
    if await _has_non_legacy_workspace(session):
        return None

    result = await session.execute(
        select(Workspace)
        .where(Workspace.telegram_chat_id <= -LEGACY_WORKSPACE_CHAT_ID_OFFSET)
        .order_by(Workspace.id)
        .limit(2)
    )
    legacy_workspaces = list(result.scalars().all())
    if len(legacy_workspaces) != 1:
        return None
    return legacy_workspaces[0]


async def _has_non_legacy_workspace(session: AsyncSession) -> bool:
    """Проверяет наличие хотя бы одного workspace с реальным chat_id."""
    result = await session.execute(
        select(Workspace.id)
        .where(Workspace.telegram_chat_id > -LEGACY_WORKSPACE_CHAT_ID_OFFSET)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _adopt_legacy_workspace(
    session: AsyncSession,
    workspace: Workspace,
    telegram_chat_id: int,
    title: str,
) -> Workspace:
    """Переводит legacy workspace на реальный chat_id и активирует его."""
    workspace.telegram_chat_id = telegram_chat_id
    workspace.title = title
    workspace.is_active = True
    await session.flush()
    logger.info(
        "Legacy workspace id=%d переназначен на chat_id=%d",
        workspace.id,
        telegram_chat_id,
    )
    return workspace


async def _get_workspace_after_integrity_error(
    session: AsyncSession,
    telegram_chat_id: int,
    title: str,
) -> Workspace:
    """Возвращает workspace после конкурентного IntegrityError по chat_id."""
    logger.info(
        "Workspace chat_id=%d уже создан конкурентной транзакцией",
        telegram_chat_id,
    )
    concurrent_workspace = await _find_workspace_by_chat_id(session, telegram_chat_id)
    if concurrent_workspace is None:
        raise RuntimeError(
            f"Workspace не найден после IntegrityError: chat_id={telegram_chat_id}"
        )
    return await _ensure_workspace_active(session, concurrent_workspace, title)


async def _find_workspace_by_chat_id(
    session: AsyncSession,
    telegram_chat_id: int,
) -> Workspace | None:
    """Ищет workspace по telegram_chat_id.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_chat_id: ID Telegram-группы

    Возвращает:
        Workspace | None: найденный workspace или None
    """
    result = await session.execute(
        select(Workspace).where(Workspace.telegram_chat_id == telegram_chat_id)
    )
    return result.scalar_one_or_none()


async def _ensure_workspace_active(
    session: AsyncSession,
    workspace: Workspace,
    title: str,
) -> Workspace:
    """Реактивирует workspace если неактивен, возвращает как есть если активен.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace: существующий workspace
        title: новое название (применяется при реактивации)

    Возвращает:
        Workspace: активный workspace
    """
    if not workspace.is_active:
        workspace.is_active = True
        workspace.title = title
        await session.flush()
        logger.info(
            "Workspace chat_id=%d реактивирован с title='%s'",
            workspace.telegram_chat_id,
            title,
        )

    return workspace


async def _create_workspace_with_settings(
    session: AsyncSession,
    telegram_chat_id: int,
    title: str,
) -> Workspace:
    """Создаёт новый Workspace с WorkspaceSettings (Europe/Moscow, ru).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_chat_id: ID Telegram-группы
        title: название группы

    Возвращает:
        Workspace: созданный workspace

    Побочные эффекты:
        Добавляет Workspace и WorkspaceSettings в сессию, делает flush.
    """
    async with session.begin_nested():
        workspace = Workspace(
            telegram_chat_id=telegram_chat_id,
            title=title,
        )
        session.add(workspace)
        await session.flush()

        settings = WorkspaceSettings(
            workspace_id=workspace.id,
            timezone="Europe/Moscow",
            locale="ru",
        )
        session.add(settings)
        await session.flush()

    logger.info(
        "Создан workspace id=%d для chat_id=%d ('%s')",
        workspace.id,
        telegram_chat_id,
        title,
    )
    return workspace


async def deactivate_workspace(
    session: AsyncSession,
    telegram_chat_id: int,
) -> None:
    """Деактивирует workspace (is_active=False). Молча игнорирует если не найден.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_chat_id: ID Telegram-группы

    Побочные эффекты:
        Обновляет is_active=False, делает flush. Ничего не делает если не найден.
    """
    workspace = await _find_workspace_by_chat_id(session, telegram_chat_id)
    if workspace is None:
        return

    workspace.is_active = False
    await session.flush()

    logger.info("Workspace chat_id=%d деактивирован", telegram_chat_id)


async def reactivate_workspace(
    session: AsyncSession,
    telegram_chat_id: int,
    title: str,
) -> Workspace:
    """Реактивирует workspace (is_active=True, обновляет title).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_chat_id: ID Telegram-группы
        title: новое название группы

    Возвращает:
        Workspace: реактивированный workspace

    Ошибки:
        ValueError: если workspace не найден

    Побочные эффекты:
        Обновляет is_active и title, делает flush.
    """
    workspace = await _find_workspace_by_chat_id(session, telegram_chat_id)
    if workspace is None:
        raise ValueError(
            f"Workspace с chat_id={telegram_chat_id} не найден для реактивации"
        )

    workspace.is_active = True
    workspace.title = title
    await session.flush()

    logger.info(
        "Workspace chat_id=%d реактивирован с title='%s'",
        telegram_chat_id,
        title,
    )
    return workspace


async def get_workspace_by_chat_id(
    session: AsyncSession,
    telegram_chat_id: int,
) -> Workspace | None:
    """Ищет workspace по telegram_chat_id.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_chat_id: ID Telegram-группы

    Возвращает:
        Workspace | None: найденный workspace или None
    """
    return await _find_workspace_by_chat_id(session, telegram_chat_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Участники workspace
# ═══════════════════════════════════════════════════════════════════════════════


async def add_or_reactivate_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> WorkspaceMember:
    """Создаёт или реактивирует участника workspace.

    Если участник не найден — создаёт нового. Если найден и неактивен —
    реактивирует (is_active=True, left_at=None). Обновляет username и first_name.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        telegram_user_id: Telegram user ID
        username: Telegram username (nullable)
        first_name: имя в Telegram (nullable)

    Возвращает:
        WorkspaceMember: созданный или обновлённый участник

    Побочные эффекты:
        Добавляет или обновляет WorkspaceMember, делает flush.
    """
    for attempt_index in range(WORKSPACE_MEMBER_CREATE_RETRIES):
        member = await _find_member(session, workspace_id, telegram_user_id)
        if member is not None:
            return await _update_member(session, member, username, first_name)

        created_member = await _create_member_with_savepoint(
            session=session,
            workspace_id=workspace_id,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )
        if created_member is not None:
            return created_member

        logger.info(
            "Повторяем поиск участника после unique-конфликта (attempt=%d)",
            attempt_index + 1,
        )

    member_after_retries = await _find_member(session, workspace_id, telegram_user_id)
    if member_after_retries is None:
        raise RuntimeError(
            "Не удалось создать участника после retries: "
            f"workspace_id={workspace_id}, telegram_user_id={telegram_user_id}"
        )
    return await _update_member(session, member_after_retries, username, first_name)


async def _find_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
) -> WorkspaceMember | None:
    """Ищет участника по паре (workspace_id, telegram_user_id).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        telegram_user_id: Telegram user ID

    Возвращает:
        WorkspaceMember | None: найденный участник или None
    """
    result = await session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.telegram_user_id == telegram_user_id,
        )
    )
    return result.scalar_one_or_none()


async def _create_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> WorkspaceMember:
    """Создаёт нового участника workspace.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        telegram_user_id: Telegram user ID
        username: Telegram username (nullable)
        first_name: имя в Telegram (nullable)

    Возвращает:
        WorkspaceMember: созданный участник

    Побочные эффекты:
        Добавляет WorkspaceMember в сессию, делает flush.
    """
    member = WorkspaceMember(
        workspace_id=workspace_id,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
        telegram_first_name=first_name,
    )
    session.add(member)
    await session.flush()

    logger.info(
        "Участник user_id=%d добавлен в workspace_id=%d",
        telegram_user_id,
        workspace_id,
    )
    return member


async def _create_member_with_savepoint(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> WorkspaceMember | None:
    """Создаёт участника в savepoint; при unique race возвращает None."""
    try:
        async with session.begin_nested():
            return await _create_member(
                session=session,
                workspace_id=workspace_id,
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
            )
    except IntegrityError as integrity_error:
        if not _is_workspace_member_unique_conflict(integrity_error):
            raise
        logger.info(
            "Конкурентное создание участника workspace_id=%d user_id=%d",
            workspace_id,
            telegram_user_id,
        )
        return None


def _is_workspace_member_unique_conflict(integrity_error: IntegrityError) -> bool:
    """Проверяет, что IntegrityError вызван uq_workspace_member_workspace_user."""
    original_error = getattr(integrity_error, "orig", None)
    if original_error is None:
        return False

    if getattr(original_error, "constraint_name", None) == (
        "uq_workspace_member_workspace_user"
    ):
        return True

    diagnostic = getattr(original_error, "diag", None)
    if diagnostic is not None and getattr(diagnostic, "constraint_name", None) == (
        "uq_workspace_member_workspace_user"
    ):
        return True

    return "uq_workspace_member_workspace_user" in str(original_error)


async def _update_member(
    session: AsyncSession,
    member: WorkspaceMember,
    username: str | None,
    first_name: str | None,
) -> WorkspaceMember:
    """Обновляет или реактивирует существующего участника.

    Если участник неактивен — реактивирует (is_active=True, left_at=None).
    Всегда обновляет username и first_name.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        member: существующий участник
        username: новый Telegram username
        first_name: новое имя в Telegram

    Возвращает:
        WorkspaceMember: обновлённый участник

    Побочные эффекты:
        Обновляет поля участника, делает flush.
    """
    if not member.is_active:
        member.is_active = True
        member.left_at = None

    member.telegram_username = username
    member.telegram_first_name = first_name
    await session.flush()

    return member


async def deactivate_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
) -> None:
    """Деактивирует участника (is_active=False, left_at=now()).

    Молча игнорирует если не найден.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        telegram_user_id: Telegram user ID

    Побочные эффекты:
        Обновляет is_active и left_at, делает flush. Ничего не делает если не найден.
    """
    member = await _find_member(session, workspace_id, telegram_user_id)
    if member is None:
        return

    member.is_active = False
    member.left_at = datetime.datetime.now(tz=datetime.UTC)
    await session.flush()

    logger.info(
        "Участник user_id=%d деактивирован в workspace_id=%d",
        telegram_user_id,
        workspace_id,
    )


async def get_user_workspaces(
    session: AsyncSession,
    telegram_user_id: int,
) -> list[Workspace]:
    """Возвращает все АКТИВНЫЕ workspace'ы, где пользователь — АКТИВНЫЙ участник.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        telegram_user_id: Telegram user ID

    Возвращает:
        list[Workspace]: список активных workspace'ов пользователя (может быть пустым)
    """
    result = await session.execute(
        select(Workspace)
        .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.telegram_user_id == telegram_user_id,
            WorkspaceMember.is_active == True,  # noqa: E712
            Workspace.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


def is_chat_member_active(chat_member: object) -> bool:
    """Проверяет, считается ли участник активным в Telegram-группе.

    Аргументы:
        chat_member: объект с атрибутами status и (опционально) is_member

    Возвращает:
        bool: True если участник фактически состоит в группе
    """
    member_status = getattr(chat_member, "status", None)
    if member_status in SIMPLE_ACTIVE_STATUSES:
        return True
    if member_status == "restricted":
        return bool(getattr(chat_member, "is_member", False))
    return False


async def verify_user_workspaces(
    bot: Bot,
    session: AsyncSession,
    telegram_user_id: int,
    workspaces: list[Workspace],
) -> list[Workspace]:
    """Проверяет workspace'ы через Telegram API и убирает устаревшие.

    Аргументы:
        bot: экземпляр aiogram Bot
        session: асинхронная сессия SQLAlchemy
        telegram_user_id: Telegram user ID
        workspaces: кандидаты на возврат пользователю

    Возвращает:
        list[Workspace]: только подтверждённые workspace'ы
    """
    verified_workspaces: list[Workspace] = []
    for workspace in workspaces:
        is_valid_workspace = await _verify_single_workspace(
            bot=bot,
            session=session,
            telegram_user_id=telegram_user_id,
            workspace=workspace,
        )
        if is_valid_workspace:
            verified_workspaces.append(workspace)
    return verified_workspaces


async def _verify_single_workspace(
    bot: Bot,
    session: AsyncSession,
    telegram_user_id: int,
    workspace: Workspace,
) -> bool:
    """Проверяет одно workspace-членство, деактивируя устаревшие записи."""
    try:
        chat_member = await bot.get_chat_member(
            chat_id=workspace.telegram_chat_id,
            user_id=telegram_user_id,
        )
        if is_chat_member_active(chat_member):
            return True
        await deactivate_member(session, workspace.id, telegram_user_id)
        return False
    except (TelegramBadRequest, TelegramForbiddenError):
        await deactivate_workspace(session, workspace.telegram_chat_id)
        return False
    except Exception:
        logger.warning(
            "Не удалось верифицировать workspace id=%d user_id=%d",
            workspace.id,
            telegram_user_id,
            exc_info=True,
        )
        return True


async def get_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
) -> WorkspaceMember | None:
    """Ищет участника по паре (workspace_id, telegram_user_id).

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        telegram_user_id: Telegram user ID

    Возвращает:
        WorkspaceMember | None: найденный участник или None
    """
    return await _find_member(session, workspace_id, telegram_user_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Chat ID миграция
# ═══════════════════════════════════════════════════════════════════════════════


async def update_chat_id(
    session: AsyncSession,
    old_chat_id: int,
    new_chat_id: int,
) -> None:
    """Атомарно обновляет telegram_chat_id у workspace при миграции группы.

    Идемпотентна: повторный вызов с тем же old/new — безопасный no-op,
    поскольку Telegram может доставить событие migrate_to_chat_id повторно.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        old_chat_id: текущий chat_id
        new_chat_id: новый chat_id

    Ошибки:
        ValueError: если workspace не найден ни по old_chat_id, ни по new_chat_id

    Побочные эффекты:
        Обновляет telegram_chat_id, делает flush.
    """
    workspace = await _find_workspace_by_chat_id(session, old_chat_id)
    if workspace is None:
        # Проверяем, не выполнена ли миграция ранее (replay/retry)
        already_migrated = await _find_workspace_by_chat_id(session, new_chat_id)
        if already_migrated is not None:
            logger.info(
                "Миграция chat_id %d → %d уже выполнена (idempotent no-op)",
                old_chat_id,
                new_chat_id,
            )
            return
        raise ValueError(
            f"Workspace с chat_id={old_chat_id} не найден для обновления chat_id"
        )

    workspace.telegram_chat_id = new_chat_id
    await session.flush()

    logger.info(
        "Chat ID workspace id=%d обновлён: %d → %d",
        workspace.id,
        old_chat_id,
        new_chat_id,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Таймзона workspace
# ═══════════════════════════════════════════════════════════════════════════════


async def get_timezone(
    session: AsyncSession,
    workspace_id: int,
) -> str:
    """Возвращает таймзону из WorkspaceSettings.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace

    Возвращает:
        str: IANA-таймзона (например, 'Europe/Moscow')

    Ошибки:
        ValueError: если настройки workspace не найдены
    """
    settings = await _get_workspace_settings(session, workspace_id)
    return settings.timezone


async def set_timezone(
    session: AsyncSession,
    workspace_id: int,
    timezone_str: str,
) -> WorkspaceSettings:
    """Устанавливает IANA-таймзону для workspace.

    Валидирует таймзону через zoneinfo.ZoneInfo.
    Невалидная или пустая строка вызывает ValueError.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace
        timezone_str: IANA-таймзона (например, 'Asia/Tokyo')

    Возвращает:
        WorkspaceSettings: обновлённые настройки

    Ошибки:
        ValueError: если timezone_str невалидна или пуста

    Побочные эффекты:
        Обновляет timezone в WorkspaceSettings, делает flush.
    """
    _validate_timezone(timezone_str)
    settings = await _get_workspace_settings(session, workspace_id)
    settings.timezone = timezone_str
    await session.flush()

    logger.info("Таймзона workspace %d изменена на %s", workspace_id, timezone_str)
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


async def _get_workspace_settings(
    session: AsyncSession,
    workspace_id: int,
) -> WorkspaceSettings:
    """Возвращает WorkspaceSettings для указанного workspace.

    Аргументы:
        session: асинхронная сессия SQLAlchemy
        workspace_id: ID workspace

    Возвращает:
        WorkspaceSettings: настройки workspace

    Ошибки:
        ValueError: если настройки workspace не найдены
    """
    result = await session.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id)
    )
    settings = result.scalar_one_or_none()

    if settings is None:
        raise ValueError(f"Настройки для workspace {workspace_id} не найдены")

    return settings
