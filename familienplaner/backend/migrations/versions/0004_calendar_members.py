"""Kalender mehreren Personen zuordnen (ersetzt calendar.default_member_id)

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendarmember",
        sa.Column("calendar_id", sa.Integer(), sa.ForeignKey("calendar.id"), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("familymember.id"), primary_key=True),
    )
    # Bestehende Einzelzuordnungen übernehmen
    op.execute(
        "INSERT INTO calendarmember (calendar_id, member_id) "
        "SELECT id, default_member_id FROM calendar WHERE default_member_id IS NOT NULL"
    )
    with op.batch_alter_table("calendar") as batch_op:
        batch_op.drop_column("default_member_id")


def downgrade() -> None:
    with op.batch_alter_table("calendar") as batch_op:
        batch_op.add_column(sa.Column("default_member_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE calendar SET default_member_id = "
        "(SELECT MIN(member_id) FROM calendarmember WHERE calendarmember.calendar_id = calendar.id)"
    )
    op.drop_table("calendarmember")
