"""
Тесты group_events handlers — lifecycle workspace при добавлении/удалении бота.

Покрывает:
- T023: handle_bot_membership_update — приветствие и регистрация инициатора
- T024: handle_bot_membership_update — деактивация workspace при удалении бота
- T030: handle_group_migration — обновление chat_id при миграции группы в супергруппу
- T033: handle_member_update — регистрация участника при вступлении в группу
- T034: handle_member_update — деактивация участника при выходе из группы
- Регистрация обработчиков в create_group_events_router
"""

from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.enums import ChatType


def _make_chat_member_updated(
    chat_id: int = -1001234567890,
    chat_title: str = "Тестовая группа",
    chat_type: ChatType = ChatType.GROUP,
    old_status: str = "left",
    new_status: str = "member",
    from_user_id: int = 100500,
    from_username: str | None = "initiator",
    from_first_name: str | None = "Инициатор",
) -> MagicMock:
    """Создаёт mock ChatMemberUpdated для my_chat_member события.

    Аргументы:
        chat_id: ID чата
        chat_title: название чата
        chat_type: тип чата (GROUP, SUPERGROUP, PRIVATE)
        old_status: предыдущий статус бота
        new_status: новый статус бота
        from_user_id: ID пользователя-инициатора
        from_username: username инициатора
        from_first_name: имя инициатора

    Возвращает:
        MagicMock: мок ChatMemberUpdated
    """
    event = MagicMock()
    event.chat = MagicMock(id=chat_id, title=chat_title, type=chat_type)
    event.old_chat_member = MagicMock(status=old_status)
    event.new_chat_member = MagicMock(status=new_status)
    event.from_user = MagicMock(
        id=from_user_id,
        username=from_username,
        first_name=from_first_name,
    )
    event.answer = AsyncMock()
    return event


def _make_migration_message(
    chat_id: int = -1001234567890,
    migrate_to_chat_id: int = -1009876543210,
) -> MagicMock:
    """Создаёт mock Message с migrate_to_chat_id для миграции группы.

    Аргументы:
        chat_id: текущий ID чата
        migrate_to_chat_id: новый ID чата после миграции

    Возвращает:
        MagicMock: мок Message
    """
    message = MagicMock()
    message.chat = MagicMock(id=chat_id)
    message.migrate_to_chat_id = migrate_to_chat_id
    return message


# ═══════════════════════════════════════════════════════════════════════════════
# T023: Бот добавлен в группу — workspace + member + приветствие
# ═══════════════════════════════════════════════════════════════════════════════


class TestBotAdded:
    """Тесты добавления бота в группу (IS_NOT_MEMBER → IS_MEMBER)."""

    async def test_creates_workspace_and_adds_initiator_as_member(self) -> None:
        """При добавлении бота создаёт workspace и регистрирует инициатора."""
        from backend.app.bot.handlers.group_events import (
            handle_bot_membership_update,
        )

        event = _make_chat_member_updated(
            old_status="left",
            new_status="member",
            from_user_id=42,
            from_username="alice",
            from_first_name="Алиса",
        )
        session = AsyncMock()
        fake_workspace = MagicMock(id=10)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_or_create_workspace",
                new=AsyncMock(return_value=fake_workspace),
            ) as create_mock,
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ) as member_mock,
        ):
            await handle_bot_membership_update(event, session)

        create_mock.assert_awaited_once()
        member_mock.assert_awaited_once_with(
            session=session,
            workspace_id=fake_workspace.id,
            telegram_user_id=42,
            username="alice",
            first_name="Алиса",
        )

    async def test_sends_welcome_message_with_group_welcome_text(self) -> None:
        """При добавлении бота отправляет GROUP_WELCOME_TEXT в группу."""
        from backend.app.bot.handlers.constants import GROUP_WELCOME_TEXT
        from backend.app.bot.handlers.group_events import (
            handle_bot_membership_update,
        )

        event = _make_chat_member_updated(old_status="left", new_status="member")
        session = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_or_create_workspace",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ),
        ):
            await handle_bot_membership_update(event, session)

        event.answer.assert_awaited_once_with(GROUP_WELCOME_TEXT)

    async def test_ignores_non_group_chat(self) -> None:
        """Событие из private-чата игнорируется без создания workspace."""
        from backend.app.bot.handlers.group_events import (
            handle_bot_membership_update,
        )

        event = _make_chat_member_updated(chat_type=ChatType.PRIVATE)
        session = AsyncMock()

        with patch(
            "backend.app.bot.handlers.group_events.workspace_service.get_or_create_workspace",
            new=AsyncMock(),
        ) as create_mock:
            await handle_bot_membership_update(event, session)

        create_mock.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# T024: Бот удалён из группы — деактивация workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestBotRemoved:
    """Тесты удаления бота из группы (IS_MEMBER → IS_NOT_MEMBER)."""

    async def test_deactivates_workspace(self) -> None:
        """При удалении бота деактивирует workspace."""
        from backend.app.bot.handlers.group_events import (
            handle_bot_membership_update,
        )

        event = _make_chat_member_updated(
            old_status="member",
            new_status="kicked",
            chat_id=-1009999999999,
        )
        session = AsyncMock()

        with patch(
            "backend.app.bot.handlers.group_events.workspace_service.deactivate_workspace",
            new=AsyncMock(),
        ) as deactivate_mock:
            await handle_bot_membership_update(event, session)

        deactivate_mock.assert_awaited_once_with(session, -1009999999999)


