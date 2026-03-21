"""Добавить таблицы measurement, vet_visit, mood_log, document, heat_cycle.

Новые таблицы для расширения базы данных AI-агента (007-extend-agent-tools).
Все таблицы связаны с pet через FK CASCADE.

Revision ID: b5c6d7e8f9a0
Revises: a1b2c3d4e5f6
Create Date: 2026-03-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать 5 новых таблиц для расширения agent tools."""
    op.create_table(
        "measurement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.Column("measurement_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("measured_at", sa.Date(), nullable=False),
        sa.Column("recorded_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pet_id"],
            ["pet.id"],
            name=op.f("fk_measurement_pet_id_pet"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_measurement")),
    )
    op.create_index(
        "ix_measurement_pet_measured",
        "measurement",
        ["pet_id", "measured_at"],
    )
    op.create_index(
        "ix_measurement_pet_type",
        "measurement",
        ["pet_id", "measurement_type"],
    )

    op.create_table(
        "vet_visit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.Column("clinic", sa.String(length=300), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pet_id"],
            ["pet.id"],
            name=op.f("fk_vet_visit_pet_id_pet"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vet_visit")),
    )
    op.create_index(
        "ix_vet_visit_pet_date",
        "vet_visit",
        ["pet_id", "visit_date"],
    )
    op.create_index(
        "ix_vet_visit_pet_status",
        "vet_visit",
        ["pet_id", "status"],
    )

    op.create_table(
        "mood_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.Column("mood", sa.String(length=20), nullable=False),
        sa.Column("appetite", sa.String(length=20), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pet_id"],
            ["pet.id"],
            name=op.f("fk_mood_log_pet_id_pet"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mood_log")),
    )
    op.create_index(
        "ix_mood_log_pet_date",
        "mood_log",
        ["pet_id", "log_date"],
    )

    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pet_id"],
            ["pet.id"],
            name=op.f("fk_document_pet_id_pet"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
    )
    op.create_index(
        "ix_document_pet_type",
        "document",
        ["pet_id", "document_type"],
    )

    op.create_table(
        "heat_cycle",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pet_id"],
            ["pet.id"],
            name=op.f("fk_heat_cycle_pet_id_pet"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heat_cycle")),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name=op.f("ck_heat_cycle_end_date_gte_start_date"),
        ),
    )
    op.create_index(
        "ix_heat_cycle_pet_start",
        "heat_cycle",
        ["pet_id", "start_date"],
    )


def downgrade() -> None:
    """Удалить 5 таблиц расширения agent tools."""
    op.drop_index("ix_heat_cycle_pet_start", table_name="heat_cycle")
    op.drop_table("heat_cycle")

    op.drop_index("ix_document_pet_type", table_name="document")
    op.drop_table("document")

    op.drop_index("ix_mood_log_pet_date", table_name="mood_log")
    op.drop_table("mood_log")

    op.drop_index("ix_vet_visit_pet_status", table_name="vet_visit")
    op.drop_index("ix_vet_visit_pet_date", table_name="vet_visit")
    op.drop_table("vet_visit")

    op.drop_index("ix_measurement_pet_type", table_name="measurement")
    op.drop_index("ix_measurement_pet_measured", table_name="measurement")
    op.drop_table("measurement")
