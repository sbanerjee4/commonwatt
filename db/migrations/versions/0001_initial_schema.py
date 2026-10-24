"""initial schema

Creates every table in db/models.py: utilities, zips, zip_utility, buildings,
users, sessions, events, plan_buildings, call_history, replies, meter_reads,
heat_day_intervals, trace_steps, audit_log. CHECK constraints and indexes are
included. The same revision runs on SQLite and Postgres: timestamp defaults use
sa.func.now(), which each dialect compiles to its own form.

Revision ID: 0001
Revises:
Create Date: 2026-10-24 14:19:08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "utilities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_utilities")),
    )

    op.create_table(
        "zips",
        sa.Column("zip", sa.String(length=10), nullable=False),
        sa.Column("ej", sa.Boolean(), nullable=False),
        sa.Column("ej_source_id", sa.String(length=255), nullable=True),
        sa.Column("centroid_lng", sa.Float(), nullable=True),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("zip", name=op.f("pk_zips")),
    )

    op.create_table(
        "buildings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("zip", sa.String(length=10), nullable=False),
        sa.Column("address", sa.String(length=512), nullable=False),
        sa.Column("property_type", sa.String(length=255), nullable=True),
        sa.Column("gross_area_sf", sa.Float(), nullable=True),
        sa.Column("site_eui", sa.Float(), nullable=True),
        sa.Column("per_electricity", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("geocode_status", sa.String(length=64), nullable=True),
        sa.Column("enrolled", sa.Boolean(), nullable=False),
        sa.Column("enrolled_capacity_kw", sa.Float(), nullable=True),
        sa.Column("offered_capacity_kw", sa.Float(), nullable=True),
        sa.Column("protected", sa.Boolean(), nullable=False),
        sa.Column("protected_reason", sa.Text(), nullable=True),
        sa.Column("protected_kind", sa.String(length=64), nullable=True),
        sa.Column("simulated", sa.Boolean(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["zip"], ["zips.zip"], name=op.f("fk_buildings_zip_zips"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buildings")),
    )
    op.create_index(op.f("ix_buildings_zip"), "buildings", ["zip"], unique=False)

    op.create_table(
        "heat_day_intervals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zip", sa.String(length=10), nullable=False),
        sa.Column("load_kw", sa.Float(), nullable=False),
        sa.Column("participating_kw", sa.Float(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utilities.id"],
            name=op.f("fk_heat_day_intervals_utility_id_utilities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["zip"], ["zips.zip"], name=op.f("fk_heat_day_intervals_zip_zips"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heat_day_intervals")),
    )
    op.create_index(
        "ix_heat_day_intervals_day_interval",
        "heat_day_intervals",
        ["day", "interval_start"],
        unique=False,
    )
    op.create_index(
        op.f("ix_heat_day_intervals_utility_id"), "heat_day_intervals", ["utility_id"], unique=False
    )
    op.create_index(op.f("ix_heat_day_intervals_zip"), "heat_day_intervals", ["zip"], unique=False)

    op.create_table(
        "zip_utility",
        sa.Column("zip", sa.String(length=10), nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=False),
        sa.Column("town", sa.String(length=255), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utilities.id"],
            name=op.f("fk_zip_utility_utility_id_utilities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["zip"], ["zips.zip"], name=op.f("fk_zip_utility_zip_zips"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("zip", name=op.f("pk_zip_utility")),
    )
    op.create_index(op.f("ix_zip_utility_utility_id"), "zip_utility", ["utility_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=True),
        sa.Column("building_id", sa.String(length=64), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('utility', 'building_manager')", name=op.f("ck_users_role_allowed")
        ),
        sa.CheckConstraint(
            "(role = 'utility' AND utility_id IS NOT NULL AND building_id IS NULL) "
            "OR (role = 'building_manager' AND building_id IS NOT NULL AND utility_id IS NULL)",
            name=op.f("ck_users_role_scope_match"),
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_users_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utilities.id"],
            name=op.f("fk_users_utility_id_utilities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_building_id"), "users", ["building_id"], unique=False)
    op.create_index(op.f("ix_users_utility_id"), "users", ["utility_id"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("utility_id", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_label", sa.String(length=255), nullable=False),
        sa.Column("target_mw", sa.Float(), nullable=False),
        sa.Column("cap_pct", sa.Float(), nullable=False),
        sa.Column("heat_threshold_exceeded", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')", name=op.f("ck_events_status_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_events_approved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["utility_id"],
            ["utilities.id"],
            name=op.f("fk_events_utility_id_utilities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_utility_id"), "events", ["utility_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("building_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "action IN ('approved', 'rejected', 'edited', 'resolved', 'protected_set', "
            "'protected_cleared', 'reply_submitted', 'capacity_updated')",
            name=op.f("ck_audit_log_action_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_audit_log_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_audit_log_event_id_events"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_log_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_building_id"), "audit_log", ["building_id"], unique=False)
    op.create_index(op.f("ix_audit_log_event_id"), "audit_log", ["event_id"], unique=False)
    op.create_index(op.f("ix_audit_log_user_id"), "audit_log", ["user_id"], unique=False)

    op.create_table(
        "call_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("kw_requested", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("est_payment", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_call_history_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_call_history_event_id_events"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_history")),
    )
    op.create_index(
        op.f("ix_call_history_building_id"), "call_history", ["building_id"], unique=False
    )
    op.create_index(op.f("ix_call_history_event_id"), "call_history", ["event_id"], unique=False)

    op.create_table(
        "plan_buildings",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("kw_requested", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_plan_buildings_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_plan_buildings_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "event_id", "plan_version", "building_id", name=op.f("pk_plan_buildings")
        ),
    )

    op.create_table(
        "trace_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("rejected_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_trace_steps_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trace_steps")),
    )
    op.create_index(op.f("ix_trace_steps_event_id"), "trace_steps", ["event_id"], unique=False)

    op.create_table(
        "meter_reads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kw", sa.Float(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_meter_reads_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["call_history.id"],
            name=op.f("fk_meter_reads_call_id_call_history"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meter_reads")),
    )
    op.create_index(op.f("ix_meter_reads_building_id"), "meter_reads", ["building_id"], unique=False)
    op.create_index(op.f("ix_meter_reads_call_id"), "meter_reads", ["call_id"], unique=False)

    op.create_table(
        "replies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("call_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("offer_kw", sa.Float(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default="0", nullable=False),
        sa.CheckConstraint("kind IN ('yes', 'no', 'offer')", name=op.f("ck_replies_kind_allowed")),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_replies_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["call_history.id"],
            name=op.f("fk_replies_call_id_call_history"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_replies")),
    )
    op.create_index(op.f("ix_replies_building_id"), "replies", ["building_id"], unique=False)
    op.create_index(op.f("ix_replies_call_id"), "replies", ["call_id"], unique=False)


def downgrade() -> None:
    # Dependents are dropped before the tables they reference.
    op.drop_index(op.f("ix_replies_call_id"), table_name="replies")
    op.drop_index(op.f("ix_replies_building_id"), table_name="replies")
    op.drop_table("replies")

    op.drop_index(op.f("ix_meter_reads_call_id"), table_name="meter_reads")
    op.drop_index(op.f("ix_meter_reads_building_id"), table_name="meter_reads")
    op.drop_table("meter_reads")

    op.drop_index(op.f("ix_trace_steps_event_id"), table_name="trace_steps")
    op.drop_table("trace_steps")

    op.drop_table("plan_buildings")

    op.drop_index(op.f("ix_call_history_event_id"), table_name="call_history")
    op.drop_index(op.f("ix_call_history_building_id"), table_name="call_history")
    op.drop_table("call_history")

    op.drop_index(op.f("ix_audit_log_user_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_event_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_building_id"), table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")

    op.drop_index(op.f("ix_events_utility_id"), table_name="events")
    op.drop_table("events")

    op.drop_index(op.f("ix_users_utility_id"), table_name="users")
    op.drop_index(op.f("ix_users_building_id"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_zip_utility_utility_id"), table_name="zip_utility")
    op.drop_table("zip_utility")

    op.drop_index(op.f("ix_heat_day_intervals_zip"), table_name="heat_day_intervals")
    op.drop_index(op.f("ix_heat_day_intervals_utility_id"), table_name="heat_day_intervals")
    op.drop_index("ix_heat_day_intervals_day_interval", table_name="heat_day_intervals")
    op.drop_table("heat_day_intervals")

    op.drop_index(op.f("ix_buildings_zip"), table_name="buildings")
    op.drop_table("buildings")

    op.drop_table("zips")
    op.drop_table("utilities")