# ═══════════════════════════════════════════════════════════════════════════════
# T030: Миграция группы в супергруппу
# ═══════════════════════════════════════════════════════════════════════════════


def _make_member_update_event(
    chat_id: int = -1001234567890,
    chat_type: ChatType = ChatType.GROUP,
    old_status: str = "left",
    new_status: str = "member",
    target_user_id: int = 200600,
    target_username: str | None = "target_user",
    target_first_name: str | None = "Целевой",
) -> MagicMock:
    """Создаёт mock ChatMemberUpdated для chat_member события (не my_chat_member).

    В отличие от _make_chat_member_updated, задаёт new_chat_member.user
    с атрибутами id, username, first_name — именно эти данные использует
    handle_member_update для регистрации/деактивации участника.

    Аргументы:
        chat_id: ID чата
        chat_type: тип чата (GROUP, SUPERGROUP, PRIVATE)
        old_status: предыдущий статус пользователя
        new_status: новый статус пользователя
        target_user_id: ID целевого пользователя (чей статус изменился)
        target_username: username целевого пользователя
        target_first_name: имя целевого пользователя

    Возвращает:
        MagicMock: мок ChatMemberUpdated
    """
    event = MagicMock()
    event.chat = MagicMock(id=chat_id, type=chat_type)
    event.old_chat_member = MagicMock(status=old_status)

    target_user = MagicMock(
        id=target_user_id,
        username=target_username,
        first_name=target_first_name,
    )
    event.new_chat_member = MagicMock(status=new_status, user=target_user)
    event.answer = AsyncMock()
    return event


