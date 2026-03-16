"""Добавить мультитенантные модели workspace.

Создаёт таблицы workspace, workspace_member, workspace_settings.
Обновляет pet (family_id → workspace_id), conversation_state (полная
реструктуризация), change_log (+ workspace_id), а также снимает legacy FK на
family_member в health/nutrition/audit.
Удаляет family_invite, family_pet, family_settings, family_member, family.

Для legacy-БД сценарий делает backfill перед включением NOT NULL в pet.

Revision ID: a1b2c3d4e5f6
Revises: d4e6c9b19f3a
Create Date: 2026-03-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "d4e6c9b19f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_WORKSPACE_CHAT_ID_OFFSET = 2_000_000_000_000
CONVERSATION_STATE_LEGACY_TABLE = "conversation_state_legacy"
CONVERSATION_STATE_WORKSPACE_TABLE = "conversation_state_workspace"


def upgrade() -> None:
    """Upgrade schema."""
    _create_workspace_tables()
    _backfill_workspace_tables_from_legacy_families()
    _update_pet_table()
    _rebuild_conversation_state()
    _update_change_log()
    _drop_family_member_foreign_keys()
    _drop_deprecated_tables()


def downgrade() -> None:
    """Downgrade schema."""
    _restore_family_core_tables()
    _backfill_family_members_from_workspace_data()
    _restore_deprecated_tables()
    _restore_family_member_foreign_keys()
    _restore_change_log()
    _restore_conversation_state()
    _restore_pet_table()
    _drop_workspace_tables()


# ═══════════════════════════════════════════════════════════════════════════════
# Upgrade: создание новых таблиц
# ═══════════════════════════════════════════════════════════════════════════════


def _create_workspace_tables() -> None:
    """Создаёт workspace, workspace_member, workspace_settings."""
    op.create_table(
        "workspace",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace")),
        sa.UniqueConstraint(
            "telegram_chat_id",
            name=op.f("uq_workspace_telegram_chat_id"),
        ),
    )
    op.create_index(
        op.f("ix_workspace_telegram_chat_id"),
        "workspace",
        ["telegram_chat_id"],
        unique=True,
    )

    op.create_table(
        "workspace_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_first_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_workspace_member_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_member")),
        sa.UniqueConstraint(
            "workspace_id",
            "telegram_user_id",
            name="uq_workspace_member_workspace_user",
        ),
    )
    op.create_index(
        op.f("ix_workspace_member_telegram_user_id"),
        "workspace_member",
        ["telegram_user_id"],
        unique=False,
    )

    op.create_table(
        "workspace_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_workspace_settings_workspace_id_workspace"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_settings")),
        sa.UniqueConstraint(
            "workspace_id",
            name=op.f("uq_workspace_settings_workspace_id"),
        ),
    )


def _backfill_workspace_tables_from_legacy_families() -> None:
    """Создаёт workspace/workspace_settings для legacy family-данных."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO workspace (telegram_chat_id, title, is_active)
            SELECT
                CAST(-CAST(:chat_offset AS BIGINT) - family.id AS BIGINT),
                'Migrated family ' || family.id,
                true
            FROM family
            ON CONFLICT (telegram_chat_id) DO NOTHING
            """
        ),
        {"chat_offset": LEGACY_WORKSPACE_CHAT_ID_OFFSET},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO workspace_settings (workspace_id, timezone, locale)
            SELECT workspace.id, 'Europe/Moscow', 'ru'
            FROM workspace
            LEFT JOIN workspace_settings
                ON workspace_settings.workspace_id = workspace.id
            WHERE workspace_settings.id IS NULL
            """
        )
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Upgrade: обновление существующих таблиц
# ═══════════════════════════════════════════════════════════════════════════════


