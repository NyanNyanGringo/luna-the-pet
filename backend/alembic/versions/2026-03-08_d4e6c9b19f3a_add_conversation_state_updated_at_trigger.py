"""add conversation_state updated_at trigger

Revision ID: d4e6c9b19f3a
Revises: 7f0ce16e469b
Create Date: 2026-03-08 21:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e6c9b19f3a"
down_revision: str | Sequence[str] | None = "7f0ce16e469b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
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
        """
        CREATE TRIGGER trg_conversation_state_set_updated_at
        BEFORE UPDATE ON conversation_state
        FOR EACH ROW
        EXECUTE FUNCTION conversation_state_set_updated_at();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_conversation_state_set_updated_at
        ON conversation_state;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS conversation_state_set_updated_at();")
