"""
Тесты для строковых констант бота.

Проверяют наличие обязательных элементов в текстах ответов:
- T005: содержимое rejoin-констант (упоминание админ-прав, длина текста)
- T010: упоминание прав администратора в GROUP_WELCOME_TEXT и HELP_GROUP_TEXT
"""

from backend.app.bot.handlers.constants import (
    GROUP_REJOIN_ADMIN_TEXT,
    GROUP_REJOIN_TEXT,
    GROUP_WELCOME_TEXT,
    HELP_GROUP_TEXT,
)

# ═══════════════════════════════════════════════════════════════════════════════
# T005: Содержимое rejoin-констант
# ═══════════════════════════════════════════════════════════════════════════════


class TestRejoinConstants:
    """Проверяет содержимое констант приветствия при возвращении бота."""

    def test_rejoin_text_mentions_admin(self) -> None:
        """GROUP_REJOIN_TEXT содержит упоминание прав администратора."""
        text_lower = GROUP_REJOIN_TEXT.lower()
        has_admin_mention = "админ" in text_lower or "администратор" in text_lower
        assert has_admin_mention, (
            "GROUP_REJOIN_TEXT должен содержать просьбу о правах администратора"
        )

    def test_rejoin_admin_text_has_no_rights_request(self) -> None:
        """GROUP_REJOIN_ADMIN_TEXT не содержит просьбу о назначении админом."""
        text_lower = GROUP_REJOIN_ADMIN_TEXT.lower()
        # Не должно быть просьбы «назначьте» в контексте прав
        assert "назначьте" not in text_lower, (
            "GROUP_REJOIN_ADMIN_TEXT не должен просить о назначении админом"
        )

    def test_rejoin_text_is_compact(self) -> None:
        """GROUP_REJOIN_TEXT умещается в 400 символов (2-3 предложения)."""
        assert len(GROUP_REJOIN_TEXT) <= 400, (
            f"GROUP_REJOIN_TEXT слишком длинный: {len(GROUP_REJOIN_TEXT)} символов"
        )

    def test_rejoin_admin_text_is_compact(self) -> None:
        """GROUP_REJOIN_ADMIN_TEXT умещается в 400 символов (2-3 предложения)."""
        assert len(GROUP_REJOIN_ADMIN_TEXT) <= 400, (
            f"GROUP_REJOIN_ADMIN_TEXT слишком длинный: "
            f"{len(GROUP_REJOIN_ADMIN_TEXT)} символов"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# T010: Упоминание прав администратора в инструкционных текстах
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminMentionInTexts:
    """Проверяет, что инструкционные тексты содержат упоминание прав админа."""

    def test_group_welcome_text_mentions_admin_rights(self) -> None:
        """GROUP_WELCOME_TEXT должен содержать упоминание прав администратора."""
        text_lower = GROUP_WELCOME_TEXT.lower()
        has_admin_mention = "админ" in text_lower or "администратор" in text_lower
        assert has_admin_mention, (
            "GROUP_WELCOME_TEXT должен содержать упоминание "
            "необходимости прав администратора"
        )

    def test_help_group_text_mentions_admin_rights(self) -> None:
        """HELP_GROUP_TEXT должен содержать упоминание прав администратора."""
        text_lower = HELP_GROUP_TEXT.lower()
        has_admin_mention = "админ" in text_lower or "администратор" in text_lower
        assert has_admin_mention, (
            "HELP_GROUP_TEXT должен содержать упоминание "
            "необходимости прав администратора"
        )
