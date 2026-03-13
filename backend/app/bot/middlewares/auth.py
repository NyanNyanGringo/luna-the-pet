"""
Middleware группового workspace-контекста.

Для групповых сообщений находит активный workspace по chat_id,
лениво добавляет/реактивирует участника и прокидывает в handler data:
- workspace: Workspace
- member: WorkspaceMember
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import TelegramObject
from backend.app.services import workspace_service

logger = logging.getLogger(__name__)

_GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}


class AuthMiddleware(BaseMiddleware):
    """Подготавливает workspace/member-контекст для group handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Ищет активный workspace, добавляет участника и вызывает handler."""
        if not _is_group_message_event(event):
            return await handler(event, data)

        session = data["session"]
        chat = event.chat
        user = event.from_user
        workspace = await workspace_service.get_workspace_by_chat_id(session, chat.id)

        if workspace is None or not workspace.is_active:
            await _send_rejection(
                event,
                "Этот чат ещё не подключён к workspace. Добавьте бота заново.",
            )
            return None

        member = await workspace_service.add_or_reactivate_member(
            session=session,
            workspace_id=workspace.id,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
        data["workspace"] = workspace
        data["member"] = member
        return await handler(event, data)


def _is_group_message_event(event: TelegramObject) -> bool:
    """Проверяет, что событие — сообщение из group/supergroup."""
    chat = getattr(event, "chat", None)
    user = getattr(event, "from_user", None)
    if chat is None or user is None:
        return False
    return chat.type in _GROUP_CHAT_TYPES


async def _send_rejection(event: TelegramObject, text: str) -> None:
    """Отправляет ответ пользователю, если событие поддерживает answer()."""
    answer_method = getattr(event, "answer", None)
    if answer_method is None or not callable(answer_method):
        return
    if not inspect.iscoroutinefunction(answer_method):
        return
    await answer_method(text)
    logger.info("Запрос отклонён middleware: %s", text)
