"""handoff layer + SMS removal

Builds on the merged in-app channel (0002/0003). Adds the automated-agent +
human-handoff layer and removes SMS:
  - new table: threads (handoff_mode auto/human, needs_human, closed_at)
  - messages.sender_role CHECK gains 'agent'
  - audit_log action CHECK rebuilt to the SMS-free chat action set
  - drop outbound_messages
  - drop users.phone, users.sms_opted_out

Same revision runs on SQLite and Postgres; CHECK/column edits use
batch_alter_table so SQLite rebuilds the table and Postgres ALTERs in place.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24 17:10:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMING = {"ck": "ck_%(table_name)s_%(constraint_name)s"}

# audit_log actions AFTER this migration (SMS actions removed).
_ACTIONS_NEW = (
    "approved", "rejected", "edited", "resolved", "protected_set",
    "protected_cleared", "reply_submitted", "capacity_updated",
    "chat_agent_reply", "chat_handoff_requested", "chat_building_reply",
    "chat_operator_message", "chat_thread_closed",
)
# audit_log actions BEFORE (the 0002 SMS-era set), for downgrade.
_ACTIONS_OLD = (
    "approved", "rejected", "edited", "resolved", "protected_set",
    "protected_cleared", "reply_submitted", "capacity_updated",
    "sms_sent", "sms_skipped", "sms_failed", "chat_building_reply",
    "chat_operator_message", "chat_thread_closed",
    "sms_webhook_invalid_signature", "sms_unregistered_sender",
    "sms_opted_out", "sms_opted_in", "sms_unrecognized_body",
    "sms_no_active_event", "sms_received",
)
_ROLES_NEW = ("system", "agent", "building_manager", "operator")
_ROLES_OLD = ("system", "building_manager", "operator")


def _in_list(column, values):
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("handoff_mode", sa.String(length=16), server_default="auto", nullable=False),
        sa.Column("needs_human", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in_list("handoff_mode", ("auto", "human")),
                           name=op.f("ck_threads_handoff_mode_allowed")),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"],
                                name=op.f("fk_threads_building_id_buildings"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"],
                                name=op.f("fk_threads_event_id_events"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threads")),
    )
    op.create_index(op.f("ix_threads_building_id"), "threads", ["building_id"], unique=False)
    op.create_index(op.f("ix_threads_event_id"), "threads", ["event_id"], unique=False)
    op.create_index("uq_threads_event_id", "threads", ["event_id", "building_id"], unique=True)

    # messages.sender_role gains 'agent'.
    with op.batch_alter_table("messages", schema=None, naming_convention=_NAMING) as b:
        b.drop_constraint("sender_role_allowed", type_="check")
        b.create_check_constraint("sender_role_allowed", _in_list("sender_role", _ROLES_NEW))

    # audit_log action set loses the SMS actions.
    with op.batch_alter_table("audit_log", schema=None, naming_convention=_NAMING) as b:
        b.drop_constraint("action_allowed", type_="check")
        b.create_check_constraint("action_allowed", _in_list("action", _ACTIONS_NEW))

    # Drop SMS-only storage.
    op.drop_table("outbound_messages")
    with op.batch_alter_table("users", schema=None) as b:
        b.drop_column("sms_opted_out")
        b.drop_column("phone")


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as b:
        b.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        b.add_column(sa.Column("sms_opted_out", sa.Boolean(), server_default="0", nullable=False))
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_sid", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"],
                                name=op.f("fk_outbound_messages_event_id_events"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_outbound_messages_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_messages")),
    )
    with op.batch_alter_table("audit_log", schema=None, naming_convention=_NAMING) as b:
        b.drop_constraint("action_allowed", type_="check")
        b.create_check_constraint("action_allowed", _in_list("action", _ACTIONS_OLD))
    with op.batch_alter_table("messages", schema=None, naming_convention=_NAMING) as b:
        b.drop_constraint("sender_role_allowed", type_="check")
        b.create_check_constraint("sender_role_allowed", _in_list("sender_role", _ROLES_OLD))

    op.drop_index("uq_threads_event_id", table_name="threads")
    op.drop_index(op.f("ix_threads_event_id"), table_name="threads")
    op.drop_index(op.f("ix_threads_building_id"), table_name="threads")
    op.drop_table("threads")