# ═══════════════════════════════════════════════════════════════════════════════
# T033: Пользователь вступил в группу — регистрация участника workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestUserJoined:
    """Тесты handle_member_update — вступление пользователя."""

    async def test_registers_member_on_user_join(self) -> None:
        """При вступлении пользователя в группу с активным workspace
        вызывает add_or_reactivate_member с данными из new_chat_member.user."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(
            old_status="left",
            new_status="member",
            target_user_id=555,
            target_username="new_guy",
            target_first_name="Новичок",
        )
        session = AsyncMock()
        fake_workspace = MagicMock(id=77, is_active=True)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=fake_workspace),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ) as member_mock,
        ):
            await handle_member_update(event, session)

        member_mock.assert_awaited_once_with(
            session=session,
            workspace_id=77,
            telegram_user_id=555,
            username="new_guy",
            first_name="Новичок",
        )
        # Молчаливая регистрация — без приветствия
        event.answer.assert_not_awaited()

    async def test_ignores_join_in_private_chat(self) -> None:
        """Событие из private-чата игнорируется без обращения к workspace."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(chat_type=ChatType.PRIVATE)
        session = AsyncMock()

        with patch(
            "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
            new=AsyncMock(),
        ) as ws_mock:
            await handle_member_update(event, session)

        ws_mock.assert_not_awaited()

    async def test_ignores_join_when_workspace_not_found(self) -> None:
        """Если workspace не найден — участник не регистрируется."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(old_status="left", new_status="member")
        session = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ) as member_mock,
        ):
            await handle_member_update(event, session)

        member_mock.assert_not_awaited()

    async def test_ignores_join_when_workspace_inactive(self) -> None:
        """Если workspace деактивирован — участник не регистрируется."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(old_status="left", new_status="member")
        session = AsyncMock()
        inactive_workspace = MagicMock(id=88, is_active=False)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=inactive_workspace),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ) as member_mock,
        ):
            await handle_member_update(event, session)

        member_mock.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# T034: Пользователь покинул группу — деактивация участника workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestRestrictedStatus:
    """Тесты handle_member_update — restricted-статус не деактивирует участника."""

    async def test_restricted_with_is_member_true_keeps_member_active(self) -> None:
        """restricted + is_member=True — в группе, не деактивировать."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(
            old_status="member",
            new_status="restricted",
            target_user_id=777,
        )
        # restricted с is_member=True — пользователь ограничен, но в группе
        event.new_chat_member.is_member = True
        session = AsyncMock()
        fake_workspace = MagicMock(id=50, is_active=True)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=fake_workspace),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.deactivate_member",
                new=AsyncMock(),
            ) as deactivate_mock,
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ),
        ):
            await handle_member_update(event, session)

        # Не должен деактивировать — пользователь ещё в группе
        deactivate_mock.assert_not_awaited()

    async def test_restricted_with_is_member_false_deactivates_member(self) -> None:
        """restricted с is_member=False — пользователь забанен, деактивировать."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(
            old_status="member",
            new_status="restricted",
            target_user_id=888,
        )
        # restricted с is_member=False — пользователь фактически забанен
        event.new_chat_member.is_member = False
        session = AsyncMock()
        fake_workspace = MagicMock(id=51, is_active=True)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=fake_workspace),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.deactivate_member",
                new=AsyncMock(),
            ) as deactivate_mock,
        ):
            await handle_member_update(event, session)

        deactivate_mock.assert_awaited_once_with(
            session=session,
            workspace_id=51,
            telegram_user_id=888,
        )

    async def test_unrestrict_reactivates_member(self) -> None:
        """Переход restricted(is_member=False) → member реактивирует участника."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(
            old_status="restricted",
            new_status="member",
            target_user_id=999,
            target_username="unban_user",
            target_first_name="Разблокированный",
        )
        # old_chat_member.is_member=False — был забанен
        event.old_chat_member.is_member = False
        session = AsyncMock()
        fake_workspace = MagicMock(id=52, is_active=True)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=fake_workspace),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.add_or_reactivate_member",
                new=AsyncMock(),
            ) as member_mock,
        ):
            await handle_member_update(event, session)

        member_mock.assert_awaited_once_with(
            session=session,
            workspace_id=52,
            telegram_user_id=999,
            username="unban_user",
            first_name="Разблокированный",
        )


class TestUserLeft:
    """Тесты handle_member_update — выход пользователя (IS_MEMBER → IS_NOT_MEMBER)."""

    async def test_deactivates_member_on_user_leave(self) -> None:
        """При выходе пользователя из группы с активным workspace
        вызывает deactivate_member с корректными параметрами."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(
            old_status="member",
            new_status="left",
            target_user_id=999,
        )
        session = AsyncMock()
        fake_workspace = MagicMock(id=33, is_active=True)

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=fake_workspace),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.deactivate_member",
                new=AsyncMock(),
            ) as deactivate_mock,
        ):
            await handle_member_update(event, session)

        deactivate_mock.assert_awaited_once_with(
            session=session,
            workspace_id=33,
            telegram_user_id=999,
        )

    async def test_ignores_leave_when_workspace_not_found(self) -> None:
        """Если workspace не найден — деактивация участника не вызывается."""
        from backend.app.bot.handlers.group_events import handle_member_update

        event = _make_member_update_event(old_status="member", new_status="left")
        session = AsyncMock()

        with (
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.get_workspace_by_chat_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.app.bot.handlers.group_events.workspace_service.deactivate_member",
                new=AsyncMock(),
            ) as deactivate_mock,
        ):
            await handle_member_update(event, session)

        deactivate_mock.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# T030: Миграция группы в супергруппу
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroupMigration:
    """Тесты handle_group_migration — обновление chat_id при миграции."""

    async def test_calls_update_chat_id_with_correct_ids(self) -> None:
        """При миграции вызывает update_chat_id с old и new chat_id."""
        from backend.app.bot.handlers.group_events import handle_group_migration

        message = _make_migration_message(
            chat_id=-1001111111111,
            migrate_to_chat_id=-1009999999999,
        )
        session = AsyncMock()

        with patch(
            "backend.app.bot.handlers.group_events.workspace_service.update_chat_id",
            new=AsyncMock(),
        ) as update_mock:
            await handle_group_migration(message, session)

        update_mock.assert_awaited_once_with(session, -1001111111111, -1009999999999)


# ═══════════════════════════════════════════════════════════════════════════════
# Регистрация обработчиков в роутере
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroupEventsRouter:
    """Тесты create_group_events_router — регистрация обработчиков."""

    def test_migration_handler_registered(self) -> None:
        """handle_group_migration зарегистрирован в роутере на migrate_to_chat_id."""
        from backend.app.bot.handlers.group_events import (
            create_group_events_router,
        )

        router = create_group_events_router()

        # Проверяем, что message observer содержит хотя бы один handler
        message_handlers = router.message.handlers
        handler_callbacks = [h.callback for h in message_handlers]

        from backend.app.bot.handlers.group_events import handle_group_migration

        assert handle_group_migration in handler_callbacks