def _update_pet_table() -> None:
    """Заменяет family_id → workspace_id в таблице pet."""
    bind = op.get_bind()
    op.add_column(
        "pet",
        sa.Column("workspace_id", sa.Integer(), nullable=True),
    )
    bind.execute(
        sa.text(
            """
            UPDATE pet
            SET workspace_id = workspace.id
            FROM workspace
            WHERE workspace.telegram_chat_id =
                CAST(-CAST(:chat_offset AS BIGINT) - pet.family_id AS BIGINT)
              AND pet.workspace_id IS NULL
            """
        ),
        {"chat_offset": LEGACY_WORKSPACE_CHAT_ID_OFFSET},
    )
    op.alter_column(
        "pet",
        "workspace_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        op.f("fk_pet_workspace_id_workspace"),
        "pet",
        "workspace",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("fk_pet_family_id_family", "pet", type_="foreignkey")
    op.drop_constraint("fk_pet_created_by_family_member", "pet", type_="foreignkey")
    op.drop_column("pet", "family_id")


def _rebuild_conversation_state() -> None:
    """Мигрирует conversation_state на workspace-схему без потери runtime-данных."""
    op.rename_table("conversation_state", CONVERSATION_STATE_LEGACY_TABLE)
    _rename_conversation_state_primary_key(
        CONVERSATION_STATE_LEGACY_TABLE,
        "pk_conversation_state_legacy",
    )
    _drop_conversation_state_updated_at_trigger(CONVERSATION_STATE_LEGACY_TABLE)
    _create_workspace_conversation_state_table()
    _assert_upgrade_conversation_state_integrity()
    _migrate_conversation_state_rows_to_workspace_schema()
    op.drop_table(CONVERSATION_STATE_LEGACY_TABLE)
    _create_conversation_state_updated_at_trigger("conversation_state")


def _create_workspace_conversation_state_table() -> None:
    """Создаёт новую workspace-структуру conversation_state."""
    op.create_table(
        "conversation_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("last_response_id", sa.String(length=200), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("session_summary", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_conversation_state_workspace_id_workspace"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_state")),
        sa.UniqueConstraint(
            "telegram_user_id",
            "workspace_id",
            name="uq_conversation_state_user_workspace",
        ),
    )


def _create_legacy_conversation_state_table() -> None:
    """Создаёт legacy-структуру conversation_state для downgrade."""
    op.create_table(
        "conversation_state",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("last_response_id", sa.String(length=200), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("session_summary", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["family_member.id"],
            name=op.f("fk_conversation_state_user_id_family_member"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_conversation_state")),
    )


def _drop_conversation_state_updated_at_trigger(table_name: str) -> None:
    """Удаляет trigger/function updated_at для указанной таблицы conversation_state."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        f"DROP TRIGGER IF EXISTS trg_conversation_state_set_updated_at ON {table_name};"
    )
    op.execute("DROP FUNCTION IF EXISTS conversation_state_set_updated_at();")


def _create_conversation_state_updated_at_trigger(table_name: str) -> None:
    """Создаёт trigger/function updated_at для указанной таблицы conversation_state."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION conversation_state_set_updated_at()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_conversation_state_set_updated_at
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION conversation_state_set_updated_at();
        """
    )


def _assert_upgrade_conversation_state_integrity() -> None:
    """Проверяет, что legacy conversation_state полностью маппится в workspace."""
    _assert_no_missing_conversation_state_members()
    _assert_no_missing_conversation_state_workspaces()


def _assert_no_missing_conversation_state_members() -> None:
    """Падает, если в legacy conversation_state есть user_id без family_member."""
    bind = op.get_bind()
    missing_rows = bind.execute(
        sa.text(
            """
            SELECT legacy.user_id
            FROM conversation_state_legacy AS legacy
            LEFT JOIN family_member ON family_member.id = legacy.user_id
            WHERE family_member.id IS NULL
            ORDER BY legacy.user_id
            LIMIT 10
            """
        )
    ).all()
    if not missing_rows:
        return
    sample_user_ids = ", ".join(str(int(row.user_id)) for row in missing_rows)
    raise RuntimeError(
        "Migration a1b2c3d4e5f6: conversation_state upgrade failed. "
        "Missing family_member for legacy user_id values: "
        f"{sample_user_ids}"
    )


def _assert_no_missing_conversation_state_workspaces() -> None:
    """Падает, если legacy conversation_state нельзя связать с workspace."""
    bind = op.get_bind()
    missing_rows = bind.execute(
        sa.text(
            """
            SELECT legacy.user_id
            FROM conversation_state_legacy AS legacy
            JOIN family_member ON family_member.id = legacy.user_id
            LEFT JOIN workspace
                ON workspace.telegram_chat_id = (
                    CAST(
                        -CAST(:chat_offset AS BIGINT) - family_member.family_id
                        AS BIGINT
                    )
                )
            WHERE workspace.id IS NULL
            ORDER BY legacy.user_id
            LIMIT 10
            """
        ),
        {"chat_offset": LEGACY_WORKSPACE_CHAT_ID_OFFSET},
    ).all()
    if not missing_rows:
        return
    sample_user_ids = ", ".join(str(int(row.user_id)) for row in missing_rows)
    raise RuntimeError(
        "Migration a1b2c3d4e5f6: conversation_state upgrade failed. "
        "Missing workspace mapping for legacy user_id values: "
        f"{sample_user_ids}"
    )


def _migrate_conversation_state_rows_to_workspace_schema() -> None:
    """Переносит legacy conversation_state в workspace-формат c дедупликацией."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            WITH mapped_state AS (
                SELECT
                    legacy.user_id AS telegram_user_id,
                    workspace.id AS workspace_id,
                    legacy.last_response_id,
                    legacy.turn_count,
                    legacy.session_summary,
                    legacy.updated_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY legacy.user_id, workspace.id
                        ORDER BY
                            legacy.updated_at DESC NULLS LAST,
                            CASE
                                WHEN COALESCE(BTRIM(legacy.last_response_id), '') = ''
                                    THEN 0
                                ELSE 1
                            END DESC,
                            legacy.turn_count DESC,
                            COALESCE(legacy.last_response_id, '') DESC
                    ) AS row_number
                FROM conversation_state_legacy AS legacy
                JOIN family_member ON family_member.id = legacy.user_id
                JOIN workspace
                    ON workspace.telegram_chat_id = (
                        CAST(
                            -CAST(:chat_offset AS BIGINT) - family_member.family_id
                            AS BIGINT
                        )
                    )
            )
            INSERT INTO conversation_state (
                telegram_user_id,
                workspace_id,
                last_response_id,
                turn_count,
                session_summary,
                updated_at
            )
            SELECT
                telegram_user_id,
                workspace_id,
                last_response_id,
                turn_count,
                session_summary,
                updated_at
            FROM mapped_state
            WHERE row_number = 1
            """
        ),
        {"chat_offset": LEGACY_WORKSPACE_CHAT_ID_OFFSET},
    )


def _update_change_log() -> None:
    """Добавляет workspace_id FK в change_log."""
    op.drop_constraint(
        "fk_change_log_actor_id_family_member",
        "change_log",
        type_="foreignkey",
    )
    op.add_column(
        "change_log",
        sa.Column("workspace_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_change_log_workspace_id_workspace"),
        "change_log",
        "workspace",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _drop_family_member_foreign_keys() -> None:
    """Удаляет legacy FK на family_member в health/nutrition таблицах."""
    op.drop_constraint(
        "fk_diet_record_recorded_by_family_member",
        "diet_record",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_feeding_entry_recorded_by_family_member",
        "feeding_entry",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_medical_record_recorded_by_family_member",
        "medical_record",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_medication_recorded_by_family_member",
        "medication",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_note_recorded_by_family_member",
        "note",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_vaccination_recorded_by_family_member",
        "vaccination",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_weight_record_recorded_by_family_member",
        "weight_record",
        type_="foreignkey",
    )


def _drop_deprecated_tables() -> None:
    """Удаляет legacy family-таблицы."""
    op.drop_table("family_invite")
    op.drop_table("family_pet")
    op.drop_table("family_settings")
    op.drop_table("family_member")
    op.drop_table("family")


# ═══════════════════════════════════════════════════════════════════════════════
# Downgrade: восстановление предыдущего состояния
# ═══════════════════════════════════════════════════════════════════════════════


def _restore_family_core_tables() -> None:
    """Восстанавливает таблицы family, family_member, family_settings."""
    op.create_table(
        "family",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "singleton_key",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family")),
        sa.UniqueConstraint("singleton_key", name="uq_family_singleton"),
    )
    op.create_table(
        "family_member",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("is_authorized", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["family.id"],
            name=op.f("fk_family_member_family_id_family"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_member")),
    )
    op.create_table(
        "family_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("date_locale", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["family.id"],
            name=op.f("fk_family_settings_family_id_family"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_settings")),
        sa.UniqueConstraint(
            "family_id",
            name=op.f("uq_family_settings_family_id"),
        ),
    )


def _restore_deprecated_tables() -> None:
    """Восстанавливает family_invite и family_pet."""
    op.create_table(
        "family_pet",
        sa.Column("family_member_id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_member_id"],
            ["family_member.id"],
            name=op.f("fk_family_pet_family_member_id_family_member"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pet_id"],
            ["pet.id"],
            name=op.f("fk_family_pet_pet_id_pet"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "family_member_id",
            "pet_id",
            name=op.f("pk_family_pet"),
        ),
    )
    op.create_table(
        "family_invite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.Column("invite_code", sa.String(length=50), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.BigInteger(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["family_member.id"],
            name=op.f("fk_family_invite_created_by_family_member"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["family.id"],
            name=op.f("fk_family_invite_family_id_family"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["family_member.id"],
            name=op.f("fk_family_invite_used_by_family_member"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_invite")),
        sa.UniqueConstraint(
            "invite_code",
            name=op.f("uq_family_invite_invite_code"),
        ),
    )


def _backfill_family_members_from_workspace_data() -> None:
    """Восстанавливает family_member для user-id, встречающихся в runtime-таблицах."""
    bind = op.get_bind()
    _ensure_singleton_family_row(bind)
    family_id_result = bind.execute(
        sa.text("SELECT id FROM family WHERE singleton_key = true LIMIT 1")
    )
    family_id = family_id_result.scalar_one()

    user_ids = bind.execute(
        sa.text(
            """
            SELECT DISTINCT user_id FROM (
                SELECT actor_id AS user_id FROM change_log WHERE actor_id IS NOT NULL
                UNION
                SELECT created_by AS user_id FROM pet WHERE created_by IS NOT NULL
                UNION
                SELECT telegram_user_id AS user_id
                FROM conversation_state
                WHERE telegram_user_id IS NOT NULL
                UNION
                SELECT recorded_by AS user_id
                FROM diet_record
                WHERE recorded_by IS NOT NULL
                UNION
                SELECT recorded_by AS user_id
                FROM feeding_entry
                WHERE recorded_by IS NOT NULL
                UNION
                SELECT recorded_by AS user_id
                FROM medical_record
                WHERE recorded_by IS NOT NULL
                UNION
                SELECT recorded_by AS user_id
                FROM medication
                WHERE recorded_by IS NOT NULL
                UNION
                SELECT recorded_by AS user_id FROM note WHERE recorded_by IS NOT NULL
                UNION
                SELECT recorded_by AS user_id
                FROM vaccination
                WHERE recorded_by IS NOT NULL
                UNION
                SELECT recorded_by AS user_id
                FROM weight_record
                WHERE recorded_by IS NOT NULL
            ) referenced_users
            ORDER BY user_id
            """
        )
    )
    for row in user_ids:
        bind.execute(
            sa.text(
                """
                INSERT INTO family_member
                    (id, first_name, username, is_authorized, family_id)
                VALUES
                    (:member_id, 'Recovered member', NULL, true, :family_id)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "member_id": int(row.user_id),
                "family_id": int(family_id),
            },
        )


