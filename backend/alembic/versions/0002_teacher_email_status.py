"""Add email and status to teachers table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00.000000

PRODUCTION FIX
──────────────
This migration adds the two columns that were missing from the production
teachers table, causing:

  psycopg2.errors.UndefinedColumn:
  column "email" of relation "teachers" does not exist

Root cause: Base.metadata.create_all() was used to initialise the database,
which only creates tables that do not yet exist. When the Teacher ORM model
was later updated to include 'email' and 'status', the EXISTING production
table was NOT altered.

This migration corrects the schema drift safely:
  - email:  nullable VARCHAR(255) with a partial unique index
  - status: NOT NULL VARCHAR with server_default='approved' so all existing
            rows are automatically set to 'approved' on alter
  - Also fixes order columns on locations, shifts, shift_locations to be
    NOT NULL with server_default='0', eliminating NULL serialization errors.

Running on existing production DB (Supabase / Koyeb):
  cd backend/
  alembic upgrade 0002

Or manually via psql:
  See migrations/004_production_fix.sql
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── teachers.email ─────────────────────────────────────────────────────────
    op.add_column(
        "teachers",
        sa.Column("email", sa.String(255), nullable=True),
    )
    # Partial unique index: two NULLs are allowed, two identical non-NULL values are not.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_teachers_email "
        "ON teachers (email) WHERE email IS NOT NULL"
    )

    # ── teachers.status ────────────────────────────────────────────────────────
    # Create the enum type first (checkfirst avoids error if it already exists).
    teacher_status = sa.Enum("pending", "approved", name="teacher_status_enum")
    teacher_status.create(bind, checkfirst=True)

    op.add_column(
        "teachers",
        sa.Column(
            "status",
            sa.Enum("pending", "approved", name="teacher_status_enum"),
            nullable=False,
            server_default="approved",
        ),
    )

    # ── Fix NULL order columns ─────────────────────────────────────────────────
    # These were added as nullable in earlier app versions; set existing NULLs
    # to 0 then enforce NOT NULL + server_default so future inserts are safe.
    for table_col in [
        ("locations",      "order"),
        ("shifts",         "order"),
        ("shift_locations", "order"),
        ("shift_locations", "slots_count"),
    ]:
        table, col = table_col
        default = "1" if col == "slots_count" else "0"
        op.execute(f'UPDATE "{table}" SET "{col}" = {default} WHERE "{col}" IS NULL')
        op.alter_column(
            table, col,
            nullable=False,
            server_default=default,
        )


def downgrade() -> None:
    op.drop_column("teachers", "status")
    op.execute("DROP INDEX IF EXISTS ix_teachers_email")
    op.drop_column("teachers", "email")
    # Restore nullable (do not drop the enum type — other migrations may use it)
    for table_col in [
        ("locations",       "order"),
        ("shifts",          "order"),
        ("shift_locations",  "order"),
        ("shift_locations",  "slots_count"),
    ]:
        table, col = table_col
        op.alter_column(table, col, nullable=True, server_default=None)