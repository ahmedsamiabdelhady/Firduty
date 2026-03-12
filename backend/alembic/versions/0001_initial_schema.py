"""Initial schema — all Firduty tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

This migration creates the full schema from scratch.
If you are upgrading an EXISTING production database that was created
with Base.metadata.create_all(), run migration 0002 instead and skip this one.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Custom types ───────────────────────────────────────────────────────────
    teacher_status = sa.Enum("pending", "approved", name="teacher_status_enum")
    duty_type      = sa.Enum("morning_endofday", "break", name="duty_type_enum")
    week_status    = sa.Enum("draft", "published", name="week_status")

    teacher_status.create(op.get_bind(), checkfirst=True)
    duty_type.create(op.get_bind(), checkfirst=True)
    week_status.create(op.get_bind(), checkfirst=True)

    # ── app_settings ───────────────────────────────────────────────────────────
    op.create_table(
        "app_settings",
        sa.Column("id",         sa.Integer(),     nullable=False),
        sa.Column("key",        sa.String(100),   nullable=False),
        sa.Column("value",      sa.String(255),   nullable=False),
        sa.Column("updated_at", sa.DateTime(),    nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_app_settings_id", "app_settings", ["id"])

    # ── teachers ───────────────────────────────────────────────────────────────
    op.create_table(
        "teachers",
        sa.Column("id",                 sa.Integer(),      nullable=False),
        sa.Column("name",               sa.String(200),    nullable=False),
        sa.Column("email",              sa.String(255),    nullable=True),
        sa.Column("status",             teacher_status,    nullable=False, server_default="approved"),
        sa.Column("active",             sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("preferred_language", sa.String(2),      nullable=False, server_default="ar"),
        sa.Column("created_at",         sa.DateTime(),     nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teachers_id",    "teachers", ["id"])
    op.create_index("ix_teachers_email", "teachers", ["email"], unique=True)

    # ── device_tokens ──────────────────────────────────────────────────────────
    op.create_table(
        "device_tokens",
        sa.Column("id",         sa.Integer(),     nullable=False),
        sa.Column("teacher_id", sa.Integer(),     nullable=False),
        sa.Column("token",      sa.String(500),   nullable=False),
        sa.Column("platform",   sa.String(10),    nullable=False),
        sa.Column("updated_at", sa.DateTime(),    nullable=True),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_device_tokens_id", "device_tokens", ["id"])

    # ── locations ──────────────────────────────────────────────────────────────
    op.create_table(
        "locations",
        sa.Column("id",      sa.Integer(),     nullable=False),
        sa.Column("name_en", sa.String(200),   nullable=False),
        sa.Column("name_ar", sa.String(200),   nullable=False),
        sa.Column("order",   sa.Integer(),     nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_locations_id", "locations", ["id"])

    # ── shifts ─────────────────────────────────────────────────────────────────
    op.create_table(
        "shifts",
        sa.Column("id",         sa.Integer(),   nullable=False),
        sa.Column("name_en",    sa.String(200), nullable=False),
        sa.Column("name_ar",    sa.String(200), nullable=False),
        sa.Column("start_time", sa.Time(),      nullable=False),
        sa.Column("end_time",   sa.Time(),      nullable=False),
        sa.Column("order",      sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("duty_type",  duty_type,      nullable=False, server_default="morning_endofday"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shifts_id", "shifts", ["id"])

    # ── week_plans ─────────────────────────────────────────────────────────────
    op.create_table(
        "week_plans",
        sa.Column("id",                     sa.Integer(), nullable=False),
        sa.Column("week_start_date",        sa.Date(),    nullable=False),
        sa.Column("status",                 week_status,  nullable=False, server_default="draft"),
        sa.Column("version",                sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cloned_from_week_start", sa.Date(),    nullable=True),
        sa.Column("created_at",             sa.DateTime(), nullable=True),
        sa.Column("updated_at",             sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_start_date"),
    )
    op.create_index("ix_week_plans_id", "week_plans", ["id"])

    # ── day_plans ──────────────────────────────────────────────────────────────
    op.create_table(
        "day_plans",
        sa.Column("id",           sa.Integer(), nullable=False),
        sa.Column("week_plan_id", sa.Integer(), nullable=False),
        sa.Column("date",         sa.Date(),    nullable=False),
        sa.ForeignKeyConstraint(["week_plan_id"], ["week_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_day_plans_id", "day_plans", ["id"])

    # ── shift_locations ────────────────────────────────────────────────────────
    op.create_table(
        "shift_locations",
        sa.Column("id",          sa.Integer(), nullable=False),
        sa.Column("day_plan_id", sa.Integer(), nullable=False),
        sa.Column("shift_id",    sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("slots_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("order",       sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["day_plan_id"],  ["day_plans.id"]),
        sa.ForeignKeyConstraint(["location_id"],  ["locations.id"]),
        sa.ForeignKeyConstraint(["shift_id"],     ["shifts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shift_locations_id", "shift_locations", ["id"])

    # ── assignments ────────────────────────────────────────────────────────────
    op.create_table(
        "assignments",
        sa.Column("id",                sa.Integer(),     nullable=False),
        sa.Column("shift_location_id", sa.Integer(),     nullable=False),
        sa.Column("slot_index",        sa.Integer(),     nullable=False),
        sa.Column("teacher_id",        sa.Integer(),     nullable=True),
        sa.Column("grade_class",       sa.String(100),   nullable=True),
        sa.ForeignKeyConstraint(["shift_location_id"], ["shift_locations.id"]),
        sa.ForeignKeyConstraint(["teacher_id"],        ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assignments_id", "assignments", ["id"])

    # ── change_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "change_logs",
        sa.Column("id",           sa.Integer(),     nullable=False),
        sa.Column("week_plan_id", sa.Integer(),     nullable=False),
        sa.Column("actor",        sa.String(100),   nullable=False),
        sa.Column("action",       sa.String(100),   nullable=False),
        sa.Column("payload_json", sa.Text(),        nullable=True),
        sa.Column("created_at",   sa.DateTime(),    nullable=True),
        sa.ForeignKeyConstraint(["week_plan_id"], ["week_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_change_logs_id", "change_logs", ["id"])

    # ── duty_confirmations ─────────────────────────────────────────────────────
    op.create_table(
        "duty_confirmations",
        sa.Column("id",            sa.Integer(), nullable=False),
        sa.Column("teacher_id",    sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_at",  sa.DateTime(), nullable=False),
        sa.Column("points_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
        sa.ForeignKeyConstraint(["teacher_id"],    ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("teacher_id", "assignment_id", name="uq_confirmation"),
    )
    op.create_index("ix_duty_confirmations_id",   "duty_confirmations", ["id"])
    op.create_index("ix_conf_teacher_month",       "duty_confirmations", ["teacher_id", "confirmed_at"])

    # ── monthly_points_summary ─────────────────────────────────────────────────
    op.create_table(
        "monthly_points_summary",
        sa.Column("id",           sa.Integer(), nullable=False),
        sa.Column("teacher_id",   sa.Integer(), nullable=False),
        sa.Column("year",         sa.Integer(), nullable=False),
        sa.Column("month",        sa.Integer(), nullable=False),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at",   sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("teacher_id", "year", "month", name="uq_monthly_summary"),
    )
    op.create_index("ix_monthly_points_summary_id", "monthly_points_summary", ["id"])
    op.create_index("ix_monthly_year_month",         "monthly_points_summary", ["year", "month"])


def downgrade() -> None:
    op.drop_table("monthly_points_summary")
    op.drop_table("duty_confirmations")
    op.drop_table("change_logs")
    op.drop_table("assignments")
    op.drop_table("shift_locations")
    op.drop_table("day_plans")
    op.drop_table("week_plans")
    op.drop_table("shifts")
    op.drop_table("locations")
    op.drop_table("device_tokens")
    op.drop_table("teachers")
    op.drop_table("app_settings")

    sa.Enum(name="week_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="duty_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="teacher_status_enum").drop(op.get_bind(), checkfirst=True)