def _ensure_singleton_family_row(bind) -> None:
    """Гарантирует, что в family есть singleton-строка для привязки family_member."""
    bind.execute(
        sa.text(
            """
            INSERT INTO family (singleton_key)
            VALUES (true)
            ON CONFLICT (singleton_key) DO NOTHING
            """
        )
    )


def _backfill_family_id_with_singleton(table_name: str) -> None:
    """Заполняет NULL family_id единственным family.id для downgrade."""
    bind = op.get_bind()
    _ensure_singleton_family_row(bind)
    if table_name == "pet":
        query = sa.text(
            """
            UPDATE pet
            SET family_id = (
                SELECT id FROM family
                WHERE singleton_key = true
                LIMIT 1
            )
            WHERE family_id IS NULL
            """
        )
    else:
        raise ValueError(f"Unsupported table for family_id backfill: {table_name}")

    bind.execute(query)


def _restore_change_log() -> None:
    """Убирает workspace_id из change_log."""
    op.drop_constraint(
        op.f("fk_change_log_workspace_id_workspace"),
        "change_log",
        type_="foreignkey",
    )
    op.drop_column("change_log", "workspace_id")
    op.create_foreign_key(
        "fk_change_log_actor_id_family_member",
        "change_log",
        "family_member",
        ["actor_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _restore_conversation_state() -> None:
    """Восстанавливает legacy conversation_state с детерминированным переносом."""
    op.rename_table("conversation_state", CONVERSATION_STATE_WORKSPACE_TABLE)
    _rename_conversation_state_primary_key(
        CONVERSATION_STATE_WORKSPACE_TABLE,
        "pk_conversation_state_workspace",
    )
    _drop_conversation_state_updated_at_trigger(CONVERSATION_STATE_WORKSPACE_TABLE)
    _create_legacy_conversation_state_table()
    _migrate_conversation_state_rows_to_legacy_schema()
    op.drop_table(CONVERSATION_STATE_WORKSPACE_TABLE)
    _create_conversation_state_updated_at_trigger("conversation_state")


def _rename_conversation_state_primary_key(
    table_name: str,
    new_constraint_name: str,
) -> None:
    """Переименовывает PK conversation_state, чтобы избежать конфликта имён."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    primary_key_exists = bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint AS constraint_definition
                JOIN pg_class AS table_definition
                    ON table_definition.oid = constraint_definition.conrelid
                WHERE constraint_definition.conname = 'pk_conversation_state'
                  AND table_definition.relname = :table_name
            )
            """
        ),
        {"table_name": table_name},
    ).scalar_one()
    if primary_key_exists:
        op.execute(
            f"ALTER TABLE {table_name} "
            "RENAME CONSTRAINT pk_conversation_state "
            f"TO {new_constraint_name};"
        )


