"""Kalender mehreren Personen zuordnen (ersetzt calendar.default_member_id)

Revision ID: 0004
Revises: 0003

Idempotent geschrieben: repariert auch Datenbanken, in denen eine frühere Version dieser Migration
nach dem Anlegen von ``calendarmember`` abgebrochen ist.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "calendarmember" not in inspector.get_table_names():
        op.create_table(
            "calendarmember",
            sa.Column("calendar_id", sa.Integer(), sa.ForeignKey("calendar.id"), primary_key=True),
            sa.Column("member_id", sa.Integer(), sa.ForeignKey("familymember.id"), primary_key=True),
        )
    columns = {c["name"] for c in inspector.get_columns("calendar")}
    if "default_member_id" in columns:
        # Bestehende Einzelzuordnungen übernehmen (doppelte aus einem abgebrochenen Lauf ignorieren)
        op.execute(
            "INSERT OR IGNORE INTO calendarmember (calendar_id, member_id) "
            "SELECT id, default_member_id FROM calendar WHERE default_member_id IS NOT NULL "
            "AND default_member_id IN (SELECT id FROM familymember)"
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