def _migrate_conversation_state_rows_to_legacy_schema() -> None:
    """Переносит workspace conversation_state в legacy-формат для downgrade."""
    bind = op.get_bind()
    # Legacy-схема хранит максимум одну запись на user_id, поэтому downgrade
    # осознанно lossy: оставляем newest состояние, при равенстве — с большим turn_count.
    bind.execute(
        sa.text(
            """
            WITH ranked_state AS (
                SELECT
                    telegram_user_id AS user_id,
                    last_response_id,
                    turn_count,
                    session_summary,
                    updated_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY telegram_user_id
                        ORDER BY
                            updated_at DESC NULLS LAST,
                            turn_count DESC,
                            id DESC
                    ) AS row_number
                FROM conversation_state_workspace
            )
            INSERT INTO conversation_state (
                user_id,
                last_response_id,
                turn_count,
                session_summary,
                updated_at
            )
            SELECT
                user_id,
                last_response_id,
                turn_count,
                session_summary,
                updated_at
            FROM ranked_state
            WHERE row_number = 1
            """
        )
    )


def _restore_pet_table() -> None:
    """Восстанавливает family_id в pet."""
    op.add_column(
        "pet",
        sa.Column("family_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pet_family_id_family",
        "pet",
        "family",
        ["family_id"],
        ["id"],
        ondelete="CASCADE",
    )
    _backfill_family_id_with_singleton("pet")
    op.alter_column(
        "pet",
        "family_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_constraint(
        op.f("fk_pet_workspace_id_workspace"),
        "pet",
        type_="foreignkey",
    )
    op.drop_column("pet", "workspace_id")
    op.create_foreign_key(
        "fk_pet_created_by_family_member",
        "pet",
        "family_member",
        ["created_by"],
        ["id"],
        ondelete="CASCADE",
    )


def _restore_family_member_foreign_keys() -> None:
    """Восстанавливает legacy FK на family_member в health/nutrition/audit."""
    op.create_foreign_key(
        "fk_diet_record_recorded_by_family_member",
        "diet_record",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_feeding_entry_recorded_by_family_member",
        "feeding_entry",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_medical_record_recorded_by_family_member",
        "medical_record",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_medication_recorded_by_family_member",
        "medication",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_note_recorded_by_family_member",
        "note",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_vaccination_recorded_by_family_member",
        "vaccination",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_weight_record_recorded_by_family_member",
        "weight_record",
        "family_member",
        ["recorded_by"],
        ["id"],
        ondelete="CASCADE",
    )


def _drop_workspace_tables() -> None:
    """Удаляет workspace, workspace_member, workspace_settings."""
    op.drop_table("workspace_settings")
    op.drop_index(
        op.f("ix_workspace_member_telegram_user_id"),
        table_name="workspace_member",
    )
    op.drop_table("workspace_member")
    op.drop_index(
        op.f("ix_workspace_telegram_chat_id"),
        table_name="workspace",
    )
    op.drop_table("workspace")
